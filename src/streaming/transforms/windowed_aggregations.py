"""
transforms/windowed_aggregations.py
EBAP Streaming — Tumbling-window aggregation DataFrames.

Pure DataFrame transformation — no config dependencies, no side effects.
Operates on the raw events stream (no user-profile join required for KPIs).
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def build_windowed_metrics(events_df: DataFrame) -> dict:
    """
    Build 3 tumbling-window aggregation DataFrames from the raw events stream.
    Groups by action and location (available without the user-profile join).
    Uses 'location' aliased as 'region' for compatibility with Redis/Iceberg sinks.

    Returns a dict keyed by window label: '1m', '5m', '1h'.
    """
    windows = {}
    for label, duration in [("1m", "1 minute"), ("5m", "5 minutes"), ("1h", "1 hour")]:
        windows[label] = (
            events_df
            .groupBy(
                F.window(F.col("event_ts"), duration).alias("w"),
                F.coalesce(F.col("location"), F.lit("unknown")).alias("region"),
                F.col("action"),
            )
            .agg(
                F.count("*").alias("event_count"),
                F.sum(F.coalesce(F.col("amount"), F.lit(0.0))).alias("total_amount"),
            )
            .select(
                F.col("w.start").alias("window_start"),
                F.col("w.end").alias("window_end"),
                F.lit(label).alias("window_duration"),
                F.col("region"),
                F.col("action"),
                F.col("event_count"),
                F.col("total_amount"),
                F.current_timestamp().alias("ingest_ts"),
            )
        )
    return windows
