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


def seed_platform_breakdown(users_df: DataFrame) -> None:
    rows = (
        users_df.filter(F.col("platform").isNotNull())
        .groupBy("platform")
        .count()
        .select(F.col("platform").alias("name"), F.col("count").alias("value"))
        .collect()
    )
    if not rows:
        return

    payload = [row.asDict(recursive=True) for row in rows]
    payload.sort(key=lambda item: item["name"])
    NexusRedisWriter().write_json(REDIS_KEY_PLATFORM_BREAKDOWN, payload, channel=CHANNEL_PLATFORM)


def write_platform_batch(batch_df: DataFrame, batch_id: int) -> None:
    del batch_id
    rows = batch_df.collect()
    if not rows:
        return

    payload = [
        {
            "name": row["name"],
            "value": int(row["value"] or 0),
        }
        for row in rows
    ]
    payload.sort(key=lambda item: item["name"])
    NexusRedisWriter().write_json(REDIS_KEY_PLATFORM_BREAKDOWN, payload, channel=CHANNEL_PLATFORM)


def build_platform_breakdown(sessions_df: DataFrame) -> DataFrame:
    return (
        sessions_df.filter(F.col("platform").isNotNull())
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
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/platform-v3")
        .trigger(processingTime=TRIGGER_DERIVED)
        .start()
    )
