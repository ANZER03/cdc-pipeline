"""Kafka stream readers for Nexus topics."""

from __future__ import annotations

import json
import logging
import urllib.request

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.avro.functions import from_avro
from pyspark.sql.types import StructType

from streaming.config import (
    KAFKA_BROKERS,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
    SCHEMA_REGISTRY_URL,
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
    KPI_SNAPSHOT_SCHEMA,
    REQUEST_LOG_AVRO_SCHEMA,
    SYSTEM_METRICS_AVRO_SCHEMA,
)

log = logging.getLogger("nexus.kafka_sources")


def _fetch_schema_from_registry(subject: str) -> str:
    """Fetch the latest Avro schema string for a subject from Schema Registry.

    Using the writer schema directly avoids name/namespace mismatches that cause
    spark-avro (PERMISSIVE mode) to return NULL for every record.
    """
    url = f"{SCHEMA_REGISTRY_URL}/subjects/{subject}/versions/latest"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    schema_str = data["schema"]
    log.info("Fetched Avro schema for subject %s from Schema Registry", subject)
    return schema_str


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


def _strip_schema_registry_header(column: str = "value"):
    # Confluent Avro payloads store a 5-byte wire header before the Avro bytes.
    return F.expr(f"substring({column}, 6, length({column}) - 5)")


def read_cdc_stream(
    spark: SparkSession, topic: str, avro_schema: str, timestamp_column: str
) -> DataFrame:
    raw = _read_kafka_stream(spark, topic, "latest")
    parsed = raw.select(
        from_avro(_strip_schema_registry_header(), avro_schema, _from_avro_options()).alias("data")
    )
    # In PERMISSIVE mode, failed rows have data=null. Filter them out.
    result = (
        parsed.filter(F.col("data").isNotNull())
        .select("data.*")
        .filter(F.col("__op").isin("c", "u", "r"))
    )
    # Debezium encodes TIMESTAMPTZ as ISO-8601 strings (ZonedTimestamp).
    # Use to_timestamp with explicit format (6-digit microseconds + literal Z suffix).
    # NOTE: withWatermark is intentionally NOT applied here — each consumer applies its own
    # watermark after unioning multiple streams, to avoid "Redefining watermark" errors.
    return result.withColumn(
        timestamp_column,
        F.coalesce(
            F.to_timestamp(F.col(timestamp_column), "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'"),
            F.to_timestamp(F.col(timestamp_column), "yyyy-MM-dd'T'HH:mm:ss'Z'"),
            F.to_timestamp(F.col(timestamp_column)),
        ),
    )


def read_direct_stream(
    spark: SparkSession, topic: str, avro_schema: str, timestamp_column: str
) -> DataFrame:
    raw = _read_kafka_stream(spark, topic, "latest")
    parsed = raw.select(
        from_avro(_strip_schema_registry_header(), avro_schema, _from_avro_options()).alias("data")
    )
    # NOTE: withWatermark is intentionally NOT applied here — consumers apply their own.
    return parsed.select("data.*").withColumn(
        timestamp_column,
        F.coalesce(
            F.to_timestamp(F.col(timestamp_column), "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'"),
            F.to_timestamp(F.col(timestamp_column), "yyyy-MM-dd'T'HH:mm:ss'Z'"),
            F.to_timestamp(F.col(timestamp_column)),
        ),
    )


def read_users(spark: SparkSession) -> DataFrame:
    schema = _fetch_schema_from_registry(f"{TOPIC_CDC_USERS}-value")
    return read_cdc_stream(spark, TOPIC_CDC_USERS, schema, "updated_at")


def read_products(spark: SparkSession) -> DataFrame:
    schema = _fetch_schema_from_registry(f"{TOPIC_CDC_PRODUCTS}-value")
    return read_cdc_stream(spark, TOPIC_CDC_PRODUCTS, schema, "updated_at")


def read_orders(spark: SparkSession) -> DataFrame:
    schema = _fetch_schema_from_registry(f"{TOPIC_CDC_ORDERS}-value")
    return read_cdc_stream(spark, TOPIC_CDC_ORDERS, schema, "updated_at")


def read_cart_items(spark: SparkSession) -> DataFrame:
    schema = _fetch_schema_from_registry(f"{TOPIC_CDC_CART_ITEMS}-value")
    return read_cdc_stream(spark, TOPIC_CDC_CART_ITEMS, schema, "added_at")


def read_user_events(spark: SparkSession) -> DataFrame:
    schema = _fetch_schema_from_registry(f"{TOPIC_CDC_USER_EVENTS}-value")
    return read_cdc_stream(spark, TOPIC_CDC_USER_EVENTS, schema, "created_at")


def read_sessions(spark: SparkSession) -> DataFrame:
    schema = _fetch_schema_from_registry(f"{TOPIC_CDC_SESSIONS}-value")
    return read_cdc_stream(spark, TOPIC_CDC_SESSIONS, schema, "started_at")


def read_request_log(spark: SparkSession) -> DataFrame:
    return read_direct_stream(spark, TOPIC_RAW_REQUEST_LOG, REQUEST_LOG_AVRO_SCHEMA, "created_at")


def read_system_metrics(spark: SparkSession) -> DataFrame:
    return read_direct_stream(
        spark, TOPIC_RAW_SYSTEM_METRICS, SYSTEM_METRICS_AVRO_SCHEMA, "recorded_at"
    )


def read_aggregated_kpis(spark: SparkSession) -> DataFrame:
    return _read_json_stream(spark, TOPIC_AGGREGATED_KPIS, KPI_SNAPSHOT_SCHEMA)


def _read_json_stream(spark: SparkSession, topic: str, schema: StructType) -> DataFrame:
    raw = _read_kafka_stream(spark, topic, "latest")
    return raw.select(F.from_json(F.col("value").cast("string"), schema).alias("data")).select(
        "data.*"
    )


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
