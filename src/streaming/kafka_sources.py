"""
kafka_sources.py
EBAP Streaming — Kafka source stream readers.

Provides two streaming DataFrame readers:
  - read_events_stream: raw user events from ebap.events.raw
  - read_cdc_users_stream: CDC user profile changes from ebap.cdc.users
"""

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType

from config import KAFKA_BROKERS, TOPIC_EVENTS_RAW, TOPIC_CDC_USERS
from schemas import EVENT_SCHEMA, CDC_ENVELOPE_SCHEMA


def read_events_stream(spark: SparkSession) -> DataFrame:
    """
    Read raw user events from ebap.events.raw.
    Returns a parsed DataFrame with typed columns + event_ts (TimestampType).
    """
    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKERS)
        .option("subscribe", TOPIC_EVENTS_RAW)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )

    parsed = (
        raw
        .select(F.col("value").cast("string").alias("raw_json"))
        .select(F.from_json(F.col("raw_json"), EVENT_SCHEMA).alias("e"))
        .select(
            F.col("e.id").alias("event_id"),
            F.col("e.user_id"),
            F.col("e.action"),
            F.col("e.metadata"),
            F.col("e.location"),
            # Parse ISO-8601 timestamp string → TimestampType
            F.to_timestamp(F.col("e.timestamp")).alias("event_ts"),
        )
        # Extract common metadata fields
        .withColumn("amount",  F.col("metadata").getItem("amount").cast(DoubleType()))
        .withColumn("item_id", F.col("metadata").getItem("item_id"))
        .drop("metadata")
        # Filter out nulls from malformed messages
        .filter(F.col("event_id").isNotNull() & F.col("user_id").isNotNull())
        # Watermark — tolerate up to 10 minutes of late data
        .withWatermark("event_ts", "10 minutes")
    )
    return parsed


def read_cdc_users_stream(spark: SparkSession) -> DataFrame:
    """
    Read CDC user profile changes from ebap.cdc.users.
    Extracts the 'after' image (current row state) from the Debezium envelope.
    Returns user profile fields keyed on user_id.
    """
    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKERS)
        .option("subscribe", TOPIC_CDC_USERS)
        .option("startingOffsets", "earliest")   # bootstrap full snapshot
        .option("failOnDataLoss", "false")
        .load()
    )

    parsed = (
        raw
        .select(F.col("value").cast("string").alias("raw_json"))
        .select(F.from_json(F.col("raw_json"), CDC_ENVELOPE_SCHEMA).alias("cdc"))
        .select(
            F.col("cdc.payload.after.user_id").alias("user_id"),
            F.col("cdc.payload.after.name").alias("user_name"),
            F.col("cdc.payload.after.plan").alias("plan"),
            F.col("cdc.payload.after.region").alias("region"),
            F.col("cdc.payload.op").alias("cdc_op"),
        )
        # Only keep inserts (op=r snapshot, op=c create, op=u update) — ignore deletes
        .filter(F.col("cdc_op").isin("r", "c", "u"))
        .filter(F.col("user_id").isNotNull())
        # Use current_timestamp as a proxy event time for watermark on CDC stream
        .withColumn("cdc_ts", F.current_timestamp())
        .withWatermark("cdc_ts", "10 minutes")
    )
    return parsed
