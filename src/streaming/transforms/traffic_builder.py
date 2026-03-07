"""Traffic time-series query for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import CHECKPOINT_BASE, TRAFFIC_WINDOW_DURATION, TRIGGER_INFRASTRUCTURE


def build_traffic_points(request_log_df: DataFrame) -> DataFrame:
    return (
        request_log_df.groupBy(F.window("created_at", TRAFFIC_WINDOW_DURATION))
        .agg(F.count("*").alias("value"))
        .select(
            (F.col("window.end").cast("double") * 1000).cast("long").alias("timestamp"),
            F.col("value"),
            F.date_format(F.col("window.end"), "hh:mm:ss a").alias("label"),
        )
    )


def start_traffic_builder(request_log_df: DataFrame) -> StreamingQuery:
    frame = build_traffic_points(request_log_df)
    return (
        frame.writeStream.outputMode("complete")
        .format("memory")
        .queryName("nexus_traffic_builder")
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/traffic")
        .trigger(processingTime=TRIGGER_INFRASTRUCTURE)
        .start()
    )
