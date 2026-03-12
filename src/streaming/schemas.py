"""StructType and Avro reference schemas for Nexus Kafka topics."""

from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)


CDC_METADATA_FIELDS = [
    StructField("__op", StringType(), True),
    StructField("__table", StringType(), True),
    StructField("__source_ts_ms", LongType(), True),
    StructField("__deleted", StringType(), True),
]


USERS_SCHEMA = StructType(
    [
        StructField("id", LongType(), False),
        StructField("username", StringType(), False),
        StructField("display_name", StringType(), False),
        StructField("email", StringType(), False),
        StructField("country_code", StringType(), True),
        StructField("city", StringType(), True),
        StructField("region_name", StringType(), True),
        StructField("platform", StringType(), True),
        StructField("created_at", TimestampType(), True),
        StructField("updated_at", TimestampType(), True),
        *CDC_METADATA_FIELDS,
    ]
)

PRODUCTS_SCHEMA = StructType(
    [
        StructField("id", LongType(), False),
        StructField("name", StringType(), False),
        StructField("category", StringType(), True),
        StructField("price", DoubleType(), False),
        StructField("merchant_region", StringType(), True),
        StructField("created_at", TimestampType(), True),
        StructField("updated_at", TimestampType(), True),
        *CDC_METADATA_FIELDS,
    ]
)

ORDERS_SCHEMA = StructType(
    [
        StructField("id", LongType(), False),
        StructField("user_id", LongType(), True),
        StructField("total_amount", DoubleType(), False),
        StructField("currency", StringType(), True),
        StructField("status", StringType(), False),
        StructField("region_name", StringType(), True),
        StructField("user_display_name", StringType(), True),
        StructField("platform", StringType(), True),
        StructField("created_at", TimestampType(), True),
        StructField("updated_at", TimestampType(), True),
        *CDC_METADATA_FIELDS,
    ]
)

ORDER_ITEMS_SCHEMA = StructType(
    [
        StructField("id", LongType(), False),
        StructField("order_id", LongType(), True),
        StructField("product_id", LongType(), True),
        StructField("quantity", IntegerType(), False),
        StructField("unit_price", DoubleType(), False),
        StructField("created_at", TimestampType(), True),
        *CDC_METADATA_FIELDS,
    ]
)

CART_ITEMS_SCHEMA = StructType(
    [
        StructField("id", LongType(), False),
        StructField("user_id", LongType(), True),
        StructField("product_id", LongType(), True),
        StructField("quantity", IntegerType(), False),
        StructField("added_at", TimestampType(), True),
        StructField("removed_at", TimestampType(), True),
        *CDC_METADATA_FIELDS,
    ]
)

USER_EVENTS_SCHEMA = StructType(
    [
        StructField("id", LongType(), False),
        StructField("user_id", LongType(), True),
        StructField("event_type", StringType(), False),
        StructField("page_url", StringType(), True),
        StructField("referrer_url", StringType(), True),
        StructField("user_agent", StringType(), True),
        StructField("ip_address", StringType(), True),
        StructField("session_id", StringType(), True),
        StructField("metadata", StringType(), True),
        StructField("user_display_name", StringType(), True),
        StructField("region_name", StringType(), True),
        StructField("city", StringType(), True),
        StructField("country_code", StringType(), True),
        StructField("platform", StringType(), True),
        StructField("amount", DoubleType(), True),
        StructField("created_at", TimestampType(), True),
        *CDC_METADATA_FIELDS,
    ]
)

SESSIONS_SCHEMA = StructType(
    [
        StructField("id", StringType(), False),
        StructField("user_id", LongType(), True),
        StructField("started_at", TimestampType(), False),
        StructField("ended_at", TimestampType(), True),
        StructField("platform", StringType(), True),
        StructField("country_code", StringType(), True),
        StructField("city", StringType(), True),
        StructField("region_name", StringType(), True),
        StructField("is_active", BooleanType(), True),
        StructField("created_at", TimestampType(), True),
        *CDC_METADATA_FIELDS,
    ]
)

REQUEST_LOG_SCHEMA = StructType(
    [
        StructField("id", LongType(), False),
        StructField("endpoint", StringType(), True),
        StructField("method", StringType(), True),
        StructField("status_code", IntegerType(), False),
        StructField("latency_ms", IntegerType(), False),
        StructField("user_id", LongType(), True),
        StructField("session_id", StringType(), True),
        StructField("region_name", StringType(), True),
        StructField("user_display_name", StringType(), True),
        StructField("platform", StringType(), True),
        StructField("created_at", TimestampType(), False),
    ]
)

SYSTEM_METRICS_SCHEMA = StructType(
    [
        StructField("id", LongType(), False),
        StructField("node_name", StringType(), False),
        StructField("metric_name", StringType(), False),
        StructField("metric_value", DoubleType(), False),
        StructField("recorded_at", TimestampType(), False),
    ]
)

KPI_SNAPSHOT_SCHEMA = StructType(
    [
        StructField("activeUsers", LongType(), False),
        StructField("activeUsersTrend", DoubleType(), False),
        StructField("revenue", DoubleType(), False),
        StructField("revenueTrend", DoubleType(), False),
        StructField("orders", LongType(), False),
        StructField("ordersTrend", DoubleType(), False),
        StructField("errorRate", DoubleType(), False),
        StructField("errorRateTrend", DoubleType(), False),
        StructField("latency", LongType(), False),
        StructField("latencyTrend", DoubleType(), False),
        StructField("updatedAt", LongType(), False),
    ]
)


# Avro reader schemas — field ordering and union ordering MUST match what Debezium registers
# in Schema Registry (writer schema). Specifically:
#   - Timestamp fields use string-first unions: [{"type":"string"}, "null"] with a string default
#   - is_active uses boolean-first union: [{"type":"boolean"}, "null"]
#   - orders.currency uses string-first union with "USD" default
#   - id fields carry connect.default (harmless extra attr ignored by spark-avro reader)
# Mismatch in union ordering causes spark-avro (PERMISSIVE) to return NULL for the entire record.

USERS_AVRO_SCHEMA = """{"type":"record","name":"UsersCdc","fields":[{"name":"id","type":{"type":"long","connect.default":0},"default":0},{"name":"username","type":"string"},{"name":"display_name","type":"string"},{"name":"email","type":"string"},{"name":"country_code","type":["null","string"],"default":null},{"name":"city","type":["null","string"],"default":null},{"name":"region_name","type":["null","string"],"default":null},{"name":"platform","type":["null","string"],"default":null},{"name":"created_at","type":[{"type":"string","connect.version":1,"connect.default":"1970-01-01T00:00:00.000000Z","connect.name":"io.debezium.time.ZonedTimestamp"},"null"],"default":"1970-01-01T00:00:00.000000Z"},{"name":"updated_at","type":[{"type":"string","connect.version":1,"connect.default":"1970-01-01T00:00:00.000000Z","connect.name":"io.debezium.time.ZonedTimestamp"},"null"],"default":"1970-01-01T00:00:00.000000Z"},{"name":"__op","type":["null","string"],"default":null},{"name":"__table","type":["null","string"],"default":null},{"name":"__source_ts_ms","type":["null","long"],"default":null},{"name":"__deleted","type":["null","string"],"default":null}]}"""
PRODUCTS_AVRO_SCHEMA = """{"type":"record","name":"ProductsCdc","fields":[{"name":"id","type":{"type":"long","connect.default":0},"default":0},{"name":"name","type":"string"},{"name":"category","type":["null","string"],"default":null},{"name":"price","type":"double"},{"name":"merchant_region","type":["null","string"],"default":null},{"name":"created_at","type":[{"type":"string","connect.version":1,"connect.default":"1970-01-01T00:00:00.000000Z","connect.name":"io.debezium.time.ZonedTimestamp"},"null"],"default":"1970-01-01T00:00:00.000000Z"},{"name":"updated_at","type":[{"type":"string","connect.version":1,"connect.default":"1970-01-01T00:00:00.000000Z","connect.name":"io.debezium.time.ZonedTimestamp"},"null"],"default":"1970-01-01T00:00:00.000000Z"},{"name":"__op","type":["null","string"],"default":null},{"name":"__table","type":["null","string"],"default":null},{"name":"__source_ts_ms","type":["null","long"],"default":null},{"name":"__deleted","type":["null","string"],"default":null}]}"""
ORDERS_AVRO_SCHEMA = """{"type":"record","name":"OrdersCdc","fields":[{"name":"id","type":{"type":"long","connect.default":0},"default":0},{"name":"user_id","type":["null","long"],"default":null},{"name":"total_amount","type":"double"},{"name":"currency","type":[{"type":"string","connect.default":"USD"},"null"],"default":"USD"},{"name":"status","type":"string"},{"name":"region_name","type":["null","string"],"default":null},{"name":"user_display_name","type":["null","string"],"default":null},{"name":"platform","type":["null","string"],"default":null},{"name":"created_at","type":[{"type":"string","connect.version":1,"connect.default":"1970-01-01T00:00:00.000000Z","connect.name":"io.debezium.time.ZonedTimestamp"},"null"],"default":"1970-01-01T00:00:00.000000Z"},{"name":"updated_at","type":[{"type":"string","connect.version":1,"connect.default":"1970-01-01T00:00:00.000000Z","connect.name":"io.debezium.time.ZonedTimestamp"},"null"],"default":"1970-01-01T00:00:00.000000Z"},{"name":"__op","type":["null","string"],"default":null},{"name":"__table","type":["null","string"],"default":null},{"name":"__source_ts_ms","type":["null","long"],"default":null},{"name":"__deleted","type":["null","string"],"default":null}]}"""
ORDER_ITEMS_AVRO_SCHEMA = """{"type":"record","name":"OrderItemsCdc","fields":[{"name":"id","type":{"type":"long","connect.default":0},"default":0},{"name":"order_id","type":["null","long"],"default":null},{"name":"product_id","type":["null","long"],"default":null},{"name":"quantity","type":{"type":"int","connect.default":1},"default":1},{"name":"unit_price","type":"double"},{"name":"created_at","type":[{"type":"string","connect.version":1,"connect.default":"1970-01-01T00:00:00.000000Z","connect.name":"io.debezium.time.ZonedTimestamp"},"null"],"default":"1970-01-01T00:00:00.000000Z"},{"name":"__op","type":["null","string"],"default":null},{"name":"__table","type":["null","string"],"default":null},{"name":"__source_ts_ms","type":["null","long"],"default":null},{"name":"__deleted","type":["null","string"],"default":null}]}"""
CART_ITEMS_AVRO_SCHEMA = """{"type":"record","name":"CartItemsCdc","fields":[{"name":"id","type":{"type":"long","connect.default":0},"default":0},{"name":"user_id","type":["null","long"],"default":null},{"name":"product_id","type":["null","long"],"default":null},{"name":"quantity","type":{"type":"int","connect.default":1},"default":1},{"name":"added_at","type":[{"type":"string","connect.version":1,"connect.default":"1970-01-01T00:00:00.000000Z","connect.name":"io.debezium.time.ZonedTimestamp"},"null"],"default":"1970-01-01T00:00:00.000000Z"},{"name":"removed_at","type":["null",{"type":"string","connect.version":1,"connect.name":"io.debezium.time.ZonedTimestamp"}],"default":null},{"name":"__op","type":["null","string"],"default":null},{"name":"__table","type":["null","string"],"default":null},{"name":"__source_ts_ms","type":["null","long"],"default":null},{"name":"__deleted","type":["null","string"],"default":null}]}"""
USER_EVENTS_AVRO_SCHEMA = """{"type":"record","name":"UserEventsCdc","fields":[{"name":"id","type":{"type":"long","connect.default":0},"default":0},{"name":"user_id","type":["null","long"],"default":null},{"name":"event_type","type":"string"},{"name":"page_url","type":["null","string"],"default":null},{"name":"referrer_url","type":["null","string"],"default":null},{"name":"user_agent","type":["null","string"],"default":null},{"name":"ip_address","type":["null","string"],"default":null},{"name":"session_id","type":["null",{"type":"string","connect.version":1,"connect.name":"io.debezium.data.Uuid"}],"default":null},{"name":"metadata","type":["null",{"type":"string","connect.version":1,"connect.name":"io.debezium.data.Json"}],"default":null},{"name":"user_display_name","type":["null","string"],"default":null},{"name":"region_name","type":["null","string"],"default":null},{"name":"city","type":["null","string"],"default":null},{"name":"country_code","type":["null","string"],"default":null},{"name":"platform","type":["null","string"],"default":null},{"name":"amount","type":["null","double"],"default":null},{"name":"created_at","type":[{"type":"string","connect.version":1,"connect.default":"1970-01-01T00:00:00.000000Z","connect.name":"io.debezium.time.ZonedTimestamp"},"null"],"default":"1970-01-01T00:00:00.000000Z"},{"name":"__op","type":["null","string"],"default":null},{"name":"__table","type":["null","string"],"default":null},{"name":"__source_ts_ms","type":["null","long"],"default":null},{"name":"__deleted","type":["null","string"],"default":null}]}"""
SESSIONS_AVRO_SCHEMA = """{"type":"record","name":"SessionsCdc","fields":[{"name":"id","type":{"type":"string","connect.version":1,"connect.default":"00000000-0000-0000-0000-000000000000","connect.name":"io.debezium.data.Uuid"},"default":"00000000-0000-0000-0000-000000000000"},{"name":"user_id","type":["null","long"],"default":null},{"name":"started_at","type":{"type":"string","connect.version":1,"connect.name":"io.debezium.time.ZonedTimestamp"}},{"name":"ended_at","type":["null",{"type":"string","connect.version":1,"connect.name":"io.debezium.time.ZonedTimestamp"}],"default":null},{"name":"platform","type":["null","string"],"default":null},{"name":"country_code","type":["null","string"],"default":null},{"name":"city","type":["null","string"],"default":null},{"name":"region_name","type":["null","string"],"default":null},{"name":"is_active","type":[{"type":"boolean","connect.default":true},"null"],"default":true},{"name":"created_at","type":[{"type":"string","connect.version":1,"connect.default":"1970-01-01T00:00:00.000000Z","connect.name":"io.debezium.time.ZonedTimestamp"},"null"],"default":"1970-01-01T00:00:00.000000Z"},{"name":"__op","type":["null","string"],"default":null},{"name":"__table","type":["null","string"],"default":null},{"name":"__source_ts_ms","type":["null","long"],"default":null},{"name":"__deleted","type":["null","string"],"default":null}]}"""
REQUEST_LOG_AVRO_SCHEMA = """{"type":"record","name":"RequestLog","fields":[{"name":"id","type":"long"},{"name":"endpoint","type":["null","string"],"default":null},{"name":"method","type":["null","string"],"default":null},{"name":"status_code","type":"int"},{"name":"latency_ms","type":"int"},{"name":"user_id","type":["null","long"],"default":null},{"name":"session_id","type":["null","string"],"default":null},{"name":"region_name","type":["null","string"],"default":null},{"name":"user_display_name","type":["null","string"],"default":null},{"name":"platform","type":["null","string"],"default":null},{"name":"created_at","type":{"type":"long","logicalType":"timestamp-millis"}}]}"""
SYSTEM_METRICS_AVRO_SCHEMA = """{"type":"record","name":"SystemMetric","fields":[{"name":"id","type":"long"},{"name":"node_name","type":"string"},{"name":"metric_name","type":"string"},{"name":"metric_value","type":"double"},{"name":"recorded_at","type":{"type":"long","logicalType":"timestamp-millis"}}]}"""
