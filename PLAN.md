# Nexus Data Streaming Platform — Refactoring Plan

> **Scope**: Refactor the EBAP CDC pipeline into a production-grade, real-time data streaming platform that feeds the Nexus Dashboard (a React e-commerce monitoring app). Backend/pipeline only — frontend is a separate repository.

> **Reference**: All data contracts, schemas, and target architecture are defined in [DESCRIPTION.md](./DESCRIPTION.md).

---

## Table of Contents

1. [Decisions & Constraints](#decisions--constraints)
2. [Current State Summary](#current-state-summary)
3. [Target State Summary](#target-state-summary)
4. [Phase 1 — PostgreSQL Schema & Seed Data](#phase-1--postgresql-schema--seed-data)
5. [Phase 2 — Kafka Topics](#phase-2--kafka-topics)
6. [Phase 3 — Debezium Connector & Avro Serialization](#phase-3--debezium-connector--avro-serialization)
7. [Phase 4 — Docker Compose Overhaul](#phase-4--docker-compose-overhaul)
8. [Phase 5 — Streaming Foundation (Config, Schemas, Sources)](#phase-5--streaming-foundation-config-schemas-sources)
9. [Phase 6 — Spark Transform Jobs](#phase-6--spark-transform-jobs)
10. [Phase 7 — Redis Write Helper & Pub/Sub](#phase-7--redis-write-helper--pubsub)
11. [Phase 8 — Data Generator](#phase-8--data-generator)
12. [Phase 9 — FastAPI Backend (SSE + REST)](#phase-9--fastapi-backend-sse--rest)
13. [Phase 10 — Cleanup & Configuration](#phase-10--cleanup--configuration)
14. [Phase 11 — Testing & Validation](#phase-11--testing--validation)
15. [Appendix A — File Inventory](#appendix-a--file-inventory)
16. [Appendix B — Redis Key & Pub/Sub Reference](#appendix-b--redis-key--pubsub-reference)

---

## Decisions & Constraints

These decisions were made during the planning session and are final for this refactoring effort.

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | Backend/pipeline only | Frontend (Nexus Dashboard) is a separate repo |
| High-volume data path | Direct to Kafka | `raw.request_log` and `raw.system_metrics` bypass PostgreSQL to avoid WAL pressure |
| Spark job architecture | Separate modules, 2-3 grouped containers | Balance between isolation and resource efficiency |
| Cold storage | Redis only (drop Iceberg) | Focus on hot-path dashboard delivery; Iceberg can be re-added later |
| Serialization | Avro + Schema Registry | Schema evolution, smaller messages, enforced contracts |
| Naming convention | Full rename to Nexus | Topics: `pg.public.*`, Redis: `nexus:*`, DB: `nexus_db` |
| Build order | Bottom-up (data layer first) | PostgreSQL → Kafka → Debezium → Docker → Spark → API |

### Spark Job Grouping (3 Containers)

| Container | Jobs | Kafka Sources | Trigger |
|-----------|------|--------------|---------|
| `spark-job-transactions` | KpiAggregator, RegionAggregator, ActivityEnricher | `pg.public.orders`, `pg.public.sessions`, `pg.public.user_events`, `pg.public.cart_items`, `pg.public.users` | 10-15s |
| `spark-job-infrastructure` | TrafficTimeSeriesBuilder, HealthCheckAggregator, GeoHeaderAggregator | `raw.request_log`, `raw.system_metrics` | 10-15s |
| `spark-job-derived` | DevicePlatformAggregator, AlertEvaluator | `pg.public.sessions`, `aggregated.kpis` | 10-30s |

---

## Current State Summary

**Completed phases (1-5 of old plan):**
- Docker Compose with 15 services (Kafka KRaft 2-broker, Schema Registry, PostgreSQL, Debezium, Redis, MinIO, Spark)
- Spark Streaming with 3 monolithic queries (Redis hot-path, Iceberg events, Iceberg metrics)
- Debezium CDC capturing only `public.users`
- JSON serialization (no Avro)
- Redis keys: `kpi:*`, `region:*` (old naming)
- Iceberg cold storage on MinIO (Bronze/Silver/Gold buckets)

**Known bugs in current implementation:**
1. **Schema mismatch**: PostgreSQL `users` table has `username`/`tier`/`created_at` but Spark CDC schema expects `name`/`plan`/`signup_ts` → null values in CDC stream
2. **User ID mismatch**: Seed data uses `usr_001`-`usr_010`, test generator uses `user-0001`-`user-0010` → stream-stream join never matches (all events dropped)
3. **Module-level alert state**: `_alert_pending_since` dict in `redis_sink.py` is not fault-tolerant

---

## Target State Summary

A fully wired data streaming platform:

```
PostgreSQL (9 tables) → Debezium CDC → Kafka (Avro + Schema Registry)
                                              ↓
Application (request_log, system_metrics) → Kafka (Direct, Avro)
                                              ↓
                                    Spark Streaming (8 jobs in 3 containers)
                                              ↓
                                    Redis (nexus:* keys + Pub/Sub channels)
                                              ↓
                                    FastAPI (REST snapshots + SSE push)
                                              ↓
                                    Nexus Dashboard (React, separate repo)
```

---

## Phase 1 — PostgreSQL Schema & Seed Data

**Goal**: Replace the single `users` table with the complete e-commerce data model.

**Status**: `[ ] Not started`

### Files to Modify

| File | Action |
|------|--------|
| `init-scripts/postgres/00-create-databases.sh` | Update: rename `ebap_db` → `nexus_db`, keep `iceberg_catalog` for future use |
| `init-scripts/postgres/seed-postgres.sql` | **Complete rewrite** |

### 1.1 Database Initialization (`00-create-databases.sh`)

- Create database `nexus_db` (replaces `ebap_db`)
- Keep `iceberg_catalog` database (no harm in leaving it; useful if Iceberg is re-added)

### 1.2 Table DDL (`seed-postgres.sql`)

Create the following tables in `nexus_db`. All DDL comes from DESCRIPTION.md Section 6.

#### Transactional Tables

**`users`**
```sql
CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(100) NOT NULL,
    display_name    VARCHAR(200) NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    country_code    CHAR(2),
    city            VARCHAR(100),
    region_name     VARCHAR(100),
    platform        VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**`products`**
```sql
CREATE TABLE products (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(500) NOT NULL,
    category        VARCHAR(100),
    price           DECIMAL(10, 2) NOT NULL,
    merchant_region VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**`orders`**
```sql
CREATE TABLE orders (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id),
    total_amount    DECIMAL(10, 2) NOT NULL,
    currency        CHAR(3) DEFAULT 'USD',
    status          VARCHAR(20) NOT NULL,       -- pending, completed, failed, refunded
    region_name     VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**`order_items`**
```sql
CREATE TABLE order_items (
    id              BIGSERIAL PRIMARY KEY,
    order_id        BIGINT REFERENCES orders(id),
    product_id      BIGINT REFERENCES products(id),
    quantity        INTEGER NOT NULL DEFAULT 1,
    unit_price      DECIMAL(10, 2) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**`cart_items`**
```sql
CREATE TABLE cart_items (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id),
    product_id      BIGINT REFERENCES products(id),
    quantity        INTEGER NOT NULL DEFAULT 1,
    added_at        TIMESTAMPTZ DEFAULT NOW(),
    removed_at      TIMESTAMPTZ
);
```

#### Behavioral Tables

**`user_events`**
```sql
CREATE TABLE user_events (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id),
    event_type      VARCHAR(50) NOT NULL,
    page_url        TEXT,
    referrer_url    TEXT,
    user_agent      TEXT,
    ip_address      INET,
    session_id      UUID,
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**`sessions`**
```sql
CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         BIGINT REFERENCES users(id),
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,
    platform        VARCHAR(50),
    country_code    CHAR(2),
    city            VARCHAR(100),
    region_name     VARCHAR(100),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### Region Mapping Tables

**`country_region_mapping`**
```sql
CREATE TABLE country_region_mapping (
    country_code    CHAR(2) NOT NULL PRIMARY KEY,
    region_name     VARCHAR(100) NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    latitude        DOUBLE PRECISION NOT NULL
);
```

**`city_region_mapping`**
```sql
CREATE TABLE city_region_mapping (
    id              BIGSERIAL PRIMARY KEY,
    country_code    CHAR(2) NOT NULL,
    city_pattern    VARCHAR(200) NOT NULL,
    region_name     VARCHAR(100) NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    latitude        DOUBLE PRECISION NOT NULL
);
CREATE INDEX idx_city_region_country ON city_region_mapping(country_code);
```

### 1.3 CDC Configuration

For every table captured by Debezium:
```sql
ALTER TABLE users       REPLICA IDENTITY FULL;
ALTER TABLE products    REPLICA IDENTITY FULL;
ALTER TABLE orders      REPLICA IDENTITY FULL;
ALTER TABLE order_items REPLICA IDENTITY FULL;
ALTER TABLE cart_items  REPLICA IDENTITY FULL;
ALTER TABLE user_events REPLICA IDENTITY FULL;
ALTER TABLE sessions    REPLICA IDENTITY FULL;
```

Publication:
```sql
CREATE PUBLICATION nexus_cdc_pub FOR TABLE
    users, products, orders, order_items,
    cart_items, user_events, sessions;
```

### 1.4 Seed Data

Populate with realistic reference and sample data:

- **`country_region_mapping`**: All countries mapped to 9 dashboard regions (see DESCRIPTION.md Section 4.2 for region definitions)
- **`city_region_mapping`**: US East/West city split + Canadian city overrides (see DESCRIPTION.md Section 6.4)
- **`users`**: 50 users distributed across all 9 regions, various platforms
- **`products`**: 25 products across categories, merchant_regions distributed globally
- **Initial `orders`**: 10-20 sample orders in various statuses (pending, completed, failed)
- **Initial `sessions`**: 20-30 sessions, some active, some ended
- **Initial `user_events`**: 30-50 events covering all event types

### 1.5 Acceptance Criteria

- [ ] `docker compose up postgres` starts successfully
- [ ] All 9 tables exist in `nexus_db` with correct schemas
- [ ] All tables have `REPLICA IDENTITY FULL`
- [ ] Publication `nexus_cdc_pub` includes all 7 CDC tables
- [ ] Region mapping tables contain data for all 9 dashboard regions
- [ ] Seed data has no foreign key violations
- [ ] `SELECT count(*) FROM users` returns 50

---

## Phase 2 — Kafka Topics

**Goal**: Create all Kafka topics with appropriate partition counts.

**Status**: `[ ] Not started`

**Depends on**: None (can run in parallel with Phase 1)

### Files to Modify

| File | Action |
|------|--------|
| `init-scripts/kafka/create-topics.sh` | **Complete rewrite** |

### 2.1 Topic Definitions

#### CDC Topics (Debezium auto-creates, but we pre-create for partition control)

| Topic | Partitions | Key | Replication |
|-------|-----------|-----|-------------|
| `pg.public.users` | 6 | `id` | 1 |
| `pg.public.products` | 3 | `id` | 1 |
| `pg.public.orders` | 12 | `id` | 1 |
| `pg.public.order_items` | 12 | `order_id` | 1 |
| `pg.public.cart_items` | 6 | `user_id` | 1 |
| `pg.public.user_events` | 12 | `user_id` | 1 |
| `pg.public.sessions` | 6 | `user_id` | 1 |

#### Direct-to-Kafka Topics (no Debezium)

| Topic | Partitions | Key | Replication |
|-------|-----------|-----|-------------|
| `raw.request_log` | 12 | `region_name` | 1 |
| `raw.system_metrics` | 6 | `node_name` | 1 |

#### Enriched / Intermediate Topics (Spark output, optional)

| Topic | Partitions | Key | Replication |
|-------|-----------|-----|-------------|
| `enriched.activities` | 6 | `user_id` | 1 |
| `aggregated.kpis` | 3 | `window_end` | 1 |
| `aggregated.regions` | 3 | `region_name` | 1 |
| `aggregated.traffic` | 3 | `window_end` | 1 |
| `evaluated.alerts` | 3 | `rule_id` | 1 |

### 2.2 Script Logic

```bash
# Wait for Kafka readiness
# Create all topics with --if-not-exists flag
# List topics matching pg.* and raw.* and enriched.* and aggregated.* and evaluated.*
```

### 2.3 Acceptance Criteria

- [ ] All 16 topics created successfully
- [ ] `kafka-topics --list` shows all expected topics
- [ ] Partition counts match specification

---

## Phase 3 — Debezium Connector & Avro Serialization

**Goal**: Expand CDC from 1 table to 7, switch from JSON to Avro, add unwrap transform.

**Status**: `[ ] Not started`

**Depends on**: Phase 1 (tables must exist), Phase 2 (topics must exist)

### Files to Modify

| File | Action |
|------|--------|
| `infrastructure/debezium/postgres-connector.json` | **Complete rewrite** |
| `init-scripts/debezium/register-connector.sh` | Update connector name |
| `infrastructure/docker/spark/Dockerfile` | Add Avro JARs, remove Iceberg JARs |

### 3.1 Connector Configuration

```json
{
  "name": "nexus-postgres-cdc",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "admin",
    "database.password": "admin",
    "database.dbname": "nexus_db",

    "topic.prefix": "pg",
    "table.include.list": "public.users,public.products,public.orders,public.order_items,public.cart_items,public.user_events,public.sessions",

    "plugin.name": "pgoutput",
    "slot.name": "nexus_cdc_slot",
    "publication.name": "nexus_cdc_pub",
    "publication.autocreate.mode": "filtered",

    "key.converter": "io.confluent.connect.avro.AvroConverter",
    "key.converter.schema.registry.url": "http://schema-registry:8081",
    "value.converter": "io.confluent.connect.avro.AvroConverter",
    "value.converter.schema.registry.url": "http://schema-registry:8081",

    "transforms": "unwrap",
    "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
    "transforms.unwrap.add.fields": "op,table,source.ts_ms",
    "transforms.unwrap.drop.tombstones": "true",
    "transforms.unwrap.delete.handling.mode": "rewrite",

    "decimal.handling.mode": "double",
    "time.precision.mode": "connect",
    "snapshot.mode": "initial",
    "heartbeat.interval.ms": "10000"
  }
}
```

**Key configuration choices:**
- `ExtractNewRecordState` unwrap: flattens the Debezium envelope so each Kafka message is a plain row (not nested `{before, after, op, source}`)
- `add.fields: op,table,source.ts_ms`: adds the operation type and source timestamp as header fields so Spark can filter by `op` and use the DB transaction time
- `decimal.handling.mode: double`: converts DECIMAL columns to doubles (simpler than Avro bytes-based decimals)
- `delete.handling.mode: rewrite`: on DELETE, produces a record with `__deleted: true` instead of a tombstone
- `snapshot.mode: initial`: full snapshot on first run, then incremental CDC

### 3.2 Debezium Connect Image

The standard `debezium/connect:2.3` image does **not** include Confluent Avro converters. We need one of:

**Option A (Recommended)**: Build a custom Debezium Connect image that adds the Avro converter JARs:
```dockerfile
FROM debezium/connect:2.3
# Download Confluent Avro converter + dependencies
RUN cd /kafka/connect && \
    mkdir confluent-avro && cd confluent-avro && \
    curl -sL https://packages.confluent.io/maven/io/confluent/kafka-connect-avro-converter/7.7.0/kafka-connect-avro-converter-7.7.0.jar -o kafka-connect-avro-converter-7.7.0.jar && \
    curl -sL https://packages.confluent.io/maven/io/confluent/kafka-schema-registry-client/7.7.0/kafka-schema-registry-client-7.7.0.jar -o kafka-schema-registry-client-7.7.0.jar && \
    curl -sL https://repo1.maven.org/maven2/org/apache/avro/avro/1.11.3/avro-1.11.3.jar -o avro-1.11.3.jar
```

**Option B**: Use `confluentinc/cp-kafka-connect` base image with Debezium connector plugin installed on top.

**New file**: `infrastructure/docker/debezium/Dockerfile`

### 3.3 Spark Dockerfile Updates

Update `infrastructure/docker/spark/Dockerfile`:

**Add:**
- `spark-avro` JAR (for reading Avro-encoded Kafka messages)
- `kafka-schema-registry-client` JAR (for Schema Registry integration)
- `kafka-avro-serializer` JAR

**Remove (or keep dormant):**
- `iceberg-spark-runtime` JAR (not needed for Redis-only)
- `iceberg-aws-bundle` JAR (not needed without MinIO/S3)

**Keep:**
- `spark-sql-kafka` JAR (Kafka source)
- `spark-redis` JAR (Redis sink)
- `postgresql` JDBC JAR (if keeping iceberg_catalog DB for future)

### 3.4 Acceptance Criteria

- [ ] Debezium connector registers successfully via REST API
- [ ] Schema Registry contains schemas for all 7 CDC topics (`curl http://localhost:8081/subjects`)
- [ ] Inserting a row into `nexus_db.users` produces an Avro-encoded message on `pg.public.users`
- [ ] The unwrap transform produces flat records (no nested `before`/`after` envelope)
- [ ] The `__op` field is present in each record
- [ ] `kafka-avro-console-consumer` can read and deserialize messages from all CDC topics

---

## Phase 4 — Docker Compose Overhaul

**Goal**: Update the container stack for the new architecture.

**Status**: `[ ] Not started`

**Depends on**: Phases 1-3 (new configs must be ready)

### Files to Modify

| File | Action |
|------|--------|
| `docker-compose.yml` | **Major rewrite** |
| `infrastructure/docker/debezium/Dockerfile` | **New file** |
| `infrastructure/docker/api/Dockerfile` | **New file** |

### 4.1 Services Overview (Target)

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| `kafka-1` | `confluentinc/cp-kafka:7.7.7` | 9092 | Kafka broker 1 (KRaft) |
| `kafka-2` | `confluentinc/cp-kafka:7.7.7` | 9093 | Kafka broker 2 (KRaft) |
| `kafka-init` | `confluentinc/cp-kafka:7.7.7` | — | Topic creation (init, exits) |
| `kafka-ui` | `provectuslabs/kafka-ui:latest` | 8080 | Kafka management UI |
| `schema-registry` | `confluentinc/cp-schema-registry:7.7.7` | 8081 | Avro schema registry |
| `postgres` | `debezium/postgres:15` | 5432 | Source DB + Iceberg catalog |
| `pgadmin` | `dpage/pgadmin4:latest` | 5050 | DB management UI |
| `debezium-connect` | Custom (see 3.2) | 8083 | CDC connector with Avro |
| `debezium-init` | `curlimages/curl:latest` | — | Register connector (init, exits) |
| `redis` | `redis:7-alpine` | 6379 | Hot storage + Pub/Sub |
| `spark-master` | Custom Spark | 8082 | Spark standalone master |
| `spark-worker` | Custom Spark | — | Spark worker (2 cores, 2GB) |
| `spark-job-transactions` | Custom Spark | — | Spark submit: KPI + Region + Activity jobs |
| `spark-job-infrastructure` | Custom Spark | — | Spark submit: Traffic + Health + Geo jobs |
| `spark-job-derived` | Custom Spark | — | Spark submit: Platform + Alert jobs |
| `nexus-api` | Custom FastAPI | 8000 | REST + SSE backend |

**Removed services** (compared to current):
- `minio` — not needed (Redis-only)
- `minio-init` — not needed
- Old single `spark-streaming-submit` — replaced by 3 job containers

### 4.2 Key Configuration Changes

**PostgreSQL**:
- Init script creates `nexus_db` instead of `ebap_db`
- Mounts updated `seed-postgres.sql`

**Debezium Connect**:
- Uses custom image with Avro converter JARs
- `SCHEMA_REGISTRY_URL` environment variable added
- Mounts updated `postgres-connector.json`

**Spark containers** (all 3 job submits):
- Remove all Iceberg/S3A/MinIO `--conf` flags
- Add Avro/Schema Registry `--conf` flags:
  ```
  --packages org.apache.spark:spark-avro_2.12:3.5.3
  --conf spark.sql.avro.schemaRegistryUrl=http://schema-registry:8081
  ```
- Each container runs a different Python entry point:
  - `spark-job-transactions` → `src/streaming/jobs/transaction_analytics.py`
  - `spark-job-infrastructure` → `src/streaming/jobs/infrastructure_analytics.py`
  - `spark-job-derived` → `src/streaming/jobs/derived_analytics.py`

**FastAPI (new)**:
```yaml
nexus-api:
  build: ./infrastructure/docker/api
  ports:
    - "8000:8000"
  environment:
    REDIS_URL: redis://redis:6379
  depends_on:
    redis:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 10s
    timeout: 5s
    retries: 3
```

### 4.3 Dependency Chain

```
postgres
  ├─→ kafka-1, kafka-2
  │     ├─→ kafka-init (topics)
  │     ├─→ schema-registry
  │     │     └─→ debezium-connect
  │     │           └─→ debezium-init (register connector)
  │     └─→ kafka-ui
  └─→ pgadmin

redis
  └─→ nexus-api

debezium-init + redis + spark-master + spark-worker
  ├─→ spark-job-transactions
  ├─→ spark-job-infrastructure
  └─→ spark-job-derived
```

### 4.4 Acceptance Criteria

- [ ] `docker compose up -d` starts all services without errors
- [ ] All health checks pass within 120 seconds
- [ ] `docker compose ps` shows all services as healthy/running
- [ ] Kafka UI accessible at `localhost:8080`
- [ ] Schema Registry accessible at `localhost:8081`
- [ ] PGAdmin accessible at `localhost:5050`
- [ ] FastAPI docs accessible at `localhost:8000/docs`

---

## Phase 5 — Streaming Foundation (Config, Schemas, Sources)

**Goal**: Restructure `src/streaming/` from monolithic to modular job architecture. Build the shared foundation layer.

**Status**: `[ ] Not started`

**Depends on**: Phase 3 (Avro schemas registered), Phase 4 (Docker ready)

### Files to Modify

| File | Action |
|------|--------|
| `src/streaming/config.py` | **Complete rewrite** |
| `src/streaming/schemas.py` | **Complete rewrite** |
| `src/streaming/spark_session.py` | **Major simplification** |
| `src/streaming/kafka_sources.py` | **Complete rewrite** |

### New Files

| File | Purpose |
|------|---------|
| `src/streaming/redis_client.py` | Shared Redis writer with pub/sub (see Phase 7) |
| `src/streaming/jobs/__init__.py` | Package init |
| `src/streaming/jobs/transaction_analytics.py` | Entry point: App 1 |
| `src/streaming/jobs/infrastructure_analytics.py` | Entry point: App 2 |
| `src/streaming/jobs/derived_analytics.py` | Entry point: App 3 |

### 5.1 Config (`config.py`)

Single source of truth for all constants. Organized by domain.

```python
# === Kafka ===
KAFKA_BROKERS = "kafka-1:9092,kafka-2:9093"
SCHEMA_REGISTRY_URL = "http://schema-registry:8081"

# CDC Topics (Debezium → Kafka, Avro-encoded)
TOPIC_CDC_USERS       = "pg.public.users"
TOPIC_CDC_PRODUCTS    = "pg.public.products"
TOPIC_CDC_ORDERS      = "pg.public.orders"
TOPIC_CDC_ORDER_ITEMS = "pg.public.order_items"
TOPIC_CDC_CART_ITEMS  = "pg.public.cart_items"
TOPIC_CDC_USER_EVENTS = "pg.public.user_events"
TOPIC_CDC_SESSIONS    = "pg.public.sessions"

# Direct Topics (Application → Kafka, Avro-encoded)
TOPIC_RAW_REQUEST_LOG    = "raw.request_log"
TOPIC_RAW_SYSTEM_METRICS = "raw.system_metrics"

# Enriched / Intermediate Topics
TOPIC_ENRICHED_ACTIVITIES = "enriched.activities"
TOPIC_AGGREGATED_KPIS     = "aggregated.kpis"
TOPIC_AGGREGATED_REGIONS  = "aggregated.regions"
TOPIC_AGGREGATED_TRAFFIC  = "aggregated.traffic"
TOPIC_EVALUATED_ALERTS    = "evaluated.alerts"

# === Redis ===
REDIS_HOST = "redis"
REDIS_PORT = 6379

# Redis Keys (nexus: prefix)
REDIS_KEY_KPI_CURRENT       = "nexus:kpi:current"
REDIS_KEY_KPI_SNAPSHOT       = "nexus:kpi:snapshot:{epoch_hour}"  # template
REDIS_KEY_TRAFFIC_TS         = "nexus:traffic:timeseries"
REDIS_KEY_ACTIVITY_FEED      = "nexus:activity:feed"
REDIS_KEY_REGIONS_CURRENT    = "nexus:regions:current"
REDIS_KEY_FLOWS_CURRENT      = "nexus:flows:current"
REDIS_KEY_PLATFORM_BREAKDOWN = "nexus:platform:breakdown"
REDIS_KEY_ALERT_RULES        = "nexus:alert:rules"
REDIS_KEY_ALERT_SUMMARY      = "nexus:alert:summary"
REDIS_KEY_HEALTH_CURRENT     = "nexus:health:current"
REDIS_KEY_GEO_HEADER         = "nexus:geo:header"

# Redis Pub/Sub Channels (nexus. prefix with dot separator)
CHANNEL_KPI       = "nexus.kpi"
CHANNEL_TRAFFIC   = "nexus.traffic"
CHANNEL_ACTIVITY  = "nexus.activity"
CHANNEL_REGIONS   = "nexus.regions"
CHANNEL_FLOWS     = "nexus.flows"
CHANNEL_ALERTS    = "nexus.alerts"
CHANNEL_PLATFORM  = "nexus.platform"
CHANNEL_HEALTH    = "nexus.health"
CHANNEL_GEO       = "nexus.geo"

# === Spark Windows ===
KPI_WINDOW_DURATION     = "30 seconds"
KPI_SLIDE_INTERVAL      = "10 seconds"
TRAFFIC_WINDOW_DURATION = "10 seconds"
REGION_WINDOW_DURATION  = "30 seconds"
REGION_SLIDE_INTERVAL   = "15 seconds"
PLATFORM_WINDOW_DURATION = "5 minutes"
HEALTH_WINDOW_DURATION  = "30 seconds"
HEALTH_SLIDE_INTERVAL   = "15 seconds"
GEO_WINDOW_DURATION     = "1 minute"
GEO_SLIDE_INTERVAL      = "30 seconds"

# === Trigger Intervals ===
TRIGGER_TRANSACTIONS  = "10 seconds"
TRIGGER_INFRASTRUCTURE = "10 seconds"
TRIGGER_DERIVED        = "10 seconds"

# === Alert Thresholds ===
ALERT_RULES = [
    {"id": "alert_1", "name": "High Latency p99 > 200ms", "severity": "critical", "metric": "system.latency.p99", "threshold": 200, "frequency": "1m"},
    {"id": "alert_2", "name": "Checkout Error Rate > 1%", "severity": "critical", "metric": "checkout.error_rate", "threshold": 1.0, "frequency": "30s"},
    {"id": "alert_3", "name": "Database CPU Utilization", "severity": "warning", "metric": "db.cpu.percent", "threshold": 80, "frequency": "5m"},
]
ALERT_CONSECUTIVE_BREACHES = 3  # breaches before pending → firing

# === Region Definitions (fixed) ===
REGIONS = [
    {"name": "North America (East)", "coords": [-74, 40]},
    {"name": "North America (West)", "coords": [-122, 37]},
    {"name": "Western Europe",       "coords": [2, 48]},
    {"name": "Japan",                "coords": [139, 35]},
    {"name": "Southeast Asia",       "coords": [103, 1]},
    {"name": "Australia",            "coords": [151, -33]},
    {"name": "Brazil",               "coords": [-46, -23]},
    {"name": "India",                "coords": [77, 28]},
    {"name": "South Africa",         "coords": [18, -33]},
]

# === Checkpoint Paths (local filesystem, no S3) ===
CHECKPOINT_BASE = "/tmp/nexus-checkpoints"
```

### 5.2 Schemas (`schemas.py`)

With Avro + Schema Registry + `ExtractNewRecordState` unwrap, the Kafka messages are **flat Avro records** (no envelope). Spark reads them using the `from_avro` function with Schema Registry integration.

However, PySpark `from_avro()` with Schema Registry requires the `spark-avro` package and specific configuration. The schema definitions here serve as **reference documentation** and for cases where we need explicit StructType parsing.

Define StructType schemas for each unwrapped CDC topic:
- `USERS_SCHEMA` — matches `users` table + `__op`, `__table`, `__source_ts_ms`
- `ORDERS_SCHEMA` — matches `orders` table + op fields
- `USER_EVENTS_SCHEMA` — matches `user_events` table + op fields
- `SESSIONS_SCHEMA` — matches `sessions` table + op fields
- `CART_ITEMS_SCHEMA` — matches `cart_items` table + op fields
- `PRODUCTS_SCHEMA` — matches `products` table + op fields
- `REQUEST_LOG_SCHEMA` — matches direct-to-Kafka request_log format
- `SYSTEM_METRICS_SCHEMA` — matches direct-to-Kafka system_metrics format

### 5.3 Spark Session (`spark_session.py`)

Simplified factory — remove all Iceberg/S3A configuration:

```python
def create_spark_session(app_name: str) -> SparkSession:
    return (
        SparkSession.builder
        .appName(app_name)
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.streaming.stopGracefullyOnShutdown", "true")
        # Schema Registry for Avro
        .config("spark.sql.avro.schemaRegistryUrl", SCHEMA_REGISTRY_URL)
        .getOrCreate()
    )
```

### 5.4 Kafka Sources (`kafka_sources.py`)

Provide reader functions for each topic/group:

```python
def read_cdc_stream(spark, topic, schema) -> DataFrame:
    """Read an Avro-encoded CDC topic, deserialize, filter non-delete ops."""

def read_direct_stream(spark, topic, schema) -> DataFrame:
    """Read an Avro-encoded direct topic (request_log, system_metrics)."""

# Convenience functions:
def read_orders(spark) -> DataFrame
def read_sessions(spark) -> DataFrame
def read_user_events(spark) -> DataFrame
def read_users(spark) -> DataFrame
def read_cart_items(spark) -> DataFrame
def read_request_log(spark) -> DataFrame
def read_system_metrics(spark) -> DataFrame
```

Each reader:
1. Reads from Kafka (`format("kafka")`)
2. Deserializes Avro value using `from_avro()` with Schema Registry
3. Extracts typed columns
4. Filters: `__op IN ('c', 'u', 'r')` for CDC topics (exclude deletes)
5. Applies watermark on the appropriate timestamp column

### 5.5 Acceptance Criteria

- [ ] `config.py` imports cleanly with no missing references
- [ ] All StructType schemas match the PostgreSQL DDL from Phase 1
- [ ] `create_spark_session()` creates a session without Iceberg errors
- [ ] Each `read_*` function returns a correctly typed DataFrame when Kafka has data
- [ ] CDC readers filter out delete operations by default

---

## Phase 6 — Spark Transform Jobs

**Goal**: Implement all 8 Spark streaming jobs as individual transform modules, wired through 3 entry points.

**Status**: `[ ] Not started`

**Depends on**: Phase 5 (foundation layer)

### New Files

```
src/streaming/transforms/
    kpi_aggregator.py
    traffic_builder.py
    activity_enricher.py
    region_aggregator.py
    device_platform.py
    alert_evaluator.py
    health_aggregator.py
    geo_header.py
```

### 6.1 Job: KpiAggregator (`kpi_aggregator.py`)

**Consumes**: orders, sessions, request_log streams
**Window**: 30s sliding, 10s slide
**Output**: `nexus:kpi:current` HASH + `nexus.kpi` pub/sub

Computation per window:
| Metric | Source | Logic |
|--------|--------|-------|
| `activeUsers` | sessions | `COUNT(DISTINCT id) WHERE is_active = true AND ended_at IS NULL` |
| `revenue` | orders | `SUM(total_amount) WHERE status = 'completed'` |
| `orders` | orders | `COUNT(*) WHERE status = 'completed'` |
| `errorRate` | request_log | `(COUNT(*) WHERE status_code >= 500) / COUNT(*) * 100` |
| `latency` | request_log | `PERCENTILE_APPROX(latency_ms, 0.5)` or `AVG(latency_ms)` |

Trend computation:
- On each window, also write `nexus:kpi:snapshot:{epoch_hour}` with 2h TTL
- Read previous hour's snapshot from Redis
- `trend = ((current - oneHourAgo) / oneHourAgo) * 100`

**foreachBatch logic:**
```python
def write_kpis(batch_df, batch_id):
    kpi_dict = compute_kpis(batch_df)
    trends = compute_trends(kpi_dict, redis_client)
    merged = {**kpi_dict, **trends, "updatedAt": now_epoch_ms()}

    redis_client.hset("nexus:kpi:current", mapping=merged)
    redis_client.publish("nexus.kpi", json.dumps(merged))
    redis_client.hset(f"nexus:kpi:snapshot:{current_epoch_hour()}", mapping=kpi_dict)
    redis_client.expire(f"nexus:kpi:snapshot:{current_epoch_hour()}", 7200)
```

### 6.2 Job: TrafficTimeSeriesBuilder (`traffic_builder.py`)

**Consumes**: request_log stream
**Window**: 10s tumbling
**Output**: `nexus:traffic:timeseries` LIST + `nexus.traffic` pub/sub

Per window:
```python
value = count(*)  # total requests in window
timestamp = window_end_epoch_ms
label = format_timestamp(window_end, "hh:mm:ss a")  # "02:15:30 PM"
```

Write pattern:
```python
point = {"timestamp": ts, "value": val, "label": lbl}
redis_client.lpush("nexus:traffic:timeseries", json.dumps(point))
redis_client.ltrim("nexus:traffic:timeseries", 0, 20)  # keep 21
redis_client.publish("nexus.traffic", json.dumps(point))
```

### 6.3 Job: ActivityEnricher (`activity_enricher.py`)

**Consumes**: user_events stream, joined with users (for display_name, location)
**Processing**: Per-event (no windowing)
**Output**: `nexus:activity:feed` LIST + `nexus.activity` pub/sub

Event type mapping:
| `user_events.event_type` | Dashboard `action` |
|--------------------------|-------------------|
| `checkout_complete` | `purchase` |
| `page_view` | `view` |
| `add_to_cart` | `cart` |
| `login` | `login` |

For `purchase` events: join with orders stream to get `total_amount`.

Enriched event format:
```json
{
  "id": "evt_<uuid>",
  "user": "Alex",
  "action": "purchase",
  "amount": 149.99,
  "timestamp": "2026-03-05T14:15:30.000Z",
  "location": "New York, US"
}
```

**User lookup strategy**: Read users CDC stream from `earliest` offset to build a complete user profile table in Spark state. Use stream-stream join (inner join is acceptable since Debezium snapshots all users at startup).

### 6.4 Job: RegionAggregator (`region_aggregator.py`)

**Consumes**: orders, request_log, sessions streams
**Window**: 30s sliding, 15s slide
**Output**: `nexus:regions:current` STRING + `nexus:flows:current` STRING + pub/sub channels

Per-region computation:
```python
sales = SUM(total_amount) FROM orders WHERE status = 'completed' GROUP BY region_name
request_count = COUNT(*) FROM request_log GROUP BY region_name
max_count = MAX(request_count)
intensity = (request_count / max_count) * 100  # normalized 0-100
```

Data flows (top 5 cross-region):
```python
# Join orders with products to find cross-region flows
# user_region (from order.region_name) → merchant_region (from product.merchant_region)
# Filter where user_region != merchant_region
# GROUP BY (user_region, merchant_region), COUNT(*) as volume
# ORDER BY volume DESC, LIMIT 5
# Normalize volume to 0-100 scale
```

Output format (regions):
```json
[
  {"name": "Japan", "coords": [139, 35], "intensity": 95.3, "sales": 18500},
  ...
]
```

Output format (flows):
```json
[
  {"id": "flow_1", "source": [-74, 40], "target": [2, 48], "value": 72.5},
  ...
]
```

### 6.5 Job: DevicePlatformAggregator (`device_platform.py`)

**Consumes**: sessions stream
**Window**: 5min tumbling
**Output**: `nexus:platform:breakdown` STRING + `nexus.platform` pub/sub

```python
platform_counts = sessions.filter(is_active == True).groupBy("platform").count()
# Output: [{"name": "Desktop", "value": 4500}, {"name": "Mobile", "value": 3200}, ...]
```

### 6.6 Job: AlertEvaluator (`alert_evaluator.py`)

**Consumes**: `aggregated.kpis` Kafka topic (output of KpiAggregator)
**Processing**: Stateful — tracks consecutive breaches per rule
**Output**: `nexus:alert:rules` STRING + `nexus:alert:summary` HASH + `nexus.alerts` pub/sub

State machine per rule:
```
OK → (breach detected) → Pending
Pending → (N consecutive breaches) → Firing
Pending/Firing → (value below threshold) → OK
```

Use `flatMapGroupsWithState` (or simpler: maintain state in Redis between micro-batches).

Only publish to `nexus.alerts` when at least one rule changes state (not every tick).

### 6.7 Job: HealthCheckAggregator (`health_aggregator.py`)

**Consumes**: system_metrics stream (`raw.system_metrics`)
**Window**: 30s sliding, 15s slide
**Output**: `nexus:health:current` HASH + `nexus.health` pub/sub

```python
cpu = AVG(metric_value) WHERE metric_name = 'cpu_percent'
memory = AVG(metric_value) WHERE metric_name = 'memory_percent'
total_nodes = COUNT(DISTINCT node_name)
healthy_nodes = COUNT(DISTINCT node_name) WHERE cpu < 90 AND memory < 95
apiClusterScore = (healthy_nodes / total_nodes) * 100
apiClusterStatus = CASE
    WHEN score >= 90 THEN 'HEALTHY'
    WHEN score >= 50 THEN 'DEGRADED'
    ELSE 'DOWN'
```

### 6.8 Job: GeoHeaderAggregator (`geo_header.py`)

**Consumes**: health data, request_log aggregations
**Window**: 1min sliding, 30s slide
**Output**: `nexus:geo:header` HASH + `nexus.geo` pub/sub

```python
uptime = (total_healthy_time / total_time) * 100
globalLoad = SUM(request_count) formatted as "X.X PB/S" or "X.X TB/S"
engineVersion = "V4-Orbit"  # static
protocolStatus = "Secure"   # static
```

### 6.9 Entry Points (Job Containers)

**`jobs/transaction_analytics.py`** — Spark App 1:
```python
spark = create_spark_session("nexus-transactions")
orders = read_orders(spark)
sessions = read_sessions(spark)
user_events = read_user_events(spark)
users = read_users(spark)
cart_items = read_cart_items(spark)

# Start streaming queries
kpi_query = start_kpi_aggregator(orders, sessions, request_log=None)
region_query = start_region_aggregator(orders, sessions)
activity_query = start_activity_enricher(user_events, users, orders)

spark.streams.awaitAnyTermination()
```

**`jobs/infrastructure_analytics.py`** — Spark App 2:
```python
spark = create_spark_session("nexus-infrastructure")
request_log = read_request_log(spark)
system_metrics = read_system_metrics(spark)

traffic_query = start_traffic_builder(request_log)
health_query = start_health_aggregator(system_metrics)
geo_query = start_geo_header_aggregator(system_metrics, request_log)

spark.streams.awaitAnyTermination()
```

**`jobs/derived_analytics.py`** — Spark App 3:
```python
spark = create_spark_session("nexus-derived")
sessions = read_sessions(spark)
# For alerts: read from aggregated.kpis topic instead of recomputing
kpis_stream = read_aggregated_kpis(spark)

platform_query = start_device_platform_aggregator(sessions)
alert_query = start_alert_evaluator(kpis_stream)

spark.streams.awaitAnyTermination()
```

### 6.10 Acceptance Criteria

- [ ] Each transform module is independently importable and testable
- [ ] KpiAggregator produces all 5 KPIs + 5 trends from windowed data
- [ ] TrafficTimeSeriesBuilder appends exactly 1 data point per 10s window
- [ ] ActivityEnricher correctly maps event_type → action and enriches with user data
- [ ] RegionAggregator produces 9-element region array + up to 5 data flows
- [ ] DevicePlatformAggregator groups by 4 platforms correctly
- [ ] AlertEvaluator implements stateful OK → Pending → Firing transitions
- [ ] HealthCheckAggregator derives cluster status from node metrics
- [ ] All 3 entry points start without errors and create their streaming queries

---

## Phase 7 — Redis Write Helper & Pub/Sub

**Goal**: Create a reusable Redis client that handles the dual-write pattern (snapshot key + pub/sub publish).

**Status**: `[ ] Not started`

**Depends on**: Phase 5 (config constants)

### New File

| File | Purpose |
|------|---------|
| `src/streaming/redis_client.py` | Shared Redis helper for all Spark jobs |

### 7.1 Design

```python
class NexusRedisWriter:
    """Thread-safe Redis writer with connection pooling for Spark executors."""

    def __init__(self, host=REDIS_HOST, port=REDIS_PORT):
        self._pool = redis.ConnectionPool(host=host, port=port, max_connections=10)

    def _client(self) -> redis.Redis:
        return redis.Redis(connection_pool=self._pool)

    def write_hash(self, key: str, mapping: dict, channel: str = None, ttl: int = None):
        """Write a HASH and optionally publish to a channel."""
        r = self._client()
        pipe = r.pipeline()
        pipe.hset(key, mapping={k: str(v) for k, v in mapping.items()})
        if ttl:
            pipe.expire(key, ttl)
        if channel:
            pipe.publish(channel, json.dumps(mapping))
        pipe.execute()

    def write_json(self, key: str, data, channel: str = None):
        """Write a JSON string and optionally publish."""
        r = self._client()
        payload = json.dumps(data)
        pipe = r.pipeline()
        pipe.set(key, payload)
        if channel:
            pipe.publish(channel, payload)
        pipe.execute()

    def push_to_list(self, key: str, item: dict, max_len: int, channel: str = None):
        """LPUSH + LTRIM a JSON item to a capped list, optionally publish."""
        r = self._client()
        payload = json.dumps(item)
        pipe = r.pipeline()
        pipe.lpush(key, payload)
        pipe.ltrim(key, 0, max_len - 1)
        if channel:
            pipe.publish(channel, payload)
        pipe.execute()

    def read_hash(self, key: str) -> dict:
        """Read all fields from a HASH key (for trend computation)."""
        return self._client().hgetall(key)
```

### 7.2 Usage Pattern in foreachBatch

Every Spark job's `foreachBatch` function will:
1. Collect batch results to the driver
2. Use `NexusRedisWriter` to write snapshot + publish

```python
writer = NexusRedisWriter()

def process_kpi_batch(batch_df, batch_id):
    if batch_df.isEmpty():
        return
    kpis = compute_kpis(batch_df)
    writer.write_hash("nexus:kpi:current", kpis, channel="nexus.kpi")
```

### 7.3 Acceptance Criteria

- [ ] `NexusRedisWriter` connects to Redis successfully
- [ ] `write_hash` writes all fields and publishes atomically (pipeline)
- [ ] `write_json` writes and publishes correctly
- [ ] `push_to_list` respects max_len (LTRIM)
- [ ] `read_hash` returns correct data for trend computation
- [ ] Connection pooling: multiple threads can use the writer concurrently

---

## Phase 8 — Data Generator

**Goal**: Create a realistic e-commerce event generator that feeds the pipeline for testing.

**Status**: `[ ] Not started`

**Depends on**: Phase 1 (tables exist), Phase 2 (topics exist)

### Files to Modify

| File | Action |
|------|--------|
| `scripts/generate_test_data.py` | **Complete rewrite** |

### 8.1 Generator Responsibilities

The data generator simulates realistic e-commerce traffic by:

1. **Writing to PostgreSQL** (triggers Debezium CDC):
   - INSERT new orders (with status transitions: pending → completed/failed)
   - INSERT user_events (page_view, login, add_to_cart, checkout_complete, etc.)
   - INSERT/UPDATE sessions (start, heartbeat, end)
   - INSERT cart_items (add to cart, remove from cart via UPDATE)

2. **Writing directly to Kafka** (bypasses PostgreSQL):
   - `raw.request_log` — high-volume API request events
   - `raw.system_metrics` — infrastructure metrics (CPU, memory per node)

### 8.2 Event Generation Logic

**User behavior sequences** (realistic correlated events):
```
login → page_view → page_view → add_to_cart → page_view → checkout_start → checkout_complete
login → page_view → page_view → logout
page_view → page_view → page_view (anonymous browsing)
```

**Order lifecycle**:
```
INSERT order (status='pending') → UPDATE order (status='completed') after 5-15s delay
INSERT order (status='pending') → UPDATE order (status='failed') with 10% probability
```

**Session lifecycle**:
```
INSERT session (is_active=true) → UPDATE session (is_active=false, ended_at=now) after 5-30min
```

**Request log** (direct to Kafka, high volume):
```
Generate 50-200 request events per second
Distribute across 9 regions
90% status 200, 5% status 4xx, 5% status 5xx
Latency: normal distribution, mean=100ms, std=50ms
```

**System metrics** (direct to Kafka):
```
Every 10 seconds, for each of 3-5 nodes:
  cpu_percent: normal distribution, mean=40, std=15
  memory_percent: normal distribution, mean=55, std=10
```

### 8.3 Configuration

```
--mode       all|postgres|kafka     (which targets to write to)
--rate       events-per-second      (default: 10)
--duration   seconds                (default: 300 = 5min)
--users      path-to-users-csv     (optional: read from seeded users)
```

### 8.4 Acceptance Criteria

- [ ] Generator runs without errors against a live stack
- [ ] PostgreSQL CDC events appear in Kafka CDC topics within 2 seconds
- [ ] Direct Kafka events appear in `raw.request_log` and `raw.system_metrics`
- [ ] Event sequences are correlated (same user_id across login → view → purchase)
- [ ] Region distribution covers all 9 regions
- [ ] Order status transitions (pending → completed) trigger Debezium UPDATE events

---

## Phase 9 — FastAPI Backend (SSE + REST)

**Goal**: Build the API layer that connects Redis to the Nexus Dashboard.

**Status**: `[ ] Not started`

**Depends on**: Phase 7 (Redis data present)

### New Files

```
src/api/
    __init__.py
    main.py                    # FastAPI app, CORS, lifespan
    config.py                  # API configuration
    routes/
        __init__.py
        snapshots.py           # 9 REST GET endpoints
        events.py              # SSE endpoint (GET /events)
    services/
        __init__.py
        redis_service.py       # aioredis client for reading + pub/sub
        sse_manager.py         # SSE connection manager, fan-out, keepalive
```

### 9.1 REST Snapshot Endpoints

| Method | Path | Redis Source | Response |
|--------|------|-------------|----------|
| GET | `/api/metrics` | `HGETALL nexus:kpi:current` | KPI JSON object |
| GET | `/api/traffic` | `LRANGE nexus:traffic:timeseries 0 20` | Array of 21 DataPoints (oldest-first) |
| GET | `/api/activities` | `LRANGE nexus:activity:feed 0 14` | Array of up to 15 Activity objects |
| GET | `/api/regions` | `GET nexus:regions:current` | Array of 9 RegionMetric objects |
| GET | `/api/flows` | `GET nexus:flows:current` | Array of up to 5 DataFlow objects |
| GET | `/api/alerts` | `GET nexus:alert:rules` + `HGETALL nexus:alert:summary` | `{rules: [...], summary: {...}}` |
| GET | `/api/platform` | `GET nexus:platform:breakdown` | Platform array |
| GET | `/api/health` | `HGETALL nexus:health:current` | Health JSON object |
| GET | `/api/geo` | `HGETALL nexus:geo:header` | Geo header JSON object |

All endpoints return `200 OK` with JSON body. If the Redis key doesn't exist yet (pipeline hasn't started), return sensible defaults (empty arrays, zero-value objects).

### 9.2 SSE Endpoint (`GET /events`)

Single long-lived HTTP connection. Subscribes to all 9 `nexus.*` Redis Pub/Sub channels and fans out each message as a named SSE event.

**Channel → SSE event type mapping:**

| Redis Pub/Sub Channel | SSE `event:` type |
|----------------------|------------------|
| `nexus.kpi` | `metrics` |
| `nexus.traffic` | `traffic` |
| `nexus.activity` | `activity` |
| `nexus.regions` | `regions` |
| `nexus.flows` | `flows` |
| `nexus.alerts` | `alert` |
| `nexus.platform` | `platform` |
| `nexus.health` | `health` |
| `nexus.geo` | `geo` |

**SSE wire format:**
```
event: metrics
data: {"activeUsers":14502,"revenue":42500,...}

event: activity
data: {"id":"evt_abc123","user":"Alex","action":"purchase",...}

```

**Keepalive**: Send `: keep-alive\n\n` comment every 25 seconds.

### 9.3 CORS Configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # Vite dev
    allow_methods=["GET"],
    allow_headers=["*"],
)
```

### 9.4 Health Endpoint

```
GET /health → {"status": "ok", "redis": "connected", "uptime": 1234.5}
```

### 9.5 Dockerfile (`infrastructure/docker/api/Dockerfile`)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY src/api/ ./api/
COPY requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Dependencies** (`requirements-api.txt`):
```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
redis[hiredis]>=5.0.0
sse-starlette>=2.0.0
```

### 9.6 Acceptance Criteria

- [ ] All 9 REST endpoints return correct JSON from Redis
- [ ] `GET /events` opens an SSE connection and receives real-time events
- [ ] SSE keepalive comments arrive every ~25 seconds when no data events
- [ ] CORS headers are set correctly for frontend origins
- [ ] `GET /health` returns 200 when Redis is connected
- [ ] Multiple SSE clients can connect simultaneously
- [ ] FastAPI docs page (`/docs`) lists all endpoints

---

## Phase 10 — Cleanup & Configuration

**Goal**: Remove dead code, align configuration, update project metadata.

**Status**: `[ ] Not started`

**Depends on**: All previous phases

### Files to Remove

| File | Reason |
|------|--------|
| `src/streaming/main.py` | Replaced by 3 job entry points |
| `src/streaming/iceberg_bootstrap.py` | Iceberg dropped (Redis-only) |
| `src/streaming/sinks/iceberg_sink.py` | Iceberg dropped |
| `src/streaming/transforms/enrichment.py` | Replaced by `activity_enricher.py` |
| `src/streaming/transforms/windowed_aggregations.py` | Replaced by individual transforms |

### Files to Update

| File | Changes |
|------|---------|
| `pyproject.toml` | Add FastAPI dependencies, update project name/description |
| `Makefile` | New targets: `make api`, `make generate-data`, `make spark-transactions`, `make spark-infrastructure`, `make spark-derived` |
| `.env.example` | New environment variables for Nexus config |
| `src/common/config.py` | Align with Nexus naming |
| `scripts/health_check.py` | Check new services (FastAPI, schema registry subjects) |
| `docs/runbook.md` | Update operational commands |

### Makefile Targets

```makefile
# Start the full stack
up:
    docker compose up -d

# Start individual components
up-infra:
    docker compose up -d kafka-1 kafka-2 schema-registry postgres redis

up-cdc:
    docker compose up -d debezium-connect debezium-init

up-spark:
    docker compose up -d spark-master spark-worker spark-job-transactions spark-job-infrastructure spark-job-derived

up-api:
    docker compose up -d nexus-api

# Data generation
generate-data:
    python scripts/generate_test_data.py --mode all --rate 10 --duration 300

# Logs
logs-transactions:
    docker compose logs -f spark-job-transactions

logs-infrastructure:
    docker compose logs -f spark-job-infrastructure

logs-derived:
    docker compose logs -f spark-job-derived

logs-api:
    docker compose logs -f nexus-api

# Health check
health:
    python scripts/health_check.py

# Redis inspection
redis-cli:
    docker compose exec redis redis-cli

redis-monitor:
    docker compose exec redis redis-cli MONITOR

# Clean
clean:
    docker compose down -v
    rm -rf /tmp/nexus-checkpoints
```

### 10.1 Acceptance Criteria

- [ ] No dead imports or references to removed files
- [ ] `make up` brings up the full stack
- [ ] `make generate-data` produces events
- [ ] `make health` reports all services healthy
- [ ] `.env.example` documents all required environment variables

---

## Phase 11 — Testing & Validation

**Goal**: Verify the entire pipeline works end-to-end.

**Status**: `[ ] Not started`

**Depends on**: All previous phases

### Files to Modify

| File | Action |
|------|--------|
| `tests/unit/test_alerting.py` | Update for new state machine |
| `tests/integration/test_connectors.py` | Remove Iceberg tests, add Avro/Redis tests |
| `tests/integration/test_iceberg_minio.py` | **Remove** (Iceberg dropped) |
| `tests/e2e/test_full_pipeline.py` | **Complete rewrite** for new architecture |

### New Test Files

```
tests/
    unit/
        test_transforms.py        # Unit tests for each transform function
        test_redis_client.py      # Unit tests for NexusRedisWriter
    integration/
        test_redis_contracts.py   # Verify Redis key shapes match DESCRIPTION.md contracts
        test_avro_schemas.py      # Verify Avro deserialization works correctly
    api/
        test_endpoints.py         # FastAPI endpoint tests
        test_sse.py               # SSE connection and event delivery tests
    e2e/
        test_full_pipeline.py     # End-to-end: generate data → verify Redis → verify API
```

### 11.1 Unit Tests

Test each transform in isolation with mock DataFrames:
- `test_kpi_aggregator`: verify windowed KPI computation
- `test_traffic_builder`: verify time-series point generation
- `test_activity_enricher`: verify event_type mapping and enrichment
- `test_region_aggregator`: verify per-region aggregation and flow computation
- `test_alert_evaluator`: verify state transitions (OK → Pending → Firing)

### 11.2 Integration Tests

**Redis contract tests**: For each Redis key defined in DESCRIPTION.md Section 9:
- Seed the key with test data via `NexusRedisWriter`
- Read back and verify JSON shape matches the contract
- Verify pub/sub message delivery

**Avro schema tests**:
- Produce a test Avro message to a CDC topic
- Consume and deserialize with Spark
- Verify all fields are correctly typed

### 11.3 API Tests

- Test each REST endpoint returns correct shape
- Test SSE endpoint receives events when Redis pub/sub fires
- Test keepalive timing
- Test CORS headers
- Test graceful behavior when Redis keys don't exist (empty state)

### 11.4 End-to-End Tests

1. Start full Docker stack
2. Run data generator for 60 seconds
3. Verify all 11 Redis keys contain data
4. Verify all 9 REST endpoints return non-empty data
5. Verify SSE endpoint receives at least one event per channel
6. Verify data shapes match DESCRIPTION.md contracts exactly

### 11.5 Acceptance Criteria

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] All API tests pass
- [ ] End-to-end test completes successfully
- [ ] Zero schema mismatches between pipeline output and DESCRIPTION.md contracts

---

## Appendix A — File Inventory

### Files to Create (New)

| Path | Phase |
|------|-------|
| `infrastructure/docker/debezium/Dockerfile` | 3 |
| `infrastructure/docker/api/Dockerfile` | 9 |
| `requirements-api.txt` | 9 |
| `src/streaming/redis_client.py` | 7 |
| `src/streaming/jobs/__init__.py` | 5 |
| `src/streaming/jobs/transaction_analytics.py` | 6 |
| `src/streaming/jobs/infrastructure_analytics.py` | 6 |
| `src/streaming/jobs/derived_analytics.py` | 6 |
| `src/streaming/transforms/kpi_aggregator.py` | 6 |
| `src/streaming/transforms/traffic_builder.py` | 6 |
| `src/streaming/transforms/activity_enricher.py` | 6 |
| `src/streaming/transforms/region_aggregator.py` | 6 |
| `src/streaming/transforms/device_platform.py` | 6 |
| `src/streaming/transforms/alert_evaluator.py` | 6 |
| `src/streaming/transforms/health_aggregator.py` | 6 |
| `src/streaming/transforms/geo_header.py` | 6 |
| `src/api/__init__.py` | 9 |
| `src/api/main.py` | 9 |
| `src/api/config.py` | 9 |
| `src/api/routes/__init__.py` | 9 |
| `src/api/routes/snapshots.py` | 9 |
| `src/api/routes/events.py` | 9 |
| `src/api/services/__init__.py` | 9 |
| `src/api/services/redis_service.py` | 9 |
| `src/api/services/sse_manager.py` | 9 |

### Files to Rewrite

| Path | Phase |
|------|-------|
| `init-scripts/postgres/seed-postgres.sql` | 1 |
| `init-scripts/kafka/create-topics.sh` | 2 |
| `infrastructure/debezium/postgres-connector.json` | 3 |
| `docker-compose.yml` | 4 |
| `src/streaming/config.py` | 5 |
| `src/streaming/schemas.py` | 5 |
| `src/streaming/kafka_sources.py` | 5 |
| `src/streaming/sinks/redis_sink.py` | 6/7 |
| `scripts/generate_test_data.py` | 8 |

### Files to Update

| Path | Phase |
|------|-------|
| `init-scripts/postgres/00-create-databases.sh` | 1 |
| `init-scripts/debezium/register-connector.sh` | 3 |
| `infrastructure/docker/spark/Dockerfile` | 3 |
| `src/streaming/spark_session.py` | 5 |
| `pyproject.toml` | 10 |
| `Makefile` | 10 |
| `.env.example` | 10 |
| `src/common/config.py` | 10 |
| `scripts/health_check.py` | 10 |

### Files to Remove

| Path | Phase |
|------|-------|
| `src/streaming/main.py` | 10 |
| `src/streaming/iceberg_bootstrap.py` | 10 |
| `src/streaming/sinks/iceberg_sink.py` | 10 |
| `src/streaming/transforms/enrichment.py` | 10 |
| `src/streaming/transforms/windowed_aggregations.py` | 10 |
| `tests/integration/test_iceberg_minio.py` | 11 |

---

## Appendix B — Redis Key & Pub/Sub Reference

Quick reference for all Redis keys and pub/sub channels. Full contract definitions are in DESCRIPTION.md Sections 5 and 9.

### Keys

| Key | Type | Max Size | Written By | TTL |
|-----|------|----------|-----------|-----|
| `nexus:kpi:current` | HASH | 11 fields | KpiAggregator | — |
| `nexus:kpi:snapshot:{epoch_hour}` | HASH | 5 fields | KpiAggregator | 2h |
| `nexus:traffic:timeseries` | LIST | 21 items | TrafficTimeSeriesBuilder | — |
| `nexus:activity:feed` | LIST | 15 items | ActivityEnricher | — |
| `nexus:regions:current` | STRING | ~2KB JSON | RegionAggregator | — |
| `nexus:flows:current` | STRING | ~1KB JSON | RegionAggregator | — |
| `nexus:platform:breakdown` | STRING | ~500B JSON | DevicePlatformAggregator | — |
| `nexus:alert:rules` | STRING | ~2KB JSON | AlertEvaluator | — |
| `nexus:alert:summary` | HASH | 4 fields | AlertEvaluator | — |
| `nexus:health:current` | HASH | 5 fields | HealthCheckAggregator | — |
| `nexus:geo:header` | HASH | 5 fields | GeoHeaderAggregator | — |

### Pub/Sub Channels

| Channel | SSE Event Type | Published By | Frequency |
|---------|---------------|-------------|-----------|
| `nexus.kpi` | `metrics` | KpiAggregator | ~10s |
| `nexus.traffic` | `traffic` | TrafficTimeSeriesBuilder | ~10s |
| `nexus.activity` | `activity` | ActivityEnricher | per-event |
| `nexus.regions` | `regions` | RegionAggregator | ~15-30s |
| `nexus.flows` | `flows` | RegionAggregator | ~15-30s |
| `nexus.alerts` | `alert` | AlertEvaluator | on state change |
| `nexus.platform` | `platform` | DevicePlatformAggregator | ~5min |
| `nexus.health` | `health` | HealthCheckAggregator | ~15-30s |
| `nexus.geo` | `geo` | GeoHeaderAggregator | ~30s |
