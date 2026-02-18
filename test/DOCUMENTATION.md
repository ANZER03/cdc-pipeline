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
