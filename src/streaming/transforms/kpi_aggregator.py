"""KPI aggregation query wiring for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import (
    CHECKPOINT_BASE,
    KPI_SLIDE_INTERVAL,
    KPI_WINDOW_DURATION,
    TRIGGER_TRANSACTIONS,
)


def build_kpi_frame(
    orders_df: DataFrame, sessions_df: DataFrame, request_log_df: DataFrame
) -> DataFrame:
    order_events = orders_df.filter(F.col("status") == "completed").select(
        F.col("updated_at").alias("event_time"),
        F.lit(0).alias("active_session_count"),
        F.col("total_amount").cast("double").alias("revenue_amount"),
        F.lit(1).alias("order_count"),
        F.lit(0).alias("request_count"),
        F.lit(0).alias("error_count"),
        F.lit(None).cast("double").alias("latency_ms"),
    )
    session_events = sessions_df.filter(F.col("is_active") & F.col("ended_at").isNull()).select(
        F.col("started_at").alias("event_time"),
        F.lit(1).alias("active_session_count"),
        F.lit(0.0).alias("revenue_amount"),
        F.lit(0).alias("order_count"),
        F.lit(0).alias("request_count"),
        F.lit(0).alias("error_count"),
        F.lit(None).cast("double").alias("latency_ms"),
    )
    request_events = request_log_df.select(
        F.col("created_at").alias("event_time"),
        F.lit(0).alias("active_session_count"),
        F.lit(0.0).alias("revenue_amount"),
        F.lit(0).alias("order_count"),
        F.lit(1).alias("request_count"),
        F.when(F.col("status_code") >= 500, F.lit(1)).otherwise(F.lit(0)).alias("error_count"),
        F.col("latency_ms").cast("double").alias("latency_ms"),
    )

    combined_events = (
        order_events.unionByName(session_events)
        .unionByName(request_events)
        .withWatermark("event_time", "10 minutes")
    )

    return (
        combined_events.groupBy(F.window("event_time", KPI_WINDOW_DURATION, KPI_SLIDE_INTERVAL))
        .agg(
            F.sum("active_session_count").cast("long").alias("activeUsers"),
            F.sum("revenue_amount").alias("revenue"),
            F.sum("order_count").cast("long").alias("orders"),
            (F.sum("error_count") / F.greatest(F.sum("request_count"), F.lit(1)) * 100.0).alias(
                "errorRate"
            ),
            F.expr("percentile_approx(latency_ms, 0.5)").alias("latency"),
        )
        .select(
            F.col("window"),
            F.col("activeUsers"),
            F.lit(0.0).alias("activeUsersTrend"),
            F.col("revenue"),
            F.lit(0.0).alias("revenueTrend"),
            F.col("orders"),
            F.lit(0.0).alias("ordersTrend"),
            F.col("errorRate"),
            F.lit(0.0).alias("errorRateTrend"),
            F.coalesce(F.col("latency"), F.lit(0)).cast("long").alias("latency"),
            F.lit(0.0).alias("latencyTrend"),
            (F.col("window.end").cast("double") * 1000).cast("long").alias("updatedAt"),
        )
    )


def start_kpi_aggregator(
    orders_df: DataFrame, sessions_df: DataFrame, request_log_df: DataFrame
) -> StreamingQuery:
    frame = build_kpi_frame(orders_df, sessions_df, request_log_df)
    return (
        frame.writeStream.outputMode("update")
        .format("memory")
        .queryName("nexus_kpi_aggregator")
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/kpi")
        .trigger(processingTime=TRIGGER_TRANSACTIONS)
        .start()
    )
