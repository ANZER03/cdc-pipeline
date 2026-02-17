# PLAN: Docker Compose Infrastructure for EBAP Architecture

**Goal:** Update `test/docker-compose.yml` to implement the full EBAP architecture as defined in the diagram (`ebap_architecture.png`).

**Base images (matching current stack):**

| Component | Image |
|---|---|
| Kafka (KRaft) | `confluentinc/cp-kafka:7.7.7` |
| Schema Registry | `confluentinc/cp-schema-registry:7.7.7` |
| Kafka Connect (Debezium) | `debezium/connect:2.3` |
| PostgreSQL | `debezium/postgres:15` |
| Spark (custom) | `custom-spark:latest` (from `test/Dockerfile`) |
| MinIO | `minio/minio:latest` |
| Trino | `trinodb/trino:latest` |
| Redis | `redis:7-alpine` |
| Grafana | `grafana/grafana:latest` |

---

## Phase 1: Core Infrastructure (Network & Coordination)

- [ ] Define a shared bridge network (`ebap-net`) for all services
- [ ] Configure Kafka broker in KRaft mode (no Zookeeper) with `confluentinc/cp-kafka:7.7.7`
  - [ ] Set `KAFKA_PROCESS_ROLES: 'broker,controller'`
  - [ ] Set `KAFKA_CONTROLLER_QUORUM_VOTERS`
  - [ ] Configure dual listeners (internal `PLAINTEXT` + external `PLAINTEXT_HOST`)
  - [ ] Set `CLUSTER_ID` for KRaft initialization
  - [ ] Add healthcheck (`kafka-topics --bootstrap-server`)
- [ ] Create Kafka topics on startup via an init container or script:
  - [ ] `ebap.events.raw` (partitions: 6)
  - [ ] `ebap.metrics.telemetry` (partitions: 6)
  - [ ] `ebap.cdc.users` (partitions: 3)
  - [ ] `ebap.audit.logs` (partitions: 1)

## Phase 2: Schema Registry & Governance

- [ ] Add Schema Registry service (`confluentinc/cp-schema-registry:7.7.7`)
  - [ ] Connect to Kafka broker (`SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS`)
  - [ ] Expose port `8081`
  - [ ] Add healthcheck
  - [ ] Set `depends_on: kafka` with health condition

## Phase 3: Source Database (PostgreSQL + CDC)

- [ ] Add PostgreSQL service (`debezium/postgres:15`)
  - [ ] Configure `wal_level=logical` for Debezium CDC
  - [ ] Seed `users` table via init script (mount `./init-scripts/` volume)
  - [ ] Expose port `5432`
  - [ ] Add healthcheck (`pg_isready`)
- [ ] Add Kafka Connect / Debezium service (`debezium/connect:2.3`)
  - [ ] Set `BOOTSTRAP_SERVERS: kafka:9092`
  - [ ] Configure connector storage topics (configs, offsets, statuses)
  - [ ] Expose REST API on port `8083`
  - [ ] Set `depends_on: [kafka, postgres]` with health conditions
- [ ] Create Debezium connector init container or script
  - [ ] POST connector JSON config to `http://debezium-connect:8083/connectors`
  - [ ] Monitor `ebap.cdc.users` topic for user profile changes

## Phase 4: Storage Layer

### Hot Storage
- [ ] Add Redis service (`redis:7-alpine`)
  - [ ] Expose port `6379`
  - [ ] Add healthcheck (`redis-cli ping`)
  - [ ] Configure `maxmemory` policy for TTL eviction

### Cold Storage (Data Lakehouse)
- [ ] Add MinIO service (`minio/minio:latest`)
  - [ ] Expose API port `9000` and console port `9001`
  - [ ] Set `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`
  - [ ] Add healthcheck (`curl /minio/health/live`)
- [ ] Add MinIO client (`mc`) init container
  - [ ] Create buckets: `ebap-bronze`, `ebap-silver`, `ebap-gold`
  - [ ] Create bucket for Spark checkpoints: `ebap-checkpoints`
  - [ ] Set `depends_on: minio` with health condition

## Phase 5: Stream Processing (Spark Structured Streaming)

- [ ] Update `test/Dockerfile` to include Redis client JAR (`jedis` or `spark-redis`)
- [ ] Add Spark Master service (`custom-spark:latest`)
  - [ ] Run as Spark master node
  - [ ] Expose Spark UI on port `8080`
  - [ ] Configure S3A/MinIO endpoint and credentials via environment
  - [ ] Configure Iceberg catalog properties
  - [ ] Set `depends_on: [kafka, minio, redis]` with health conditions
- [ ] Add Spark Worker service(s) (`custom-spark:latest`)
  - [ ] Connect to Spark Master
  - [ ] Scale: `deploy.replicas: 2` (minimum)
  - [ ] Mount streaming job scripts (`./src/streaming/`)
- [ ] Create Spark Streaming job submit container
  - [ ] Submit the structured streaming PySpark job
  - [ ] Job reads from `ebap.events.raw` and `ebap.cdc.users`
  - [ ] Dual-write: aggregated metrics → Redis, enriched events → MinIO/Iceberg
  - [ ] Set checkpoint location to `s3a://ebap-checkpoints/streaming/`

## Phase 6: Batch Processing (Spark Batch Jobs)

- [ ] Add Spark Batch Master service (`custom-spark:latest`)
  - [ ] Separate Spark master for batch workloads
  - [ ] Expose Spark UI on port `8090` (different from streaming)
  - [ ] Configure S3A/MinIO endpoint and credentials
  - [ ] Set `depends_on: [minio]` with health condition
- [ ] Add Spark Batch Worker(s) (`custom-spark:latest`)
  - [ ] Connect to batch Spark Master
  - [ ] Mount batch job scripts (`./src/batch/`)
- [ ] Mount batch file sources volume (`./data/batch-input/`)
  - [ ] CSV, JSON, Parquet, and log files land here
  - [ ] Batch jobs read from this volume, transform, and write to MinIO/Iceberg
- [ ] Create batch ETL job submit container
  - [ ] Reads files from `/data/batch-input/`
  - [ ] Cleanses, transforms, and writes to `s3a://ebap-silver/` in Iceberg format
- [ ] Create Iceberg compaction job (scheduled or manual trigger)
  - [ ] Merges small files into 128MB targets
  - [ ] Runs against Iceberg tables in MinIO

## Phase 7: Serving Layer (Trino)

- [ ] Add Trino service (`trinodb/trino:latest`)
  - [ ] Expose port `8085` (web UI + JDBC)
  - [ ] Mount catalog config: `./config/trino/iceberg.properties`
    - [ ] Set `connector.name=iceberg`
    - [ ] Set `iceberg.catalog.type=hadoop`
    - [ ] Set `hive.s3.endpoint=http://minio:9000`
    - [ ] Set S3 credentials
  - [ ] Set `depends_on: [minio]` with health condition
- [ ] Validate Trino can query Iceberg tables written by Spark

## Phase 8: Visualization (Grafana)

- [ ] Add Grafana service (`grafana/grafana:latest`)
  - [ ] Expose port `3000`
  - [ ] Mount provisioning config (`./config/grafana/provisioning/`)
  - [ ] Set `GF_SECURITY_ADMIN_PASSWORD`
- [ ] Provision Redis datasource
  - [ ] Install Redis datasource plugin (`GF_INSTALL_PLUGINS=redis-datasource`)
  - [ ] Configure connection to `redis:6379`
- [ ] Provision Trino datasource
  - [ ] Configure JDBC/SQL connection to `trino:8085`
- [ ] Create provisioned dashboards:
  - [ ] Live Panel — real-time KPIs from Redis (5s refresh)
  - [ ] Historical Panel — trends from Trino (1h cache)
  - [ ] Geo-Map Panel — regional health from Redis

## Phase 9: Init Scripts & Orchestration

- [ ] Create directory structure:
  ```
  test/
  ├── docker-compose.yml
  ├── Dockerfile
  ├── config/
  │   ├── trino/
  │   │   └── iceberg.properties
  │   ├── grafana/
  │   │   └── provisioning/
  │   │       ├── datasources/
  │   │       │   └── datasources.yml
  │   │       └── dashboards/
  │   └── debezium/
  │       └── postgres-connector.json
  ├── init-scripts/
  │   ├── create-topics.sh
  │   ├── seed-postgres.sql
  │   └── register-debezium.sh
  ├── src/
  │   ├── streaming/
  │   │   └── stream_processing.py
  │   └── batch/
  │       └── batch_etl.py
  └── data/
      └── batch-input/
          ├── sample.csv
          ├── sample.json
          └── sample.parquet
  ```
- [ ] Add `depends_on` ordering to ensure correct startup sequence:
  ```
  kafka → schema-registry → kafka-connect → postgres
                          → spark-streaming → redis
  minio → mc-init → spark-batch
                   → trino
  grafana (last, depends on redis + trino)
  ```
- [ ] Add restart policies (`restart: unless-stopped`) for long-running services
- [ ] Add named volumes for data persistence:
  - [ ] `kafka-data`
  - [ ] `minio-data`
  - [ ] `postgres-data`
  - [ ] `redis-data`
  - [ ] `grafana-data`

## Phase 10: Validation & Smoke Tests

- [ ] Verify Kafka topics are created and receiving data
- [ ] Verify Debezium is streaming CDC changes from PostgreSQL
- [ ] Verify Spark Streaming is consuming from Kafka and writing to Redis + MinIO
- [ ] Verify Spark Batch reads files and writes to Iceberg/MinIO
- [ ] Verify Trino can query Iceberg tables
- [ ] Verify Grafana dashboards display live and historical data
- [ ] Run `docker compose up` end-to-end and confirm all healthchecks pass
