"""Alert evaluation query for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import ALERT_RULES, CHECKPOINT_BASE, TRIGGER_DERIVED


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
        .format("memory")
        .queryName("nexus_alert_evaluator")
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/alerts")
        .trigger(processingTime=TRIGGER_DERIVED)
        .start()
    )
