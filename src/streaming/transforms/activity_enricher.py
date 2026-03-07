"""Activity enrichment query for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import CHECKPOINT_BASE, TRIGGER_TRANSACTIONS


def build_activity_feed(
    user_events_df: DataFrame, users_df: DataFrame, orders_df: DataFrame
) -> DataFrame:
    mapped = user_events_df.withColumn(
        "action",
        F.when(F.col("event_type") == "checkout_complete", F.lit("purchase"))
        .when(F.col("event_type") == "page_view", F.lit("view"))
        .when(F.col("event_type") == "add_to_cart", F.lit("cart"))
        .when(F.col("event_type") == "login", F.lit("login")),
    ).filter(F.col("action").isNotNull())

    purchased_orders = orders_df.filter(F.col("status") == "completed").select(
        F.col("user_id").alias("order_user_id"),
        F.col("total_amount").alias("amount"),
    )

    return (
        mapped.alias("events")
        .join(
            F.broadcast(users_df.alias("users")),
            F.col("events.user_id") == F.col("users.id"),
            "left",
        )
        .join(
            F.broadcast(purchased_orders.alias("orders")),
            F.col("events.user_id") == F.col("orders.order_user_id"),
            "left",
        )
        .select(
            F.concat(F.lit("evt_"), F.col("events.id").cast("string")).alias("id"),
            F.coalesce(
                F.col("users.display_name"), F.col("users.username"), F.lit("Unknown")
            ).alias("user"),
            F.col("action"),
            F.when(F.col("action") == "purchase", F.col("amount"))
            .otherwise(F.lit(None))
            .alias("amount"),
            F.date_format(F.col("events.created_at"), "yyyy-MM-dd'T'HH:mm:ss.SSSXXX").alias(
                "timestamp"
            ),
            F.concat_ws(
                ", ",
                F.coalesce(F.col("users.city"), F.lit("Unknown")),
                F.coalesce(F.col("users.country_code"), F.lit("--")),
            ).alias("location"),
        )
    )


def start_activity_enricher(
    user_events_df: DataFrame, users_df: DataFrame, orders_df: DataFrame
) -> StreamingQuery:
    frame = build_activity_feed(user_events_df, users_df, orders_df)
    return (
        frame.writeStream.outputMode("append")
        .format("memory")
        .queryName("nexus_activity_enricher")
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/activity")
        .trigger(processingTime=TRIGGER_TRANSACTIONS)
        .start()
    )
