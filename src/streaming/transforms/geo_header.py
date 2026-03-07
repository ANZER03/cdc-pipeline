"""Geo header aggregation query for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import (
    CHANNEL_GEO,
    CHECKPOINT_BASE,
    GEO_SLIDE_INTERVAL,
    GEO_WINDOW_DURATION,
    REDIS_KEY_GEO_HEADER,
    TRIGGER_INFRASTRUCTURE,
)
from streaming.redis_client import NexusRedisWriter


def write_geo_batch(batch_df: DataFrame, batch_id: int) -> None:
    del batch_id
    rows = batch_df.orderBy(F.col("updatedAt").desc()).limit(1).collect()
    if not rows:
        return

    payload = rows[0].asDict(recursive=True)
    NexusRedisWriter().write_hash(REDIS_KEY_GEO_HEADER, payload, channel=CHANNEL_GEO)


def build_geo_header(system_metrics_df: DataFrame, request_log_df: DataFrame) -> DataFrame:
    del system_metrics_df
    request_counts = request_log_df.groupBy(
        F.window("created_at", GEO_WINDOW_DURATION, GEO_SLIDE_INTERVAL)
    ).agg(F.count("*").alias("request_count"))
    return request_counts.select(
        F.lit(99.999).alias("uptime"),
        F.concat(
            F.format_number(F.coalesce(F.col("request_count"), F.lit(0)) / 1000.0, 1),
            F.lit(" TB/S"),
        ).alias("globalLoad"),
        F.coalesce(F.col("request_count"), F.lit(0)).cast("long").alias("globalLoadBytes"),
        F.lit("V4-Orbit").alias("engineVersion"),
        F.lit("Secure").alias("protocolStatus"),
        (F.col("window.end").cast("double") * 1000).cast("long").alias("updatedAt"),
    )


def start_geo_header_aggregator(
    system_metrics_df: DataFrame, request_log_df: DataFrame
) -> StreamingQuery:
    frame = build_geo_header(system_metrics_df, request_log_df)
    return (
        frame.writeStream.outputMode("complete")
        .foreachBatch(write_geo_batch)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/geo")
        .trigger(processingTime=TRIGGER_INFRASTRUCTURE)
        .start()
    )
