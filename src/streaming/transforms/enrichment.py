"""
transforms/enrichment.py
EBAP Streaming — Stream-stream join: enrich events with user profiles.

Pure DataFrame transformation — no config dependencies, no side effects.
Ideal for unit testing with mock DataFrames.
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def enrich_events(events_df: DataFrame, users_df: DataFrame) -> DataFrame:
    """
    Stream-stream join: enrich events with the latest user profile.
    Uses inner join (required for stream-stream without range condition).
    Events without a matching CDC user record will be dropped — acceptable since
    Debezium snapshots all existing users at startup (op=r) before live changes.
    """
    enriched = (
        events_df.alias("ev")
        .join(
            users_df.alias("u"),
            on=F.col("ev.user_id") == F.col("u.user_id"),
            how="inner"
        )
        .select(
            F.col("ev.event_id"),
            # PII: hash user_id with SHA-256 before writing to cold storage (FR-GDPR)
            F.sha2(F.col("ev.user_id"), 256).alias("user_id_hashed"),
            F.col("ev.action"),
            F.col("ev.amount"),
            F.col("ev.item_id"),
            F.col("ev.location"),
            F.coalesce(F.col("u.region"), F.lit("unknown")).alias("region"),
            F.coalesce(F.col("u.plan"),   F.lit("unknown")).alias("plan"),
            F.col("ev.event_ts"),
            F.current_timestamp().alias("ingest_ts"),
        )
    )
    return enriched
