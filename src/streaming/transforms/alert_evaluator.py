"""Alert evaluation query for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import (
    ALERT_RULES,
    CHANNEL_ALERTS,
    CHECKPOINT_BASE,
    REDIS_KEY_ALERT_RULES,
    REDIS_KEY_ALERT_SUMMARY,
    TRIGGER_DERIVED,
)
from streaming.redis_client import NexusRedisWriter


def write_alert_batch(batch_df: DataFrame, batch_id: int) -> None:
    del batch_id
    rows = batch_df.collect()
    if not rows:
        return

    payload = [row.asDict(recursive=True) for row in rows]
    summary = {
        "criticalCount": sum(
            1 for row in payload if row["severity"] == "critical" and row["status"] != "ok"
        ),
        "warningCount": sum(
            1 for row in payload if row["severity"] == "warning" and row["status"] != "ok"
        ),
        "healthyCount": sum(1 for row in payload if row["status"] == "ok"),
        "criticalImpact": "Currently affecting 0% of users",
        "updatedAt": max(int(row["updatedAt"]) for row in payload),
    }
    writer = NexusRedisWriter()
    writer.write_json(REDIS_KEY_ALERT_RULES, payload, channel=CHANNEL_ALERTS)
    writer.write_hash(REDIS_KEY_ALERT_SUMMARY, summary)


def build_alert_frame(kpis_stream: DataFrame) -> DataFrame:
    rule_rows = []
    for rule in ALERT_RULES:
        metric_column = {
            "system.latency.p99": "latency",
            "checkout.error_rate": "errorRate",
            "db.cpu.percent": None,
        }[rule["metric"]]
        if metric_column is None:
            current_value = F.lit(0.0).alias("currentValue")
            status = F.lit("pending").alias("status")
        else:
            current_value = F.col(metric_column).cast("double").alias("currentValue")
            status = (
                F.when(F.col(metric_column) >= F.lit(float(rule["threshold"])), F.lit("firing"))
                .otherwise(F.lit("ok"))
                .alias("status")
            )
        rule_rows.append(
            kpis_stream.select(
                F.lit(rule["id"]).alias("id"),
                F.lit(rule["name"]).alias("name"),
                status,
                F.lit(rule["severity"]).alias("severity"),
                F.lit(rule["metric"]).alias("metric"),
                current_value,
                F.lit(float(rule["threshold"])).alias("threshold"),
                F.col("updatedAt").cast("long").alias("updatedAt"),
                F.from_unixtime(F.col("updatedAt") / 1000.0).alias("lastEvaluated"),
                F.lit(rule["frequency"]).alias("frequency"),
            )
        )
    frame = rule_rows[0]
    for extra in rule_rows[1:]:
        frame = frame.unionByName(extra)
    return frame


def start_alert_evaluator(kpis_stream: DataFrame) -> StreamingQuery:
    frame = build_alert_frame(kpis_stream)
    return (
        frame.writeStream.outputMode("update")
        .foreachBatch(write_alert_batch)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/alerts-v2")
        .trigger(processingTime=TRIGGER_DERIVED)
        .start()
    )
