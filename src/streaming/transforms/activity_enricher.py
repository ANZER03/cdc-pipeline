"""Activity enrichment query for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import (
    CHANNEL_ACTIVITY,
    CHECKPOINT_BASE,
    REDIS_KEY_ACTIVITY_FEED,
    TRIGGER_TRANSACTIONS,
)
from streaming.redis_client import NexusRedisWriter


def write_activity_batch(batch_df: DataFrame, batch_id: int) -> None:
    del batch_id
    rows = batch_df.orderBy(F.col("timestamp").desc()).limit(15).collect()
    if not rows:
        return

    writer = NexusRedisWriter()
    for row in reversed(rows):
        payload = row.asDict(recursive=True)
        writer.push_to_list(REDIS_KEY_ACTIVITY_FEED, payload, max_len=15, channel=CHANNEL_ACTIVITY)


def build_activity_feed(
    user_events_df: DataFrame, users_df: DataFrame, orders_df: DataFrame
) -> DataFrame:
    del users_df
    del orders_df

    mapped = user_events_df.withColumn(
        "action",
        F.when(F.col("endpoint").contains("checkout"), F.lit("purchase"))
        .when(F.col("endpoint").contains("cart"), F.lit("cart"))
        .when(F.col("endpoint").contains("auth"), F.lit("login"))
        .otherwise(F.lit("view")),
    )

    return (
        mapped
        .select(
            F.concat(F.lit("evt_"), F.col("id").cast("string")).alias("id"),
            F.concat(F.lit("User "), F.coalesce(F.col("user_id").cast("string"), F.lit("0"))).alias(
                "user"
            ),
            F.col("action"),
            F.when(F.col("action") == "purchase", F.lit(149.99))
            .otherwise(F.lit(None))
            .alias("amount"),
            F.date_format(F.col("created_at"), "yyyy-MM-dd'T'HH:mm:ss.SSSXXX").alias("timestamp"),
            F.concat_ws(", ", F.coalesce(F.col("region_name"), F.lit("Unknown")), F.lit("--")).alias(
                "location"
            ),
        )
    )


def start_activity_enricher(
    user_events_df: DataFrame, users_df: DataFrame, orders_df: DataFrame
) -> StreamingQuery:
    frame = build_activity_feed(user_events_df, users_df, orders_df)
    return (
        frame.writeStream.outputMode("append")
        .foreachBatch(write_activity_batch)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/activity")
        .trigger(processingTime=TRIGGER_TRANSACTIONS)
        .start()
    )
