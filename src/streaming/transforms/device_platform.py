"""Device platform aggregation query for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import CHECKPOINT_BASE, TRIGGER_DERIVED


def build_platform_breakdown(sessions_df: DataFrame) -> DataFrame:
    return (
        sessions_df.filter(F.col("is_active") == True)
        .groupBy("platform")
        .count()
        .select(
            F.col("platform").alias("name"),
            F.col("count").alias("value"),
        )
    )


def start_device_platform_aggregator(sessions_df: DataFrame) -> StreamingQuery:
    frame = build_platform_breakdown(sessions_df)
    return (
        frame.writeStream.outputMode("complete")
        .format("memory")
        .queryName("nexus_device_platform")
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/platform")
        .trigger(processingTime=TRIGGER_DERIVED)
        .start()
    )
