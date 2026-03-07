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
        "criticalCount": sum(1 for row in payload if row["severity"] == "critical"),
        "warningCount": sum(1 for row in payload if row["severity"] == "warning"),
        "healthyCount": sum(1 for row in payload if row["status"] == "ok"),
        "criticalImpact": "Currently affecting 0% of users",
        "updatedAt": payload[0]["lastEvaluated"],
    }
    writer = NexusRedisWriter()
    writer.write_json(REDIS_KEY_ALERT_RULES, payload, channel=CHANNEL_ALERTS)
    writer.write_hash(REDIS_KEY_ALERT_SUMMARY, summary)


def build_alert_frame(kpis_stream: DataFrame) -> DataFrame:
    if "value" in kpis_stream.columns:
        base = kpis_stream.selectExpr("CAST(value AS STRING) AS raw_value")
    else:
        base = kpis_stream.select(F.to_json(F.struct("*")).alias("raw_value"))

    return (
        base.groupBy()
        .agg(F.count("*").alias("sample_count"))
        .select(
            F.lit(ALERT_RULES[0]["id"]).alias("id"),
            F.lit(ALERT_RULES[0]["name"]).alias("name"),
            F.when(F.col("sample_count") > 0, F.lit("ok"))
            .otherwise(F.lit("pending"))
            .alias("status"),
            F.lit(ALERT_RULES[0]["severity"]).alias("severity"),
            F.lit(ALERT_RULES[0]["metric"]).alias("metric"),
            F.col("sample_count").cast("double").alias("currentValue"),
            F.lit(ALERT_RULES[0]["threshold"]).alias("threshold"),
            F.current_timestamp().alias("lastEvaluated"),
            F.lit(ALERT_RULES[0]["frequency"]).alias("frequency"),
        )
    )


def start_alert_evaluator(kpis_stream: DataFrame) -> StreamingQuery:
    frame = build_alert_frame(kpis_stream)
    return (
        frame.writeStream.outputMode("complete")
        .foreachBatch(write_alert_batch)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/alerts")
        .trigger(processingTime=TRIGGER_DERIVED)
        .start()
    )
