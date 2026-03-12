"""Shared configuration for Nexus streaming jobs."""

from __future__ import annotations

import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
log = logging.getLogger("nexus.streaming")

# Kafka
KAFKA_BROKERS = "kafka-1:9092,kafka-2:9093"
SCHEMA_REGISTRY_URL = "http://schema-registry:8081"

# PostgreSQL
POSTGRES_HOST = "postgres"
POSTGRES_PORT = 5432
POSTGRES_DB = "nexus_db"
POSTGRES_USER = "admin"
POSTGRES_PASSWORD = "admin"

TOPIC_CDC_USERS = "pg.public.users"
TOPIC_CDC_PRODUCTS = "pg.public.products"
TOPIC_CDC_ORDERS = "pg.public.orders"
TOPIC_CDC_ORDER_ITEMS = "pg.public.order_items"
TOPIC_CDC_CART_ITEMS = "pg.public.cart_items"
TOPIC_CDC_USER_EVENTS = "pg.public.user_events"
TOPIC_CDC_SESSIONS = "pg.public.sessions"

TOPIC_RAW_REQUEST_LOG = "raw.request_log"
TOPIC_RAW_SYSTEM_METRICS = "raw.system_metrics"

TOPIC_ENRICHED_ACTIVITIES = "enriched.activities"
TOPIC_AGGREGATED_KPIS = "aggregated.kpis"
TOPIC_AGGREGATED_REGIONS = "aggregated.regions"
TOPIC_AGGREGATED_TRAFFIC = "aggregated.traffic"
TOPIC_EVALUATED_ALERTS = "evaluated.alerts"

# Redis
REDIS_HOST = "redis"
REDIS_PORT = 6379

REDIS_KEY_KPI_CURRENT = "nexus:kpi:current"
REDIS_KEY_KPI_SNAPSHOT = "nexus:kpi:snapshot:{epoch_hour}"
REDIS_KEY_TRAFFIC_TS = "nexus:traffic:timeseries"
REDIS_KEY_ACTIVITY_FEED = "nexus:activity:feed"
REDIS_KEY_REGIONS_CURRENT = "nexus:regions:current"
REDIS_KEY_FLOWS_CURRENT = "nexus:flows:current"
REDIS_KEY_PLATFORM_BREAKDOWN = "nexus:platform:breakdown"
REDIS_KEY_ALERT_RULES = "nexus:alert:rules"
REDIS_KEY_ALERT_SUMMARY = "nexus:alert:summary"
REDIS_KEY_HEALTH_CURRENT = "nexus:health:current"
REDIS_KEY_GEO_HEADER = "nexus:geo:header"

CHANNEL_KPI = "nexus.kpi"
CHANNEL_TRAFFIC = "nexus.traffic"
CHANNEL_ACTIVITY = "nexus.activity"
CHANNEL_REGIONS = "nexus.regions"
CHANNEL_FLOWS = "nexus.flows"
CHANNEL_ALERTS = "nexus.alerts"
CHANNEL_PLATFORM = "nexus.platform"
CHANNEL_HEALTH = "nexus.health"
CHANNEL_GEO = "nexus.geo"

# Windows and triggers
KPI_WINDOW_DURATION = "30 seconds"
KPI_SLIDE_INTERVAL = "10 seconds"
TRAFFIC_WINDOW_DURATION = "10 seconds"
REGION_WINDOW_DURATION = "30 seconds"
REGION_SLIDE_INTERVAL = "15 seconds"
PLATFORM_WINDOW_DURATION = "5 minutes"
HEALTH_WINDOW_DURATION = "30 seconds"
HEALTH_SLIDE_INTERVAL = "15 seconds"
GEO_WINDOW_DURATION = "1 minute"
GEO_SLIDE_INTERVAL = "30 seconds"

TRIGGER_TRANSACTIONS = "30 seconds"
TRIGGER_INFRASTRUCTURE = "30 seconds"
TRIGGER_DERIVED = "30 seconds"

ALERT_RULES = [
    {
        "id": "alert_1",
        "name": "High Latency p99 > 200ms",
        "severity": "critical",
        "metric": "system.latency.p99",
        "threshold": 200,
        "frequency": "1m",
    },
    {
        "id": "alert_2",
        "name": "Checkout Error Rate > 1%",
        "severity": "critical",
        "metric": "checkout.error_rate",
        "threshold": 1.0,
        "frequency": "30s",
    },
    {
        "id": "alert_3",
        "name": "Database CPU Utilization",
        "severity": "warning",
        "metric": "db.cpu.percent",
        "threshold": 80,
        "frequency": "5m",
    },
]
ALERT_CONSECUTIVE_BREACHES = 3

REGIONS = [
    {"name": "North America (East)", "coords": [-74, 40]},
    {"name": "North America (West)", "coords": [-122, 37]},
    {"name": "Western Europe", "coords": [2, 48]},
    {"name": "Japan", "coords": [139, 35]},
    {"name": "Southeast Asia", "coords": [103, 1]},
    {"name": "Australia", "coords": [151, -33]},
    {"name": "Brazil", "coords": [-46, -23]},
    {"name": "India", "coords": [77, 28]},
    {"name": "South Africa", "coords": [18, -33]},
]

CHECKPOINT_BASE = "/tmp/nexus-checkpoints"
