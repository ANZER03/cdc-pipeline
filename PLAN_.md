# Pipeline Denormalization Migration Plan

> **Goal**: Remove all per-batch JDBC reads from Spark streaming jobs by embedding
> denormalized fields ("fat events") into event schemas at production time.
> Dashboard contracts (Redis keys, API endpoints, SSE channels) remain unchanged.
> Validation: 90-second end-to-end generation run.

---

## Table of Contents

1. [Diagnosis Summary](#1-diagnosis-summary)
2. [Architecture Principles](#2-architecture-principles)
3. [Schema Changes](#3-schema-changes)
4. [Phase 0 -- Clean Slate](#phase-0----clean-slate)
5. [Phase 1 -- Generator Fat Events](#phase-1----generator-fat-events)
6. [Phase 2 -- Remove JDBC Reads from Streaming Jobs](#phase-2----remove-jdbc-reads-from-streaming-jobs)
7. [Phase 3 -- Activity Enricher Upgrade](#phase-3----activity-enricher-upgrade)
8. [Phase 4 -- Platform Aggregator Cleanup](#phase-4----platform-aggregator-cleanup)
9. [Phase 5 -- Alert Evaluator Decision](#phase-5----alert-evaluator-decision)
10. [Phase 6 -- Validation](#phase-6----validation)
11. [File Change Manifest](#file-change-manifest)
12. [Risk Register](#risk-register)

---

## 1. Diagnosis Summary

Three root causes were identified during end-to-end testing:

| # | Issue | Root Cause | Status |
|---|-------|-----------|--------|
| 1 | Alert duplication | Both `alert_evaluator.py` and `kpi_aggregator.py` wrote to `nexus:alert:rules` / `nexus:alert:summary` | **Fixed** -- alert evaluator query removed from `transaction_analytics.py` |
| 2 | Generator hang | `run_postgres_generation()` used iteration count instead of wall-clock duration | **Fixed** -- switched to `time.monotonic()` loop with `timeout=` on subprocesses |
| 3 | Transaction Spark job lag (50-100s behind 10s trigger) | Per-batch JDBC reads + 4 concurrent streaming queries + `outputMode("complete")` + accumulating state | **Unfixed** -- requires denormalization (this plan) |

### Per-Batch JDBC Reads (The Primary Bottleneck)

| File | Line(s) | What It Does | Batch Impact |
|------|---------|-------------|-------------|
| `kpi_aggregator.py` | 100-127 | Queries `sessions` + `orders` via JDBC every KPI batch | ~2-5s per batch |
| `region_aggregator.py` | 155-179 | Queries `orders GROUP BY region_name` every region batch | ~2-5s per batch |
| `device_platform.py` | 79-101 | Queries `sessions GROUP BY platform` every platform batch | ~1-3s per batch |

Each of these runs a synchronous JDBC round-trip to Postgres **inside** a `foreachBatch` callback, blocking the Spark micro-batch pipeline and causing cascading delays across all 4 streaming queries sharing the transaction job's `SparkSession`.

---

## 2. Architecture Principles

1. **Fat events at the source**: The generator embeds all fields a downstream consumer needs directly into the Postgres row and Kafka payload. No runtime joins or lookups.
2. **Stream-only aggregation**: Spark jobs compute KPIs, regions, and platforms purely from the CDC/direct Kafka streams. Zero JDBC reads in the hot path.
3. **One-time JDBC only at startup** (if needed): Dimension snapshots (users, products) may be loaded once at job startup as broadcast variables for enrichment, but never inside `foreachBatch`.
4. **Dashboard contracts are frozen**: Redis keys, API endpoints, SSE channels, and payload shapes do not change.
5. **`display_name` is the primary user-facing field**, `username` is secondary/debug.

---

## 3. Schema Changes

### 3.1 Orders -- Add `user_display_name`, `platform`

**Current** `ORDERS_SCHEMA` (`schemas.py:52-63`):

```
id, user_id, total_amount, currency, status, region_name, created_at, updated_at, [CDC fields]
```

**New** fields to add:

| Field | Type | Nullable | Source | Purpose |
|-------|------|----------|--------|---------|
| `user_display_name` | StringType | Yes | `users.display_name` (looked up at insert time in generator) | Activity feed `user` field for purchases |
| `platform` | StringType | Yes | `users.platform` (looked up at insert time in generator) | Cross-region flow analysis, platform attribution |

The generator already has the full `UserRecord` when creating orders, so these are trivially available.

**StructType addition** (after `region_name`):

```python
StructField("user_display_name", StringType(), True),
StructField("platform", StringType(), True),
```

**Avro addition** (in `ORDERS_AVRO_SCHEMA`):

```json
{"name":"user_display_name","type":["null","string"],"default":null},
{"name":"platform","type":["null","string"],"default":null}
```

**Postgres DDL** -- add columns:

```sql
ALTER TABLE orders ADD COLUMN IF NOT EXISTS user_display_name VARCHAR(200);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS platform VARCHAR(50);
```

### 3.2 User Events -- Add `user_display_name`, `region_name`, `city`, `country_code`, `platform`, `amount`

**Current** `USER_EVENTS_SCHEMA` (`schemas.py:90-103`):

```
id, user_id, event_type, page_url, referrer_url, user_agent, ip_address, session_id, metadata, created_at, [CDC fields]
```

**New** fields to add:

| Field | Type | Nullable | Source | Purpose |
|-------|------|----------|--------|---------|
| `user_display_name` | StringType | Yes | `users.display_name` | Activity feed `user` field |
| `region_name` | StringType | Yes | `users.region_name` | Activity feed `location` |
| `city` | StringType | Yes | `users.city` | Activity feed `location` ("City, CC") |
| `country_code` | StringType | Yes | `users.country_code` | Activity feed `location` ("City, CC") |
| `platform` | StringType | Yes | `users.platform` | Platform attribution |
| `amount` | DoubleType | Yes | Order `total_amount` for `checkout_complete` events, null otherwise | Activity feed `amount` |

**StructType additions** (after `metadata`, before `created_at`):

```python
StructField("user_display_name", StringType(), True),
StructField("region_name", StringType(), True),
StructField("city", StringType(), True),
StructField("country_code", StringType(), True),
StructField("platform", StringType(), True),
StructField("amount", DoubleType(), True),
```

**Avro additions** (in `USER_EVENTS_AVRO_SCHEMA`):

```json
{"name":"user_display_name","type":["null","string"],"default":null},
{"name":"region_name","type":["null","string"],"default":null},
{"name":"city","type":["null","string"],"default":null},
{"name":"country_code","type":["null","string"],"default":null},
{"name":"platform","type":["null","string"],"default":null},
{"name":"amount","type":["null","double"],"default":null}
```

**Postgres DDL**:

```sql
ALTER TABLE user_events ADD COLUMN IF NOT EXISTS user_display_name VARCHAR(200);
ALTER TABLE user_events ADD COLUMN IF NOT EXISTS region_name VARCHAR(100);
ALTER TABLE user_events ADD COLUMN IF NOT EXISTS city VARCHAR(100);
ALTER TABLE user_events ADD COLUMN IF NOT EXISTS country_code CHAR(2);
ALTER TABLE user_events ADD COLUMN IF NOT EXISTS platform VARCHAR(50);
ALTER TABLE user_events ADD COLUMN IF NOT EXISTS amount DOUBLE PRECISION;
```

### 3.3 Request Log -- Add `user_display_name` (optional), `platform`

**Current** `REQUEST_LOG_SCHEMA` (`schemas.py:122-134`):

```
id, endpoint, method, status_code, latency_ms, user_id, session_id, region_name, created_at
```

**New** fields to add:

| Field | Type | Nullable | Source | Purpose |
|-------|------|----------|--------|---------|
| `user_display_name` | StringType | Yes | `users.display_name` | Richer activity enrichment when request_log is the activity source |
| `platform` | StringType | Yes | `users.platform` | Platform-based request metrics |

**StructType additions** (after `region_name`):

```python
StructField("user_display_name", StringType(), True),
StructField("platform", StringType(), True),
```

**Avro additions** (in `REQUEST_LOG_AVRO_SCHEMA`):

```json
{"name":"user_display_name","type":["null","string"],"default":null},
{"name":"platform","type":["null","string"],"default":null}
```

> Note: `request_log` is written directly to Kafka (not via Postgres CDC), so no DDL change is needed.

### 3.4 Sessions -- No Schema Change Needed

Sessions already have: `platform`, `country_code`, `city`, `region_name`, `is_active`.

Optional: Add `user_display_name` if needed later. Not required for current dashboard contracts.

### 3.5 Summary of All Schema Additions

| Table/Topic | New Fields | Avro Schema Constant | StructType Constant |
|-------------|-----------|---------------------|-------------------|
| `orders` / `pg.public.orders` | `user_display_name`, `platform` | `ORDERS_AVRO_SCHEMA` | `ORDERS_SCHEMA` |
| `user_events` / `pg.public.user_events` | `user_display_name`, `region_name`, `city`, `country_code`, `platform`, `amount` | `USER_EVENTS_AVRO_SCHEMA` | `USER_EVENTS_SCHEMA` |
| `request_log` / `raw.request_log` | `user_display_name`, `platform` | `REQUEST_LOG_AVRO_SCHEMA` | `REQUEST_LOG_SCHEMA` |

---

## Phase 0 -- Clean Slate

**Purpose**: Eliminate stale checkpoints and Kafka offsets that would conflict with schema changes.

### Steps

1. Stop all containers:
   ```bash
   docker compose down -v
   ```

2. Remove Spark checkpoint directories:
   ```bash
   # These live inside the Spark containers at /tmp/nexus-checkpoints/
   # The -v flag on docker compose down removes volumes, which handles this.
   # If checkpoints are on bind mounts, also run:
   rm -rf /tmp/nexus-checkpoints
   ```

3. Delete all Kafka topics (or let them be recreated fresh by `docker compose up`):
   ```bash
   # Topics are stored in Kafka volumes, wiped by -v
   ```

4. Reset Debezium connector state:
   ```bash
   # Connector offsets are in Kafka internal topics, wiped by -v
   ```

5. Re-register Avro schemas in Schema Registry (they auto-register on first produce, but verify compatibility mode allows the additions):
   ```bash
   # Schema Registry data is in its internal topic, wiped by -v
   # The new schemas will register on first generator or Debezium produce
   ```

6. Verify clean state:
   ```bash
   docker compose up -d
   # Wait for all services healthy
   docker compose ps
   ```

---

## Phase 1 -- Generator Fat Events

**Purpose**: Make the generator embed denormalized fields in all Postgres INSERTs and Kafka payloads.

### 1.1 File: `scripts/generate_test_data.py`

#### Orders INSERT

**Current** (approximate, in the order generation function):
```sql
INSERT INTO orders (user_id, total_amount, currency, status, region_name, created_at, updated_at)
VALUES ({user.id}, {amount}, 'USD', '{status}', '{user.region_name}', ...);
```

**New**:
```sql
INSERT INTO orders (user_id, total_amount, currency, status, region_name, user_display_name, platform, created_at, updated_at)
VALUES ({user.id}, {amount}, 'USD', '{status}', '{user.region_name}', '{user.display_name}', '{user.platform}', ...);
```

The generator already loads full `UserRecord` objects with `display_name`, `region_name`, `platform` etc., so this is a straightforward SQL string change.

#### User Events INSERT

**Current**:
```sql
INSERT INTO user_events (user_id, event_type, page_url, referrer_url, user_agent, ip_address, session_id, metadata, created_at)
VALUES (...);
```

**New**:
```sql
INSERT INTO user_events (user_id, event_type, page_url, referrer_url, user_agent, ip_address, session_id, metadata,
                         user_display_name, region_name, city, country_code, platform, amount, created_at)
VALUES (..., '{user.display_name}', '{user.region_name}', '{user.city}', '{user.country_code}', '{user.platform}', {amount_or_null}, ...);
```

For `amount`: Only non-null for `checkout_complete` events. The generator creates the order and knows the `total_amount`, so pass it through to the user event.

#### Request Log Kafka Payload

**Current** `REQUEST_LOG_SCHEMA` in generator (`generate_test_data.py:28-43`):
```python
"fields": [
    {"name": "id", "type": "long"},
    {"name": "endpoint", ...},
    {"name": "method", ...},
    {"name": "status_code", ...},
    {"name": "latency_ms", ...},
    {"name": "user_id", ...},
    {"name": "session_id", ...},
    {"name": "region_name", ...},
    {"name": "created_at", ...},
]
```

**New** -- add after `region_name`:
```python
{"name": "user_display_name", "type": ["null", "string"], "default": None},
{"name": "platform", "type": ["null", "string"], "default": None},
```

And in the payload construction, include:
```python
"user_display_name": user.display_name if user else None,
"platform": user.platform if user else None,
```

### 1.2 File: `src/streaming/schemas.py`

Update all three schema pairs (StructType + Avro string) as specified in [Section 3](#3-schema-changes).

### 1.3 Postgres DDL

Either add an `ALTER TABLE` migration script or modify `init.sql` / the schema seed:

```sql
-- orders
ALTER TABLE orders ADD COLUMN IF NOT EXISTS user_display_name VARCHAR(200);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS platform VARCHAR(50);

-- user_events
ALTER TABLE user_events ADD COLUMN IF NOT EXISTS user_display_name VARCHAR(200);
ALTER TABLE user_events ADD COLUMN IF NOT EXISTS region_name VARCHAR(100);
ALTER TABLE user_events ADD COLUMN IF NOT EXISTS city VARCHAR(100);
ALTER TABLE user_events ADD COLUMN IF NOT EXISTS country_code CHAR(2);
ALTER TABLE user_events ADD COLUMN IF NOT EXISTS platform VARCHAR(50);
ALTER TABLE user_events ADD COLUMN IF NOT EXISTS amount DOUBLE PRECISION;
```

> Since we're doing a clean-slate Phase 0, it's simpler to modify the original `CREATE TABLE` statements in the init SQL directly.

---

## Phase 2 -- Remove JDBC Reads from Streaming Jobs

**Purpose**: Rewrite `foreachBatch` callbacks to use only stream-derived data.

### 2.1 KPI Aggregator (`kpi_aggregator.py`)

#### Remove: `_load_current_business_kpis()` (lines 100-127)

This function runs a JDBC query every batch to get `activeUsers`, `revenue`, and `orders` from Postgres. But `build_kpi_frame()` (lines 171-228) already computes these from the stream:

- `activeUsers` = windowed count of active sessions
- `revenue` = windowed sum of completed order amounts
- `orders` = windowed count of completed orders

The JDBC call then **overwrites** the stream values with the all-time Postgres totals. This is the wrong semantic for a real-time dashboard (it makes the values cumulative rather than windowed).

**Change**: Remove the `current.update(_load_current_business_kpis(...))` call in `write_kpi_batch()` (line 67). The stream-computed values from `build_kpi_frame()` are the correct real-time values.

**Specifically**:

```python
# BEFORE (line 66-67):
current = _serialize_kpi_row(rows[0])
current.update(_load_current_business_kpis(batch_df.sparkSession))

# AFTER:
current = _serialize_kpi_row(rows[0])
# Stream values are used directly -- no JDBC override
```

**Also remove**: All Postgres config imports (`POSTGRES_HOST`, `POSTGRES_PORT`, etc.) from `kpi_aggregator.py` since they're only used by the deleted JDBC function.

#### Delete function: `_load_current_business_kpis()` entirely (lines 100-127)

### 2.2 Region Aggregator (`region_aggregator.py`)

#### Remove: `_load_sales_by_region()` (lines 155-179)

This function queries `SUM(total_amount) GROUP BY region_name` from Postgres every batch. But `build_region_snapshot()` (lines 107-137) already computes windowed `sales` per region from the order stream.

**Change**: Use the stream-computed `sales` directly in `write_region_batch()`.

```python
# BEFORE (line 38):
sales_by_region = _load_sales_by_region(batch_df.sparkSession)
# ...
"sales": round(float(sales_by_region.get(region_name, 0.0)), 2),

# AFTER:
# Use the sales value already computed in the stream aggregation:
"sales": round(float(item["sales"] or 0.0), 2),
```

**Delete function**: `_load_sales_by_region()` entirely (lines 155-179).

**Also remove**: All Postgres config imports from `region_aggregator.py`.

### 2.3 Device Platform (`device_platform.py`)

#### Remove: `_load_current_platform_counts()` (lines 79-101)

This function queries `sessions GROUP BY platform` from Postgres every batch. But `build_platform_breakdown()` (lines 56-65) already computes platform counts from the sessions CDC stream.

**Change**: Rewrite `write_platform_batch()` to use the batch DataFrame directly.

```python
# BEFORE (line 41):
rows = _load_current_platform_counts(batch_df.sparkSession)

# AFTER:
rows = batch_df.collect()
```

**Delete function**: `_load_current_platform_counts()` entirely (lines 79-101).

**Also remove**: `seed_platform_breakdown()` (lines 23-36) -- the one-time JDBC seed is no longer needed because the stream will populate the data. The first streaming micro-batch will write the platform breakdown.

**Also remove**: All Postgres config imports from `device_platform.py`.

### 2.4 Update Job Entry Points

#### `transaction_analytics.py`

Remove JDBC snapshot reads that are no longer needed:

```python
# BEFORE:
users_snapshot = read_postgres_table_snapshot(spark, "users")
orders_snapshot = read_postgres_table_snapshot(spark, "orders")
# ...
start_activity_enricher(request_log, users_snapshot, orders_snapshot)

# AFTER:
# Activity enricher uses denormalized fields from request_log directly
start_activity_enricher(request_log)
```

Remove `read_postgres_table_snapshot` import.

#### `derived_analytics.py`

Remove JDBC snapshot read and seed call:

```python
# BEFORE:
users_snapshot = read_postgres_table_snapshot(spark, "users")
seed_platform_breakdown(users_snapshot)

# AFTER:
# Platform breakdown is populated by the streaming query on first batch
# No seed needed
```

Remove `read_postgres_table_snapshot` and `seed_platform_breakdown` imports.

---

## Phase 3 -- Activity Enricher Upgrade

**Purpose**: Use denormalized fields from `request_log` instead of placeholder `User {id}`.

### Current State (`activity_enricher.py`)

The activity enricher currently:
- Takes `request_log` as input (despite the signature accepting `user_events_df`, `users_df`, `orders_df` -- the latter two are `del`'d)
- Maps endpoint patterns to action types (`checkout` -> purchase, `cart` -> cart, etc.)
- Uses `F.concat(F.lit("User "), F.col("user_id").cast("string"))` as the user display name (placeholder)
- Uses hardcoded `F.lit(149.99)` for purchase amounts
- Uses `region_name` + `"--"` for location (no city/country)

### Changes

With the denormalized `request_log` (now containing `user_display_name` and `platform`):

```python
# BEFORE:
F.concat(F.lit("User "), F.coalesce(F.col("user_id").cast("string"), F.lit("0"))).alias("user")

# AFTER:
F.coalesce(F.col("user_display_name"), F.concat(F.lit("User "), F.col("user_id").cast("string"))).alias("user")
```

For location, `request_log` already has `region_name`. We don't have `city`/`country_code` on request_log, but we can use region_name:

```python
# BEFORE:
F.concat_ws(", ", F.coalesce(F.col("region_name"), F.lit("Unknown")), F.lit("--")).alias("location")

# AFTER:
F.coalesce(F.col("region_name"), F.lit("Unknown")).alias("location")
```

### Alternative: Switch Activity Source to `user_events`

If we switch the activity enricher to consume `pg.public.user_events` instead of `raw.request_log`, we get **all** denormalized fields (`user_display_name`, `city`, `country_code`, `region_name`, `amount`, `platform`). This would produce much richer activity events:

```python
# With user_events as source:
"user": user_display_name,          # Real name, not "User 42"
"location": "New York, US",          # city + country_code
"amount": 149.99,                    # Real order amount for purchases
"action": mapped from event_type     # checkout_complete -> purchase, etc.
```

**Recommendation**: Switch to `user_events` as the primary activity source. This is the designed intent per `DESCRIPTION.md` Section 8.3.

### Signature Change

```python
# BEFORE:
def build_activity_feed(user_events_df, users_df, orders_df) -> DataFrame:
    del users_df
    del orders_df
    # uses request_log despite the parameter name

# AFTER:
def build_activity_feed(user_events_df: DataFrame) -> DataFrame:
    # user_events_df is now actually pg.public.user_events with denormalized fields
```

Update `start_activity_enricher()` and `transaction_analytics.py` call site accordingly.

---

## Phase 4 -- Platform Aggregator Cleanup

**Purpose**: Remove all JDBC dependencies from the derived analytics job.

### Changes to `device_platform.py`

1. Delete `seed_platform_breakdown()` function
2. Delete `_load_current_platform_counts()` function
3. Rewrite `write_platform_batch()` to use batch DataFrame directly:

```python
def write_platform_batch(batch_df: DataFrame, batch_id: int) -> None:
    del batch_id
    rows = batch_df.collect()
    if not rows:
        return
    payload = [{"name": str(row["name"]), "value": int(row["value"] or 0)} for row in rows]
    payload.sort(key=lambda item: item["name"])
    NexusRedisWriter().write_json(REDIS_KEY_PLATFORM_BREAKDOWN, payload, channel=CHANNEL_PLATFORM)
```

4. Remove all Postgres imports

### Changes to `derived_analytics.py`

```python
# BEFORE:
from streaming.kafka_sources import read_postgres_table_snapshot, read_sessions
from streaming.transforms.device_platform import seed_platform_breakdown, start_device_platform_aggregator

def main() -> None:
    spark = create_spark_session("nexus-derived")
    sessions = read_sessions(spark)
    users_snapshot = read_postgres_table_snapshot(spark, "users")
    seed_platform_breakdown(users_snapshot)
    queries = [start_device_platform_aggregator(sessions)]
    spark.streams.awaitAnyTermination()

# AFTER:
from streaming.kafka_sources import read_sessions
from streaming.transforms.device_platform import start_device_platform_aggregator

def main() -> None:
    spark = create_spark_session("nexus-derived")
    sessions = read_sessions(spark)
    queries = [start_device_platform_aggregator(sessions)]
    spark.streams.awaitAnyTermination()
```

---

## Phase 5 -- Alert Evaluator Decision

### Current State

The alert evaluator (`alert_evaluator.py`) is currently **not wired** into any streaming job after the duplication fix. The KPI aggregator's `_write_alerts()` function solely owns alert Redis state.

### Options

| Option | Pros | Cons |
|--------|------|------|
| **A. Keep current** (KPI aggregator owns alerts) | Simple, already working, no new streaming query | No stateful pending→firing transition, `db.cpu.percent` rule always shows `pending` because KPI aggregator doesn't have system metrics |
| **B. Re-enable evaluator downstream of `aggregated.kpis` Kafka topic** | Proper separation of concerns, can implement stateful consecutive-breach logic, can source `db.cpu.percent` from health data | Adds a streaming query to the derived job, increases complexity |
| **C. Move alert logic into infrastructure job** | Has access to system metrics for `db.cpu.percent`, also reads `aggregated.kpis` from Kafka | Mixes concerns, infrastructure job currently only handles raw topics |

**Recommendation**: Option A for now. The 3-rule alert system works and the dashboard displays correctly. Re-enable Option B in a future iteration if stateful alert evaluation is needed.

---

## Phase 6 -- Validation

### 6.1 Pre-Validation Checklist

- [ ] All schema changes applied (StructType, Avro, DDL)
- [ ] Generator populates new fields in orders, user_events, request_log
- [ ] All JDBC calls removed from hot-path `foreachBatch` callbacks
- [ ] No `read_postgres_table_snapshot` usage in streaming job entry points (except if needed for one-time broadcast)
- [ ] `seed_platform_breakdown()` removed
- [ ] Activity enricher uses `user_display_name` instead of placeholder

### 6.2 End-to-End Test Protocol

```bash
# 1. Clean slate
docker compose down -v

# 2. Start stack
docker compose up -d

# 3. Wait for services (Kafka, Schema Registry, Debezium, Spark)
# ~60-90 seconds for full startup

# 4. Run 90-second generation
python scripts/generate_test_data.py --preset light --duration 90

# 5. During and after generation, verify:
```

### 6.3 Verification Points

| Check | Command / Endpoint | Expected |
|-------|-------------------|----------|
| Generator completes | Exit code 0, duration ≤ ~97s | No hang, no timeout |
| Postgres has new columns | `\d orders`, `\d user_events` | `user_display_name`, `platform`, etc. present |
| Orders have denormalized data | `SELECT user_display_name, platform FROM orders LIMIT 5` | Non-null values |
| User events have denormalized data | `SELECT user_display_name, region_name, city, amount FROM user_events LIMIT 5` | Non-null for applicable rows |
| KPI endpoint | `GET /api/metrics` | `activeUsers > 0`, `revenue > 0`, `orders > 0` |
| Traffic endpoint | `GET /api/traffic` | Array with recent data points |
| Activity endpoint | `GET /api/activities` | `user` field shows display names (not "User 42") |
| Regions endpoint | `GET /api/regions` | 9 regions with `sales > 0` for active regions |
| Flows endpoint | `GET /api/flows` | Array with flow entries |
| Platform endpoint | `GET /api/platform` | Array with Desktop/Mobile/iOS/Android counts |
| Alerts endpoint | `GET /api/alerts` | 3 rules, correct structure |
| Health endpoint | `GET /api/health` | CPU, memory values |
| Geo endpoint | `GET /api/geo` | Header metrics |
| SSE delivers events | `GET /events` | `platform`, `activity`, `kpi` events arrive live |
| No JDBC in Spark logs | `docker logs spark-job-transactions 2>&1 \| grep -i jdbc` | No JDBC connection during streaming (only at startup if any broadcast loads) |
| Spark job lag | Spark UI or log timestamps | Trigger delay ≤ 15s (down from 50-100s) |

### 6.4 Baseline Comparison

Compare against pre-migration baseline from last successful 90s test:

| Metric | Pre-Migration | Post-Migration Target |
|--------|-------------|---------------------|
| Generator duration | ~97s | ≤ 100s |
| Spark trigger delay | 50-100s | ≤ 15s |
| All 9 API endpoints updated | Yes | Yes |
| SSE events delivered | Yes (`platform`, `activity`) | Yes (all event types) |
| Activity feed `user` field | "User {id}" placeholder | Real display names |
| Activity feed `amount` | Hardcoded 149.99 | Real order amounts |
| Alert structure | 3 rules, correct | 3 rules, correct |

---

## File Change Manifest

### Must Modify

| File | Changes | Phase |
|------|---------|-------|
| `src/streaming/schemas.py` | Add fields to `ORDERS_SCHEMA`, `ORDERS_AVRO_SCHEMA`, `USER_EVENTS_SCHEMA`, `USER_EVENTS_AVRO_SCHEMA`, `REQUEST_LOG_SCHEMA`, `REQUEST_LOG_AVRO_SCHEMA` | 1 |
| `scripts/generate_test_data.py` | Add denormalized fields to orders INSERT, user_events INSERT, request_log Kafka payload and schema | 1 |
| `src/streaming/transforms/kpi_aggregator.py` | Remove `_load_current_business_kpis()`, remove JDBC call in `write_kpi_batch()`, remove Postgres imports | 2 |
| `src/streaming/transforms/region_aggregator.py` | Remove `_load_sales_by_region()`, use stream `sales` in `write_region_batch()`, remove Postgres imports | 2 |
| `src/streaming/transforms/device_platform.py` | Remove `seed_platform_breakdown()`, `_load_current_platform_counts()`, rewrite `write_platform_batch()`, remove Postgres imports | 2, 4 |
| `src/streaming/transforms/activity_enricher.py` | Use `user_display_name` from stream, real amounts, proper location. Optionally switch source to `user_events` CDC | 3 |
| `src/streaming/jobs/transaction_analytics.py` | Remove `read_postgres_table_snapshot` calls, update `start_activity_enricher` call | 2, 3 |
| `src/streaming/jobs/derived_analytics.py` | Remove `read_postgres_table_snapshot`, remove `seed_platform_breakdown` | 4 |
| `src/streaming/kafka_sources.py` | No functional change needed (schemas are updated in `schemas.py`, readers reference them). Consider removing `read_postgres_table_snapshot()` if no longer used anywhere. | 2 |

### Postgres DDL

| File | Changes | Phase |
|------|---------|-------|
| `postgres/init.sql` (or equivalent) | Add new columns to `CREATE TABLE orders`, `CREATE TABLE user_events` | 0-1 |

### No Change Required

| File | Reason |
|------|--------|
| `src/streaming/config.py` | Redis keys, topics, windows unchanged |
| `src/streaming/redis_client.py` | Writer helpers unchanged |
| `src/streaming/jobs/infrastructure_analytics.py` | Already uses direct Kafka, no JDBC |
| `src/streaming/transforms/traffic_builder.py` | No JDBC dependency |
| `src/streaming/transforms/health_aggregator.py` | No JDBC dependency |
| `src/streaming/transforms/geo_header.py` | No JDBC dependency |
| `src/api/routes/snapshots.py` | Dashboard contract frozen |
| `src/api/services/redis_service.py` | Dashboard contract frozen |
| `src/api/routes/events.py` | Dashboard contract frozen |
| `FLOW.md` | Update after migration is validated |
| `DESCRIPTION.md` | Reference document, no code changes |

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Avro schema incompatibility after adding fields | Spark fails to decode messages | Phase 0 clean slate wipes Schema Registry; new schemas register fresh. All new fields are nullable with defaults. |
| Stale checkpoint conflicts | `StateSchemaNotCompatible` errors | Phase 0 wipes all checkpoints (`docker compose down -v`). |
| Generator SQL string escaping | Display names with apostrophes break INSERT | Use parameterized queries or escape single quotes in display names. |
| Stream-only KPIs show lower numbers than JDBC totals | Dashboard shows windowed counts (e.g., 50 orders) instead of cumulative (e.g., 1800 orders) | This is the correct semantic for a real-time dashboard. The previous JDBC approach was masking stale data as "real-time". If cumulative is desired, maintain a Redis counter that accumulates deltas. |
| `outputMode("complete")` on region/platform queries | Full state recomputation each batch can be slow as state grows | Monitor after JDBC removal. If still slow, switch to `update` mode with explicit state management. This is a future optimization, not a blocker. |
| Activity enricher source switch (request_log → user_events) | Different event semantics, may miss request-level activity | Keep request_log as fallback. user_events provides richer data per DESCRIPTION.md design. Can union both sources if needed. |

---

## Execution Order Summary

```
Phase 0: docker compose down -v (clean slate)
    |
Phase 1: Schema changes (schemas.py, DDL, generator)
    |
Phase 2: Remove JDBC from kpi_aggregator, region_aggregator, device_platform
    |     Update transaction_analytics.py, derived_analytics.py entry points
    |
Phase 3: Upgrade activity_enricher to use denormalized fields
    |
Phase 4: Final cleanup of derived_analytics.py (remove seed, snapshot)
    |
Phase 5: Alert evaluator -- no change (keep Option A)
    |
Phase 6: docker compose up -d → generate 90s → verify all endpoints
```

Phases 1-4 can be implemented as a single commit since they are interdependent (schema changes must align with both producer and consumer code).
