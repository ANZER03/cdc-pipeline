"""Health aggregation query for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import (
    CHECKPOINT_BASE,
    HEALTH_SLIDE_INTERVAL,
    HEALTH_WINDOW_DURATION,
    TRIGGER_INFRASTRUCTURE,
)


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
        .format("memory")
        .queryName("nexus_health_aggregator")
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/health")
        .trigger(processingTime=TRIGGER_INFRASTRUCTURE)
        .start()
    )
