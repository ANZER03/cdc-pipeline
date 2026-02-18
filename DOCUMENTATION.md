# EBAP — Documentation

> This file is updated after each phase is implemented and tested successfully.
> It serves as the living reference for what was built, how it works, and how to use it.

---

## Table of Contents

- [Phase 1: Core Infrastructure](#phase-1-core-infrastructure)
- [Phase 2: Schema Registry](#phase-2-schema-registry)
- [Phase 3: PostgreSQL + CDC + Iceberg Catalog](#phase-3-postgresql--cdc--iceberg-catalog)
- [Phase 4: Storage Layer](#phase-4-storage-layer)
- [Phase 5: Stream Processing](#phase-5-stream-processing)
- [Phase 6: Batch Processing](#phase-6-batch-processing)
- [Phase 7: Serving Layer (Trino)](#phase-7-serving-layer-trino)
- [Phase 8: Visualization (Grafana)](#phase-8-visualization-grafana)
- [Phase 9: Orchestration](#phase-9-orchestration)
- [Phase 10: Validation](#phase-10-validation)

---

<!-- Phases will be documented below as they are completed -->

## Phase 1: Core Infrastructure

**Status:** COMPLETED
**Date:** 2026-02-18

### What was built

- **Kafka broker** in KRaft mode (no Zookeeper) using `confluentinc/cp-kafka:7.7.7`
- **Shared bridge network** `ebap-net` for all EBAP services
- **Named volume** `kafka-data` for persistent broker storage
- **kafka-init** container that creates all EBAP topics on startup

### Services

| Service | Container | Image | Ports |
|---|---|---|---|
| kafka | ebap-kafka | `confluentinc/cp-kafka:7.7.7` | `9092` (external), `29092` (internal) |
| kafka-init | ebap-kafka-init | `confluentinc/cp-kafka:7.7.7` | — (exits after topic creation) |

### Kafka Configuration

- **Mode:** KRaft (combined broker + controller, node ID 1)
- **Cluster ID:** `MkU3OEVBNTcwNTJENDM2Qk`
- **Listeners:**
  - `PLAINTEXT://kafka:9092` — inter-container communication
  - `PLAINTEXT_HOST://localhost:29092` — host machine access
  - `CONTROLLER://kafka:29093` — KRaft quorum
- **Log retention:** 7 days, 1 GB segment size
- **Healthcheck:** `kafka-topics --bootstrap-server kafka:9092 --list` (5s interval, 10 retries)

### Topics Created

| Topic | Partitions | Purpose |
|---|---|---|
| `ebap.events.raw` | 6 | User clickstream events |
| `ebap.metrics.telemetry` | 6 | System health metrics |
| `ebap.cdc.users` | 3 | CDC stream from PostgreSQL users table |
| `ebap.audit.logs` | 1 | Trino query audit trail |

### How to Run

```bash
cd test/
docker compose up -d
docker wait ebap-kafka-init   # wait for topics to be created
```

### How to Verify

```bash
# List topics
docker exec ebap-kafka kafka-topics --bootstrap-server kafka:9092 --list

# Describe a topic
docker exec ebap-kafka kafka-topics --bootstrap-server kafka:9092 --describe --topic ebap.events.raw

# Produce/consume round-trip test
echo '{"test":"message"}' | docker exec -i ebap-kafka kafka-console-producer --bootstrap-server kafka:9092 --topic ebap.events.raw
docker exec ebap-kafka kafka-console-consumer --bootstrap-server kafka:9092 --topic ebap.events.raw --from-beginning --max-messages 1 --timeout-ms 10000
```

### Test Results

- Kafka broker: healthy (KRaft mode, node ID 1)
- All 4 topics created with correct partition counts
- Produce/consume round-trip: message written and read back successfully
- Network `ebap-net`: broker reachable at `172.19.0.2`

---

## Phase 2: Schema Registry

**Status:** COMPLETED
**Date:** 2026-02-18

### What was built

- **Confluent Schema Registry** (`confluentinc/cp-schema-registry:7.7.7`) for centralized schema governance
- Supports **Avro**, **JSON Schema**, and **Protobuf** serialization formats
- Default compatibility level set to **BACKWARD** (safe schema evolution)
- Healthcheck via `curl -f http://localhost:8081/subjects`

### Services

| Service | Container | Image | Ports |
|---|---|---|---|
| schema-registry | ebap-schema-registry | `confluentinc/cp-schema-registry:7.7.7` | `8081` (REST API) |

### Configuration

- **Kafka bootstrap:** `kafka:9092` (uses the internal `PLAINTEXT` listener)
- **Listener:** `http://0.0.0.0:8081`
- **Compatibility:** `BACKWARD` (consumers using old schema can read data written with new schema)
- **Depends on:** `kafka` (service_healthy condition)
- **Restart policy:** `unless-stopped`

### REST API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/subjects` | GET | List all registered subjects |
| `/subjects/{subject}/versions` | POST | Register a new schema version |
| `/subjects/{subject}/versions/{version}` | GET | Retrieve a specific schema version |
| `/config` | GET | Get global compatibility level |
| `/schemas/types` | GET | List supported schema types |

### How to Run

```bash
cd test/
docker compose up -d
# Wait for Schema Registry to become healthy
docker compose ps   # Check "healthy" status for schema-registry
```

### How to Verify

```bash
# Check Schema Registry is responding
curl -s http://localhost:8081/subjects

# Check global compatibility level
curl -s http://localhost:8081/config

# Check supported schema types
curl -s http://localhost:8081/schemas/types

# Register a test schema (Avro example)
curl -s -X POST -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  --data '{"schema": "{\"type\":\"record\",\"name\":\"Test\",\"fields\":[{\"name\":\"id\",\"type\":\"string\"}]}"}' \
  http://localhost:8081/subjects/test-subject/versions

# Retrieve it back
curl -s http://localhost:8081/subjects/test-subject/versions/1
```

### Test Results

- Schema Registry: healthy, connected to Kafka broker
- Compatibility level: BACKWARD (confirmed via `/config`)
- Supported types: JSON, PROTOBUF, AVRO
- Schema registration: successfully registered and retrieved an Avro schema
- Schema deletion: soft and permanent delete both work
- Subjects list: correctly reflects registered/deleted schemas

---

## Phase 3: PostgreSQL + CDC + Iceberg Catalog

**Status:** COMPLETED
**Date:** 2026-02-18

### What was built

- **PostgreSQL** (`debezium/postgres:15`) with dual-role configuration:
  - `ebap_db` — application database with `users` table (CDC source)
  - `iceberg_catalog` — JDBC catalog database for Iceberg metadata (used by Spark + Trino later)
- **Debezium Kafka Connect** (`debezium/connect:2.3`) for CDC from PostgreSQL to Kafka
- **debezium-init** container that auto-registers the CDC connector on startup
- **Init scripts:** `00-create-databases.sh` (creates `iceberg_catalog` DB) + `01-seed-postgres.sql` (creates `users` table, seeds 10 rows, creates CDC publication)
- **Topic routing:** RegexRouter transform maps `ebap.cdc.public.users` -> `ebap.cdc.users`

### Services

| Service | Container | Image | Ports |
|---|---|---|---|
| postgres | ebap-postgres | `debezium/postgres:15` | `5432` |
| debezium-connect | ebap-debezium-connect | `debezium/connect:2.3` | `8083` (REST API) |
| debezium-init | ebap-debezium-init | `curlimages/curl:latest` | — (exits after registration) |

### PostgreSQL Configuration

- **User/Password:** `admin` / `admin`
- **Databases:**
  - `ebap_db` — default database (set via `POSTGRES_DB`)
  - `iceberg_catalog` — created by `00-create-databases.sh`
- **WAL level:** `logical` (enabled by `debezium/postgres` image)
- **Publication:** `ebap_publication` for `users` table
- **Named volume:** `postgres-data` for persistence

### Users Table Schema

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PRIMARY KEY | Auto-increment |
| user_id | VARCHAR(64) UNIQUE | Business key (e.g., `usr_001`) |
| username | VARCHAR(128) | Display name |
| email | VARCHAR(256) | Email address |
| tier | VARCHAR(32) | `free`, `premium`, `enterprise` |
| region | VARCHAR(64) | AWS region format |
| created_at | TIMESTAMP | Auto-set on insert |
| updated_at | TIMESTAMP | Updated manually on change |

### Debezium Connector Configuration

- **Connector name:** `ebap-postgres-cdc`
- **Plugin:** `pgoutput` (native PostgreSQL logical replication)
- **Slot:** `ebap_slot`
- **Publication:** `ebap_publication`
- **Topic prefix:** `ebap.cdc`
- **Target topic:** `ebap.cdc.users` (via RegexRouter transform)
- **Converters:** JSON (schemas disabled for readability)
- **Connect storage topics:** `ebap.connect.configs`, `ebap.connect.offsets`, `ebap.connect.statuses`

### How to Run

```bash
cd test/
docker compose up -d
# Wait for all services — debezium-init exits after registering connector
docker compose ps -a
```

### How to Verify

```bash
# Check databases exist
docker exec ebap-postgres psql -U admin -d ebap_db -c "\l" | grep -E "ebap_db|iceberg_catalog"

# Check users table
docker exec ebap-postgres psql -U admin -d ebap_db -c "SELECT * FROM users;"

# Check Debezium connector status
curl -s http://localhost:8083/connectors/ebap-postgres-cdc/status | python3 -m json.tool

# Read CDC events from Kafka
docker exec ebap-kafka kafka-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic ebap.cdc.users \
  --from-beginning --max-messages 5 --timeout-ms 10000

# Test live CDC: insert a new user and verify it appears
docker exec ebap-postgres psql -U admin -d ebap_db -c \
  "INSERT INTO users (user_id, username, email, tier, region) VALUES ('usr_test', 'test_user', 'test@example.com', 'free', 'us-east-1');"
# Then consume from the topic again to see the new event
```

### Test Results

- PostgreSQL: healthy, both `ebap_db` and `iceberg_catalog` databases created
- Users table: 10 seed rows inserted successfully
- Publication: `ebap_publication` active on `users` table
- Debezium Connect: healthy, connector `ebap-postgres-cdc` RUNNING
- CDC initial snapshot: all 10 users captured on `ebap.cdc.users` topic (`op=r`)
- CDC live INSERT: new user `usr_011` captured on topic (`op=c`)
- CDC live UPDATE: tier change for `usr_002` captured with before/after values (`op=u`)

---

## Phase 4: Storage Layer

**Status:** COMPLETED
**Date:** 2026-02-18

### What was built

- **Redis** (`redis:7-alpine`) — hot storage for real-time metrics with RDB persistence
- **MinIO** (`minio/minio:latest`) — S3-compatible object storage for the data lakehouse
- **MinIO Init** (`minio/mc:latest`) — init container that creates the 4 lakehouse buckets on startup
- **Named volumes** `redis-data` and `minio-data` for persistence

### Services

| Service | Container | Image | Ports |
|---|---|---|---|
| redis | ebap-redis | `redis:7-alpine` | `6379` (Redis protocol) |
| minio | ebap-minio | `minio/minio:latest` | `9000` (S3 API), `9001` (Console UI) |
| minio-init | ebap-minio-init | `minio/mc:latest` | — (exits after bucket creation) |

### Redis Configuration

- **Version:** 7.4.7
- **Persistence:** RDB snapshot every 60s if at least 1 key changed (`--save 60 1`)
- **Memory limit:** 256 MB with LRU eviction (`--maxmemory 256mb --maxmemory-policy allkeys-lru`)
- **Log level:** `warning` (minimal noise)
- **Healthcheck:** `redis-cli ping` (5s interval, 5 retries)
- **Volume:** `redis-data:/data`
- **Restart policy:** `unless-stopped`

### MinIO Configuration

- **Credentials:** `admin` / `password`
- **S3 API:** `http://minio:9000` (inter-container) / `http://localhost:9000` (host)
- **Console:** `http://localhost:9001`
- **Healthcheck:** `curl -f http://localhost:9000/minio/health/live` (10s interval, 5 retries)
- **Volume:** `minio-data:/data`
- **Restart policy:** `unless-stopped`

### Buckets Created

| Bucket | Purpose |
|---|---|
| `ebap-bronze` | Raw ingested data (landing zone) |
| `ebap-silver` | Cleansed/transformed Iceberg tables (main warehouse) |
| `ebap-gold` | Aggregated/business-ready datasets |
| `ebap-checkpoints` | Spark Structured Streaming checkpoint state |

### How to Run

```bash
docker compose up -d redis minio
# Wait for both to become healthy
docker compose up -d minio-init
# Check init logs
docker logs ebap-minio-init
```

### How to Verify

```bash
# Redis: PING test
docker exec ebap-redis redis-cli ping
# Expected: PONG

# Redis: SET/GET round-trip
docker exec ebap-redis redis-cli SET test:key "hello" EX 60
docker exec ebap-redis redis-cli GET test:key
# Expected: hello

# MinIO: Health check
curl -s http://localhost:9000/minio/health/live
curl -s http://localhost:9000/minio/health/ready

# MinIO: List buckets
docker run --rm --network ebap-net --entrypoint /bin/sh minio/mc \
  -c "mc alias set myminio http://minio:9000 admin password && mc ls myminio/"
# Expected: ebap-bronze/, ebap-silver/, ebap-gold/, ebap-checkpoints/

# MinIO Console: http://localhost:9001 (login: admin / password)
```

### Test Results

- Redis: healthy, version 7.4.7, PING/SET/GET/DEL all working
- MinIO: healthy, live and ready endpoints responding
- MinIO Init: all 4 buckets (`ebap-bronze`, `ebap-silver`, `ebap-gold`, `ebap-checkpoints`) created successfully
- All pre-existing services (Kafka, Schema Registry, PostgreSQL, Debezium, Kafka UI) remain healthy
- Total running services: 7 (all healthy)
