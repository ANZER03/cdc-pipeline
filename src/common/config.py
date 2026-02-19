"""
common/config.py
EBAP — Centralized configuration loader.

Reads configuration from environment variables with sensible defaults.
All application modules should import constants from here rather than
defining them inline.
"""

import os

# ---------------------------------------------------------------------------
# Kafka
# ---------------------------------------------------------------------------
KAFKA_BROKERS    = os.getenv("KAFKA_BROKERS",    "kafka:9092")
TOPIC_EVENTS_RAW = os.getenv("TOPIC_EVENTS_RAW", "ebap.events.raw")
TOPIC_CDC_USERS  = os.getenv("TOPIC_CDC_USERS",  "ebap.cdc.users")

# ---------------------------------------------------------------------------
# Iceberg / MinIO
# ---------------------------------------------------------------------------
CHECKPOINT_BASE       = os.getenv("CHECKPOINT_BASE",  "s3a://ebap-checkpoints/streaming")
ICEBERG_CATALOG       = os.getenv("ICEBERG_CATALOG",  "ebap")
ICEBERG_DB            = os.getenv("ICEBERG_DB",        "events_db")
ICEBERG_TABLE_EVENTS  = f"{ICEBERG_CATALOG}.{ICEBERG_DB}.enriched_events"
ICEBERG_TABLE_METRICS = f"{ICEBERG_CATALOG}.{ICEBERG_DB}.windowed_metrics"

MINIO_ENDPOINT        = os.getenv("MINIO_ENDPOINT",   "http://minio:9000")
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID", "admin")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "password")

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
REDIS_HOST        = os.getenv("REDIS_HOST",        "redis")
REDIS_PORT        = int(os.getenv("REDIS_PORT",    "6379"))
REDIS_TTL_SECONDS = int(os.getenv("REDIS_TTL",     "86400"))  # 24 hours

# ---------------------------------------------------------------------------
# Alerting thresholds
# ---------------------------------------------------------------------------
ALERT_ERROR_RATE_THRESHOLD = float(os.getenv("ALERT_ERROR_RATE_THRESHOLD", "0.05"))
ALERT_PENDING_DURATION_S   = int(os.getenv("ALERT_PENDING_DURATION_S",     "60"))

# ---------------------------------------------------------------------------
# PostgreSQL (Iceberg JDBC catalog)
# ---------------------------------------------------------------------------
POSTGRES_HOST     = os.getenv("POSTGRES_HOST",     "postgres")
POSTGRES_PORT     = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER     = os.getenv("POSTGRES_USER",     "admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "admin")
ICEBERG_CATALOG_DB = os.getenv("ICEBERG_CATALOG_DB", "iceberg_catalog")
