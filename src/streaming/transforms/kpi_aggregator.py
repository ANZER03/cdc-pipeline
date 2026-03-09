"""KPI aggregation query wiring for Nexus."""

from __future__ import annotations

from typing import Any, cast

from pyspark.sql import DataFrame, Row
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import (
    ALERT_RULES,
    CHECKPOINT_BASE,
    CHANNEL_ALERTS,
    CHANNEL_KPI,
    KPI_SLIDE_INTERVAL,
    KPI_WINDOW_DURATION,
    REDIS_KEY_ALERT_RULES,
    REDIS_KEY_ALERT_SUMMARY,
    REDIS_KEY_KPI_CURRENT,
    REDIS_KEY_KPI_SNAPSHOT,
    TOPIC_AGGREGATED_KPIS,
    TRIGGER_TRANSACTIONS,
)
from streaming.redis_client import NexusRedisWriter


def _current_epoch_hour(updated_at_ms: int) -> int:
    return updated_at_ms // 3_600_000


def _previous_epoch_hour(updated_at_ms: int) -> int:
    return max(_current_epoch_hour(updated_at_ms) - 1, 0)


def _compute_trend(current: float, previous: float | None) -> float:
    if previous in (None, 0):
        return 0.0
    return round(((current - previous) / previous) * 100.0, 1)


def _serialize_kpi_row(row: Row) -> dict[str, float | int]:
    data = cast(dict, row.asDict(recursive=True))
    return {
        "activeUsers": int(data["activeUsers"] or 0),
        "revenue": round(float(data["revenue"] or 0.0), 2),
        "orders": int(data["orders"] or 0),
        "errorRate": round(float(data["errorRate"] or 0.0), 2),
        "latency": int(data["latency"] or 0),
        "updatedAt": int(data["updatedAt"]),
    }


def write_kpi_batch(batch_df: DataFrame, batch_id: int) -> None:
    del batch_id
    rows = batch_df.orderBy(F.col("updatedAt").desc()).limit(1).collect()
    if not rows:
        return

    writer = NexusRedisWriter()
    current = _serialize_kpi_row(rows[0])
    updated_at = int(current["updatedAt"])
    current_hour = _current_epoch_hour(updated_at)
    snapshot_key = REDIS_KEY_KPI_SNAPSHOT.format(epoch_hour=current_hour)
    previous_snapshot_key = REDIS_KEY_KPI_SNAPSHOT.format(
        epoch_hour=_previous_epoch_hour(updated_at)
    )
    previous = writer.read_hash(previous_snapshot_key)

    payload = {
        **current,
        "activeUsersTrend": _compute_trend(
            current["activeUsers"], _as_float(previous.get("activeUsers"))
        ),
        "revenueTrend": _compute_trend(current["revenue"], _as_float(previous.get("revenue"))),
        "ordersTrend": _compute_trend(current["orders"], _as_float(previous.get("orders"))),
        "errorRateTrend": _compute_trend(
            current["errorRate"], _as_float(previous.get("errorRate"))
        ),
        "latencyTrend": _compute_trend(current["latency"], _as_float(previous.get("latency"))),
    }

    writer.write_hash(REDIS_KEY_KPI_CURRENT, payload, channel=CHANNEL_KPI)
    writer.write_hash(snapshot_key, current, ttl=7200)
    _write_alerts(writer, payload)


def _as_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _write_alerts(writer: NexusRedisWriter, payload: dict[str, float | int]) -> None:
    rules = []
    for rule in ALERT_RULES:
        if rule["metric"] == "system.latency.p99":
            current_value = float(payload["latency"])
        elif rule["metric"] == "checkout.error_rate":
            current_value = float(payload["errorRate"])
        else:
            current_value = 0.0

        status = "firing" if current_value >= float(rule["threshold"]) else "ok"
        rules.append(
            {
                "id": rule["id"],
                "name": rule["name"],
                "status": status,
                "severity": rule["severity"],
                "metric": rule["metric"],
                "currentValue": round(current_value, 2),
                "threshold": float(rule["threshold"]),
                "updatedAt": int(payload["updatedAt"]),
                "lastEvaluated": int(payload["updatedAt"]),
                "frequency": rule["frequency"],
            }
        )

    summary = {
        "criticalCount": sum(
            1 for rule in rules if rule["severity"] == "critical" and rule["status"] != "ok"
        ),
        "warningCount": sum(
            1 for rule in rules if rule["severity"] == "warning" and rule["status"] != "ok"
        ),
        "healthyCount": sum(1 for rule in rules if rule["status"] == "ok"),
        "criticalImpact": "Currently affecting 0% of users",
        "updatedAt": int(payload["updatedAt"]),
    }
    writer.write_json(REDIS_KEY_ALERT_RULES, rules, channel=CHANNEL_ALERTS)
    writer.write_hash(REDIS_KEY_ALERT_SUMMARY, summary)


def build_kpi_frame(
    orders_df: DataFrame, sessions_df: DataFrame, request_log_df: DataFrame
) -> DataFrame:
    order_events = orders_df.filter(F.col("status") == "completed").select(
        F.col("updated_at").alias("event_time"),
        F.lit(0).alias("active_session_count"),
        F.col("total_amount").cast("double").alias("revenue_amount"),
        F.lit(1).alias("order_count"),
        F.lit(0).alias("request_count"),
        F.lit(0).alias("error_count"),
        F.lit(None).cast("double").alias("latency_ms"),
    )
    session_events = sessions_df.filter(F.col("is_active") & F.col("ended_at").isNull()).select(
        F.col("started_at").alias("event_time"),
        F.lit(1).alias("active_session_count"),
        F.lit(0.0).alias("revenue_amount"),
        F.lit(0).alias("order_count"),
        F.lit(0).alias("request_count"),
        F.lit(0).alias("error_count"),
        F.lit(None).cast("double").alias("latency_ms"),
    )
    request_events = request_log_df.select(
        F.col("created_at").alias("event_time"),
        F.lit(0).alias("active_session_count"),
        F.lit(0.0).alias("revenue_amount"),
        F.lit(0).alias("order_count"),
        F.lit(1).alias("request_count"),
        F.when(F.col("status_code") >= 500, F.lit(1)).otherwise(F.lit(0)).alias("error_count"),
        F.col("latency_ms").cast("double").alias("latency_ms"),
    )

    combined_events = (
        order_events.unionByName(session_events)
        .unionByName(request_events)
        .withWatermark("event_time", "10 minutes")
    )

    return (
        combined_events.groupBy(F.window("event_time", KPI_WINDOW_DURATION, KPI_SLIDE_INTERVAL))
        .agg(
            F.sum("active_session_count").cast("long").alias("activeUsers"),
            F.sum("revenue_amount").alias("revenue"),
            F.sum("order_count").cast("long").alias("orders"),
            (F.sum("error_count") / F.greatest(F.sum("request_count"), F.lit(1)) * 100.0).alias(
                "errorRate"
            ),
            F.expr("percentile_approx(latency_ms, 0.5)").alias("latency"),
        )
        .select(
            F.col("window"),
            F.col("activeUsers"),
            F.col("revenue"),
            F.col("orders"),
            F.col("errorRate"),
            F.coalesce(F.col("latency"), F.lit(0)).cast("long").alias("latency"),
            (F.col("window.end").cast("double") * 1000).cast("long").alias("updatedAt"),
        )
    )


def start_kpi_aggregator(
    orders_df: DataFrame, sessions_df: DataFrame, request_log_df: DataFrame
) -> tuple[StreamingQuery, StreamingQuery]:
    frame = build_kpi_frame(orders_df, sessions_df, request_log_df)
    redis_query = (
        frame.writeStream.outputMode("update")
        .foreachBatch(write_kpi_batch)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/kpi")
        .trigger(processingTime=TRIGGER_TRANSACTIONS)
        .start()
    )
    kafka_payload = frame.select(
        F.col("updatedAt").cast("string").alias("key"),
        F.to_json(
            F.struct(
                "activeUsers",
                F.lit(0.0).alias("activeUsersTrend"),
                "revenue",
                F.lit(0.0).alias("revenueTrend"),
                "orders",
                F.lit(0.0).alias("ordersTrend"),
                F.round(F.col("errorRate"), 2).alias("errorRate"),
                F.lit(0.0).alias("errorRateTrend"),
                "latency",
                F.lit(0.0).alias("latencyTrend"),
                "updatedAt",
            )
        ).alias("value"),
    )
    kafka_query = (
        kafka_payload.writeStream.format("kafka")
        .outputMode("update")
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/kpi-kafka")
        .option("kafka.bootstrap.servers", "kafka-1:9092,kafka-2:9093")
        .option("topic", TOPIC_AGGREGATED_KPIS)
        .trigger(processingTime=TRIGGER_TRANSACTIONS)
        .start()
    )
    return redis_query, kafka_query
