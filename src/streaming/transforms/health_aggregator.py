"""Health aggregation query for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import (
    CHANNEL_HEALTH,
    CHECKPOINT_BASE,
    HEALTH_SLIDE_INTERVAL,
    HEALTH_WINDOW_DURATION,
    REDIS_KEY_HEALTH_CURRENT,
    TRIGGER_INFRASTRUCTURE,
)
from streaming.redis_client import NexusRedisWriter


def write_health_batch(batch_df: DataFrame, batch_id: int) -> None:
    del batch_id
    rows = batch_df.orderBy(F.col("updatedAt").desc()).limit(1).collect()
    if not rows:
        return

    payload = rows[0].asDict(recursive=True)
    NexusRedisWriter().write_hash(REDIS_KEY_HEALTH_CURRENT, payload, channel=CHANNEL_HEALTH)


def build_health_frame(system_metrics_df: DataFrame) -> DataFrame:
    windowed = system_metrics_df.groupBy(
        F.window("recorded_at", HEALTH_WINDOW_DURATION, HEALTH_SLIDE_INTERVAL)
    ).agg(
        F.avg(F.when(F.col("metric_name") == "cpu_percent", F.col("metric_value"))).alias("cpu"),
        F.avg(F.when(F.col("metric_name") == "memory_percent", F.col("metric_value"))).alias(
            "memory"
        ),
        F.approx_count_distinct("node_name").alias("total_nodes"),
    )
    return windowed.select(
        F.coalesce(F.col("cpu"), F.lit(0.0)).alias("cpu"),
        F.coalesce(F.col("memory"), F.lit(0.0)).alias("memory"),
        F.when(F.col("total_nodes") > 0, F.lit(100.0))
        .otherwise(F.lit(0.0))
        .alias("apiClusterScore"),
        F.when(F.col("total_nodes") > 0, F.lit("HEALTHY"))
        .otherwise(F.lit("DOWN"))
        .alias("apiClusterStatus"),
        (F.col("window.end").cast("double") * 1000).cast("long").alias("updatedAt"),
    )


def start_health_aggregator(system_metrics_df: DataFrame) -> StreamingQuery:
    frame = build_health_frame(system_metrics_df)
    return (
        frame.writeStream.outputMode("complete")
        .foreachBatch(write_health_batch)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/health")
        .trigger(processingTime=TRIGGER_INFRASTRUCTURE)
        .start()
    )
