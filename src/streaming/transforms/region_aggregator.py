"""Region and flow aggregation for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import (
    CHECKPOINT_BASE,
    REGION_SLIDE_INTERVAL,
    REGION_WINDOW_DURATION,
    TRIGGER_TRANSACTIONS,
)


def build_region_snapshot(orders_df: DataFrame, request_log_df: DataFrame) -> DataFrame:
    order_events = orders_df.filter(F.col("status") == "completed").select(
        F.col("updated_at").alias("event_time"),
        F.coalesce(F.col("region_name"), F.lit("Unknown")).alias("region_name"),
        F.col("total_amount").cast("double").alias("sales"),
        F.lit(0).alias("request_count"),
    )
    request_events = request_log_df.select(
        F.col("created_at").alias("event_time"),
        F.coalesce(F.col("region_name"), F.lit("Unknown")).alias("region_name"),
        F.lit(0.0).alias("sales"),
        F.lit(1).alias("request_count"),
    )

    return (
        order_events.unionByName(request_events)
        .withWatermark("event_time", "10 minutes")
        .groupBy(
            F.window("event_time", REGION_WINDOW_DURATION, REGION_SLIDE_INTERVAL), "region_name"
        )
        .agg(
            F.sum("sales").alias("sales"),
            F.sum("request_count").alias("request_count"),
        )
        .select(
            "window",
            "region_name",
            "sales",
            F.least(F.col("request_count") * F.lit(5.0), F.lit(100.0)).alias("intensity"),
        )
    )


def build_flow_snapshot(orders_df: DataFrame, products_df: DataFrame) -> DataFrame:
    del products_df
    return orders_df.filter(F.col("status") == "completed").select(
        F.concat(F.lit("flow_"), F.col("id").cast("string")).alias("id"),
        F.col("region_name").alias("source_region"),
        F.col("region_name").alias("target_region"),
        F.lit(100.0).alias("value"),
    )


def start_region_aggregator(
    orders_df: DataFrame, request_log_df: DataFrame, products_df: DataFrame
) -> tuple[StreamingQuery, StreamingQuery]:
    regions = build_region_snapshot(orders_df, request_log_df)
    flows = build_flow_snapshot(orders_df, products_df)
    region_query = (
        regions.writeStream.outputMode("complete")
        .format("memory")
        .queryName("nexus_region_aggregator")
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/regions")
        .trigger(processingTime=TRIGGER_TRANSACTIONS)
        .start()
    )
    flow_query = (
        flows.writeStream.outputMode("append")
        .format("memory")
        .queryName("nexus_flow_aggregator")
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/flows")
        .trigger(processingTime=TRIGGER_TRANSACTIONS)
        .start()
    )
    return region_query, flow_query
