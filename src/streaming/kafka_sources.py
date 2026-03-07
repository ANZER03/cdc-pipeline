"""Kafka stream readers for Nexus topics."""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.avro.functions import from_avro

from streaming.config import (
    KAFKA_BROKERS,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
    TOPIC_AGGREGATED_KPIS,
    TOPIC_CDC_CART_ITEMS,
    TOPIC_CDC_ORDERS,
    TOPIC_CDC_PRODUCTS,
    TOPIC_CDC_SESSIONS,
    TOPIC_CDC_USER_EVENTS,
    TOPIC_CDC_USERS,
    TOPIC_RAW_REQUEST_LOG,
    TOPIC_RAW_SYSTEM_METRICS,
)
from streaming.schemas import (
    CART_ITEMS_AVRO_SCHEMA,
    ORDERS_AVRO_SCHEMA,
    PRODUCTS_AVRO_SCHEMA,
    REQUEST_LOG_AVRO_SCHEMA,
    SESSIONS_AVRO_SCHEMA,
    SYSTEM_METRICS_AVRO_SCHEMA,
    USER_EVENTS_AVRO_SCHEMA,
    USERS_AVRO_SCHEMA,
)


def _read_kafka_stream(spark: SparkSession, topic: str, starting_offsets: str) -> DataFrame:
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKERS)
        .option("subscribe", topic)
        .option("startingOffsets", starting_offsets)
        .option("failOnDataLoss", "false")
        .load()
    )


def _from_avro_options() -> dict[str, str]:
    return {"mode": "PERMISSIVE"}


def read_cdc_stream(
    spark: SparkSession, topic: str, avro_schema: str, timestamp_column: str
) -> DataFrame:
    raw = _read_kafka_stream(spark, topic, "earliest")
    parsed = raw.select(from_avro(F.col("value"), avro_schema, _from_avro_options()).alias("data"))
    result = parsed.select("data.*").filter(F.col("__op").isin("c", "u", "r"))
    return result.withWatermark(timestamp_column, "10 minutes")


def read_direct_stream(
    spark: SparkSession, topic: str, avro_schema: str, timestamp_column: str
) -> DataFrame:
    raw = _read_kafka_stream(spark, topic, "latest")
    parsed = raw.select(from_avro(F.col("value"), avro_schema, _from_avro_options()).alias("data"))
    return parsed.select("data.*").withWatermark(timestamp_column, "10 minutes")


def read_users(spark: SparkSession) -> DataFrame:
    return read_cdc_stream(spark, TOPIC_CDC_USERS, USERS_AVRO_SCHEMA, "updated_at")


def read_products(spark: SparkSession) -> DataFrame:
    return read_cdc_stream(spark, TOPIC_CDC_PRODUCTS, PRODUCTS_AVRO_SCHEMA, "updated_at")


def read_orders(spark: SparkSession) -> DataFrame:
    return read_cdc_stream(spark, TOPIC_CDC_ORDERS, ORDERS_AVRO_SCHEMA, "updated_at")


def read_cart_items(spark: SparkSession) -> DataFrame:
    return read_cdc_stream(spark, TOPIC_CDC_CART_ITEMS, CART_ITEMS_AVRO_SCHEMA, "added_at")


def read_user_events(spark: SparkSession) -> DataFrame:
    return read_cdc_stream(spark, TOPIC_CDC_USER_EVENTS, USER_EVENTS_AVRO_SCHEMA, "created_at")


def read_sessions(spark: SparkSession) -> DataFrame:
    return read_cdc_stream(spark, TOPIC_CDC_SESSIONS, SESSIONS_AVRO_SCHEMA, "started_at")


def read_request_log(spark: SparkSession) -> DataFrame:
    return read_direct_stream(spark, TOPIC_RAW_REQUEST_LOG, REQUEST_LOG_AVRO_SCHEMA, "created_at")


def read_system_metrics(spark: SparkSession) -> DataFrame:
    return read_direct_stream(
        spark, TOPIC_RAW_SYSTEM_METRICS, SYSTEM_METRICS_AVRO_SCHEMA, "recorded_at"
    )


def read_aggregated_kpis(spark: SparkSession) -> DataFrame:
    return _read_kafka_stream(spark, TOPIC_AGGREGATED_KPIS, "latest")


def read_postgres_table_snapshot(spark: SparkSession, table_name: str) -> DataFrame:
    return (
        spark.read.format("jdbc")
        .option("url", f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
        .option("dbtable", table_name)
        .option("user", POSTGRES_USER)
        .option("password", POSTGRES_PASSWORD)
        .option("driver", "org.postgresql.Driver")
        .load()
    )
