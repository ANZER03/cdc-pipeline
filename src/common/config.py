"""Legacy-compatible shared configuration aliases for Nexus."""

import os

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka-1:9092,kafka-2:9093")
SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")
TOPIC_RAW_REQUEST_LOG = os.getenv("TOPIC_RAW_REQUEST_LOG", "raw.request_log")
TOPIC_RAW_SYSTEM_METRICS = os.getenv("TOPIC_RAW_SYSTEM_METRICS", "raw.system_metrics")
TOPIC_CDC_USERS = os.getenv("TOPIC_CDC_USERS", "pg.public.users")

CHECKPOINT_BASE = os.getenv("CHECKPOINT_BASE", "/tmp/nexus-checkpoints")

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

ALERT_CONSECUTIVE_BREACHES = int(os.getenv("ALERT_CONSECUTIVE_BREACHES", "3"))

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "admin")
POSTGRES_DB = os.getenv("POSTGRES_DB", "nexus_db")
