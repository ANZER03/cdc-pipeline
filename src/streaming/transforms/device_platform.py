"""Device platform aggregation query for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import (
    CHANNEL_PLATFORM,
    CHECKPOINT_BASE,
    REDIS_KEY_PLATFORM_BREAKDOWN,
    TRIGGER_DERIVED,
)
from streaming.redis_client import NexusRedisWriter


def write_platform_batch(batch_df: DataFrame, batch_id: int) -> None:
    del batch_id
    rows = batch_df.collect()
    payload = [row.asDict(recursive=True) for row in rows]
    NexusRedisWriter().write_json(REDIS_KEY_PLATFORM_BREAKDOWN, payload, channel=CHANNEL_PLATFORM)


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
        .foreachBatch(write_platform_batch)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/platform")
        .trigger(processingTime=TRIGGER_DERIVED)
        .start()
    )
