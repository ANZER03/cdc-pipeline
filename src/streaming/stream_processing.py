"""
stream_processing.py
EBAP Phase 5 — Spark Structured Streaming Job

Architecture:
  Kafka (ebap.events.raw + ebap.cdc.users)
    → Schema enforcement (StructType)
    → Watermark (10 min late-data tolerance)
    → Stream-Stream join on user_id
    → Windowed aggregations (1m / 5m / 1h tumbling windows)
    → Alerting state machine (Normal → Pending → Firing)
    → Dual-write:
        Hot  path: Redis (SET with 24h TTL)   — real-time KPIs
        Cold path: Iceberg/MinIO (partitioned by day + region) — historical

Usage (submitted by spark-streaming-submit container):
  spark-submit --master spark://spark-master-streaming:7077 \
    --conf spark.sql.catalog.ebap=... \
    /opt/spark/jobs/stream_processing.py
"""

import json
import hashlib
import logging
from datetime import datetime, timezone

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField,
    StringType, DoubleType, LongType, MapType, TimestampType, IntegerType
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("ebap.streaming")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
KAFKA_BROKERS         = "kafka:9092"
TOPIC_EVENTS_RAW      = "ebap.events.raw"
TOPIC_CDC_USERS       = "ebap.cdc.users"
CHECKPOINT_BASE       = "s3a://ebap-checkpoints/streaming"
ICEBERG_CATALOG       = "ebap"
ICEBERG_DB            = "events_db"
ICEBERG_TABLE_EVENTS  = f"{ICEBERG_CATALOG}.{ICEBERG_DB}.enriched_events"
ICEBERG_TABLE_METRICS = f"{ICEBERG_CATALOG}.{ICEBERG_DB}.windowed_metrics"
REDIS_TTL_SECONDS     = 86400   # 24 hours

# Alerting thresholds
ALERT_ERROR_RATE_THRESHOLD = 0.05  # 5% error rate triggers Pending
ALERT_PENDING_DURATION_S   = 60    # seconds in Pending before Firing

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# SparkSession
# ---------------------------------------------------------------------------

def create_spark_session() -> SparkSession:
    """Build SparkSession with Iceberg catalog + S3A/MinIO config."""
    spark = (
        SparkSession.builder
        .appName("EBAP-Streaming")
        # Iceberg extensions
        .config("spark.sql.extensions",
                "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        # Iceberg JDBC catalog (shared with Trino via iceberg_catalog PostgreSQL DB)
        .config("spark.sql.catalog.ebap",
                "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.ebap.catalog-impl",
                "org.apache.iceberg.jdbc.JdbcCatalog")
        .config("spark.sql.catalog.ebap.uri",
                "jdbc:postgresql://postgres:5432/iceberg_catalog")
        .config("spark.sql.catalog.ebap.jdbc.user",   "admin")
        .config("spark.sql.catalog.ebap.jdbc.password", "admin")
        .config("spark.sql.catalog.ebap.warehouse",   "s3a://ebap-silver/")
        .config("spark.sql.catalog.ebap.io-impl",
                "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.sql.catalog.ebap.s3.endpoint",  "http://minio:9000")
        .config("spark.sql.catalog.ebap.s3.path-style-access", "true")
        # S3A / MinIO
        .config("spark.hadoop.fs.s3a.endpoint",        "http://minio:9000")
        .config("spark.hadoop.fs.s3a.access.key",      "admin")
        .config("spark.hadoop.fs.s3a.secret.key",      "password")
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl",
                "org.apache.hadoop.fs.s3a.S3AFileSystem")
        # Redis datasource
        .config("spark.redis.host", "redis")
        .config("spark.redis.port", "6379")
        # Reduce logging noise
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    log.info("SparkSession created — Iceberg catalog: %s", ICEBERG_CATALOG)
    return spark


# ---------------------------------------------------------------------------
# Iceberg Table Bootstrap
# ---------------------------------------------------------------------------

def bootstrap_iceberg_tables(spark: SparkSession) -> None:
    """Create Iceberg namespace + tables if they don't exist yet."""
    log.info("Bootstrapping Iceberg tables in catalog '%s'", ICEBERG_CATALOG)

    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {ICEBERG_CATALOG}.{ICEBERG_DB}")

    # enriched_events — one row per Kafka event, enriched with user profile
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {ICEBERG_TABLE_EVENTS} (
            event_id        STRING,
            user_id_hashed  STRING,
            action          STRING,
            amount          DOUBLE,
            item_id         STRING,
            location        STRING,
            region          STRING,
            plan            STRING,
            event_ts        TIMESTAMP,
            ingest_ts       TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (days(event_ts), region)
        TBLPROPERTIES (
            'write.format.default' = 'parquet',
            'write.parquet.compression-codec' = 'snappy'
        )
    """)

    # windowed_metrics — aggregated counts per window + region + action
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {ICEBERG_TABLE_METRICS} (
            window_start    TIMESTAMP,
            window_end      TIMESTAMP,
            window_duration STRING,
            region          STRING,
            action          STRING,
            event_count     LONG,
            total_amount    DOUBLE,
            ingest_ts       TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (days(window_start), region)
        TBLPROPERTIES (
            'write.format.default' = 'parquet',
            'write.parquet.compression-codec' = 'snappy'
        )
    """)

    log.info("Iceberg tables ready: %s, %s", ICEBERG_TABLE_EVENTS, ICEBERG_TABLE_METRICS)


# ---------------------------------------------------------------------------
# Kafka Source Streams
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Stream-Stream Join
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Windowed Aggregations
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Alerting State Machine
# ---------------------------------------------------------------------------

def _alert_state(error_rate: float, pending_since_epoch: float, now_epoch: float) -> str:
    """
    Pure function implementing the alerting state machine:
      Normal  → error_rate < threshold
      Pending → error_rate >= threshold, duration < ALERT_PENDING_DURATION_S
      Firing  → error_rate >= threshold, duration >= ALERT_PENDING_DURATION_S
    """
    if error_rate < ALERT_ERROR_RATE_THRESHOLD:
        return "Normal"
    elapsed = now_epoch - pending_since_epoch
    if elapsed < ALERT_PENDING_DURATION_S:
        return "Pending"
    return "Firing"


# ---------------------------------------------------------------------------
# foreachBatch: Redis hot-path writer
# ---------------------------------------------------------------------------

# Module-level dict to track alert pending timestamps (per-region)
# In a real deployment this would live in Redis or Spark state store.
_alert_pending_since: dict = {}


def write_to_redis(batch_df: DataFrame, epoch_id: int) -> None:
    """
    foreachBatch sink for the 1-minute windowed metrics → Redis.

    Redis key patterns:
      kpi:active_users                       → total event count in last 1m (all regions)
      kpi:purchase_count                     → purchase count in last 1m
      kpi:total_revenue                      → sum of purchase amounts in last 1m
      region:{region}:event_count            → event count per region (1m window)
      region:{region}:health_intensity       → 0-100 load proxy for Grafana geo-map
      alert:{region}:state                   → Normal / Pending / Firing
    """
    import redis as redis_lib

    r = redis_lib.Redis(host="redis", port=6379, decode_responses=True)
    pipe = r.pipeline()

    rows = batch_df.collect()
    now_epoch = datetime.now(timezone.utc).timestamp()

    # Aggregate totals for global KPIs
    total_events   = 0
    purchase_count = 0
    total_revenue  = 0.0

    region_stats: dict = {}

    for row in rows:
        region = row["region"] or "unknown"
        action = row["action"] or "unknown"
        count  = int(row["event_count"] or 0)
        amount = float(row["total_amount"] or 0.0)

        total_events += count
        if action == "purchase":
            purchase_count += count
            total_revenue  += amount

        if region not in region_stats:
            region_stats[region] = {"event_count": 0, "revenue": 0.0, "errors": 0}
        region_stats[region]["event_count"] += count
        if action in ("error", "checkout_fail"):
            region_stats[region]["errors"] += count

    # Global KPIs
    pipe.set("kpi:active_users",    total_events,    ex=REDIS_TTL_SECONDS)
    pipe.set("kpi:purchase_count",  purchase_count,  ex=REDIS_TTL_SECONDS)
    pipe.set("kpi:total_revenue",   f"{total_revenue:.2f}", ex=REDIS_TTL_SECONDS)
    pipe.set("kpi:last_updated",    datetime.now(timezone.utc).isoformat(), ex=REDIS_TTL_SECONDS)

    # Per-region KPIs + alerting state machine
    for region, stats in region_stats.items():
        ec     = stats["event_count"]
        errors = stats["errors"]
        error_rate = errors / ec if ec > 0 else 0.0

        # Health intensity: scale event count to 0-100 (cap at 1000 events/min → 100%)
        intensity = min(100, int((ec / 1000) * 100))

        pipe.set(f"region:{region}:event_count",      ec,        ex=REDIS_TTL_SECONDS)
        pipe.set(f"region:{region}:health_intensity", intensity, ex=REDIS_TTL_SECONDS)
        pipe.set(f"region:{region}:revenue",          f"{stats['revenue']:.2f}", ex=REDIS_TTL_SECONDS)

        # Alerting state machine
        if error_rate < ALERT_ERROR_RATE_THRESHOLD:
            # Back to Normal — reset pending timer
            _alert_pending_since.pop(region, None)
            alert_state = "Normal"
        else:
            if region not in _alert_pending_since:
                _alert_pending_since[region] = now_epoch  # start pending clock
            alert_state = _alert_state(error_rate, _alert_pending_since[region], now_epoch)

        pipe.set(f"alert:{region}:state",      alert_state, ex=REDIS_TTL_SECONDS)
        pipe.set(f"alert:{region}:error_rate", f"{error_rate:.4f}", ex=REDIS_TTL_SECONDS)

    pipe.execute()
    log.info(
        "[epoch %d] Redis write: %d total events, %d purchases, revenue=%.2f, regions=%s",
        epoch_id, total_events, purchase_count, total_revenue, list(region_stats.keys())
    )


# ---------------------------------------------------------------------------
# foreachBatch: Iceberg cold-path writer (enriched events)
# ---------------------------------------------------------------------------

def write_enriched_to_iceberg(batch_df: DataFrame, epoch_id: int) -> None:
    """
    foreachBatch sink for enriched events → Iceberg (ebap-silver).
    Uses merge-on-read upsert keyed on event_id to satisfy exactly-once semantics.
    """
    if batch_df.isEmpty():
        return

    count = batch_df.count()

    # Register as a temp view so we can use SQL MERGE
    batch_df.createOrReplaceTempView("batch_enriched_events")

    batch_df.sparkSession.sql(f"""
        MERGE INTO {ICEBERG_TABLE_EVENTS} t
        USING batch_enriched_events s
        ON t.event_id = s.event_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)

    log.info("[epoch %d] Iceberg enriched_events upserted %d rows", epoch_id, count)


def write_metrics_to_iceberg(batch_df: DataFrame, epoch_id: int) -> None:
    """
    foreachBatch sink for windowed metrics → Iceberg (ebap-silver).
    Appends — windows are immutable once closed.
    """
    if batch_df.isEmpty():
        return

    count = batch_df.count()
    batch_df.writeTo(ICEBERG_TABLE_METRICS).append()
    log.info("[epoch %d] Iceberg windowed_metrics appended %d rows", epoch_id, count)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    spark = create_spark_session()

    # --- 1. Bootstrap Iceberg tables ---
    bootstrap_iceberg_tables(spark)

    # --- 2. Read source streams ---
    log.info("Starting Kafka source streams...")
    events_df = read_events_stream(spark)
    users_df  = read_cdc_users_stream(spark)

    # --- 3. Stream-stream join: enrich events with user profiles ---
    enriched_df = enrich_events(events_df, users_df)

    # --- 4. Windowed aggregations (on events only — no join needed for KPIs) ---
    windowed = build_windowed_metrics(events_df)

    # --- 5. Hot path: 1-minute metrics → Redis ---
    log.info("Starting Redis (hot path) streaming query...")
    redis_query = (
        windowed["1m"]
        .writeStream
        .outputMode("update")
        .foreachBatch(write_to_redis)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/redis")
        .trigger(processingTime="30 seconds")
        .queryName("redis-hot-path")
        .start()
    )

    # --- 6. Cold path: enriched events → Iceberg ---
    log.info("Starting Iceberg enriched-events (cold path) streaming query...")
    iceberg_events_query = (
        enriched_df
        .writeStream
        .outputMode("append")
        .foreachBatch(write_enriched_to_iceberg)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/iceberg-events")
        .trigger(processingTime="60 seconds")
        .queryName("iceberg-enriched-events")
        .start()
    )

    # --- 7. Cold path: 1-hour windowed metrics → Iceberg ---
    log.info("Starting Iceberg windowed-metrics (cold path) streaming query...")
    iceberg_metrics_query = (
        windowed["1h"]
        .writeStream
        .outputMode("append")
        .foreachBatch(write_metrics_to_iceberg)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/iceberg-metrics")
        .trigger(processingTime="60 seconds")
        .queryName("iceberg-windowed-metrics")
        .start()
    )

    log.info(
        "All streaming queries active: [%s, %s, %s]",
        redis_query.name,
        iceberg_events_query.name,
        iceberg_metrics_query.name,
    )

    # Block until all queries terminate (or SIGTERM for graceful shutdown)
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
