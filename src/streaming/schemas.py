"""
schemas.py
EBAP Streaming — Spark StructType schema definitions.

Defines the schemas for:
  - ebap.events.raw Kafka value (EVENT_SCHEMA)
  - Debezium CDC envelope on ebap.cdc.users (CDC_PAYLOAD_SCHEMA, CDC_ENVELOPE_SCHEMA)
"""

from pyspark.sql.types import (
    StructType, StructField,
    StringType, DoubleType, LongType, MapType, TimestampType, IntegerType
)

# Schema for ebap.events.raw Kafka value
# {"id":"...", "user_id":"...", "action":"purchase", "metadata":{...}, "location":"...", "timestamp":"..."}
EVENT_SCHEMA = StructType([
    StructField("id",        StringType(),            nullable=False),
    StructField("user_id",   StringType(),            nullable=False),
    StructField("action",    StringType(),            nullable=False),
    StructField("metadata",  MapType(StringType(), StringType()), nullable=True),
    StructField("location",  StringType(),            nullable=True),
    StructField("timestamp", StringType(),            nullable=False),
])

# Schema for the Debezium CDC envelope on ebap.cdc.users
# Debezium wraps payload in {"schema":{...}, "payload":{"before":{...}, "after":{...}, "op":"..."}}
CDC_PAYLOAD_SCHEMA = StructType([
    StructField("op",   StringType(), nullable=True),
    StructField("after", StructType([
        StructField("id",           IntegerType(), nullable=True),
        StructField("user_id",      StringType(),  nullable=True),
        StructField("name",         StringType(),  nullable=True),
        StructField("email",        StringType(),  nullable=True),
        StructField("plan",         StringType(),  nullable=True),
        StructField("region",       StringType(),  nullable=True),
        StructField("signup_ts",    StringType(),  nullable=True),
    ]), nullable=True),
])

CDC_ENVELOPE_SCHEMA = StructType([
    StructField("payload", CDC_PAYLOAD_SCHEMA, nullable=True),
])
