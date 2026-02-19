"""
config.py
EBAP Streaming — Constants and logging configuration.

Single source of truth for all tuneable constants used across the streaming package.
Every other module imports from here.
"""

import logging

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
