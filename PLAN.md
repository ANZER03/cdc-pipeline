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

**Iceberg Catalog Strategy: PostgreSQL JDBC Catalog**

PostgreSQL serves as the **shared JDBC catalog** for Apache Iceberg. Both Spark and Trino
connect to the same `iceberg_catalog` database to read/write table metadata. This ensures:
- A single source of truth for table schemas, namespaces, and snapshot pointers
- No reliance on a Hive Metastore (simpler stack)
- ACID-safe metadata operations backed by PostgreSQL transactions
- Data files remain in MinIO (S3); only metadata pointers live in PostgreSQL

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

- [x] Add Schema Registry service (`confluentinc/cp-schema-registry:7.7.7`)
  - [x] Connect to Kafka broker (`SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS`)
  - [x] Expose port `8081`
  - [x] Add healthcheck
  - [x] Set `depends_on: kafka` with health condition

## Phase 3: Source Database (PostgreSQL + CDC + Iceberg Catalog)

PostgreSQL serves a **dual role** in this architecture:
1. **Source database** — hosts the `users` table for CDC via Debezium
2. **Iceberg JDBC catalog** — stores Iceberg table metadata (namespaces, table pointers, snapshots) so that both Spark and Trino share a single source of truth for the lakehouse schema

- [x] Add PostgreSQL service (`debezium/postgres:15`)
  - [x] Configure `wal_level=logical` for Debezium CDC
  - [x] Expose port `5432`
  - [x] Add healthcheck (`pg_isready`)
  - [x] Mount init scripts volume (`./init-scripts/`)
  - [x] **Create two databases via init script:**
    - [x] `ebap_db` — application database (users table, CDC source)
    - [x] `iceberg_catalog` — JDBC catalog database for Iceberg metadata
  - [x] Seed `ebap_db.users` table with mock data
  - [x] Create publication for Debezium CDC on `users` table
- [x] Add Kafka Connect / Debezium service (`debezium/connect:2.3`)
  - [x] Set `BOOTSTRAP_SERVERS: kafka:9092`
  - [x] Configure connector storage topics (configs, offsets, statuses)
  - [x] Expose REST API on port `8083`
  - [x] Set `depends_on: [kafka, postgres]` with health conditions
- [x] Create Debezium connector init container or script
  - [x] POST connector JSON config to `http://debezium-connect:8083/connectors`
  - [x] Monitor `ebap.cdc.users` topic for user profile changes

## Phase 4: Storage Layer

### Hot Storage
- [x] Add Redis service (`redis:7-alpine`)
  - [x] Expose port `6379`
  - [x] Add healthcheck (`redis-cli ping`)
  - [x] Configure `maxmemory` policy for TTL eviction

### Cold Storage (Data Lakehouse)
- [x] Add MinIO service (`minio/minio:latest`)
  - [x] Expose API port `9000` and console port `9001`
  - [x] Set `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`
  - [x] Add healthcheck (`curl /minio/health/live`)
- [x] Add MinIO client (`mc`) init container
  - [x] Create buckets: `ebap-bronze`, `ebap-silver`, `ebap-gold`
  - [x] Create bucket for Spark checkpoints: `ebap-checkpoints`
  - [x] Set `depends_on: minio` with health condition

## Phase 5: Stream Processing (Spark Structured Streaming)

- [ ] Update `test/Dockerfile` to include Redis client JAR (`jedis` or `spark-redis`)
- [ ] Update `test/Dockerfile` to include PostgreSQL JDBC driver (`postgresql-42.x.jar`) for Iceberg JDBC catalog
- [ ] Add Spark Master service (`custom-spark:latest`)
  - [ ] Run as Spark master node
  - [ ] Expose Spark UI on port `8080`
  - [ ] Configure S3A/MinIO endpoint and credentials via environment
  - [ ] Configure Iceberg with JDBC catalog:
    - [ ] `spark.sql.catalog.ebap = org.apache.iceberg.spark.SparkCatalog`
    - [ ] `spark.sql.catalog.ebap.catalog-impl = org.apache.iceberg.jdbc.JdbcCatalog`
    - [ ] `spark.sql.catalog.ebap.uri = jdbc:postgresql://postgres:5432/iceberg_catalog`
    - [ ] `spark.sql.catalog.ebap.jdbc.user = admin`
    - [ ] `spark.sql.catalog.ebap.jdbc.password = admin`
    - [ ] `spark.sql.catalog.ebap.warehouse = s3a://ebap-silver/`
    - [ ] `spark.sql.catalog.ebap.io-impl = org.apache.iceberg.aws.s3.S3FileIO`
    - [ ] `spark.sql.catalog.ebap.s3.endpoint = http://minio:9000`
  - [ ] Set `depends_on: [kafka, minio, redis, postgres]` with health conditions
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
  - [ ] Configure Iceberg with JDBC catalog (same config as streaming Spark):
    - [ ] `spark.sql.catalog.ebap.catalog-impl = org.apache.iceberg.jdbc.JdbcCatalog`
    - [ ] `spark.sql.catalog.ebap.uri = jdbc:postgresql://postgres:5432/iceberg_catalog`
    - [ ] `spark.sql.catalog.ebap.warehouse = s3a://ebap-silver/`
  - [ ] Set `depends_on: [minio, postgres]` with health condition
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
    - [ ] Set `iceberg.catalog.type=jdbc`
    - [ ] Set `iceberg.jdbc-catalog.catalog-name=ebap`
    - [ ] Set `iceberg.jdbc-catalog.driver-class=org.postgresql.Driver`
    - [ ] Set `iceberg.jdbc-catalog.connection-url=jdbc:postgresql://postgres:5432/iceberg_catalog`
    - [ ] Set `iceberg.jdbc-catalog.connection-user=admin`
    - [ ] Set `iceberg.jdbc-catalog.connection-password=admin`
    - [ ] Set `iceberg.jdbc-catalog.default-warehouse-dir=s3a://ebap-silver/`
    - [ ] Set S3/MinIO endpoint and credentials (`hive.s3.*`)
  - [ ] Mount PostgreSQL JDBC driver into Trino plugin directory
  - [ ] Set `depends_on: [minio, postgres]` with health condition
- [ ] Validate Trino reads the same Iceberg tables written by Spark (shared JDBC catalog)
- [ ] Verify namespace and table metadata is visible in `iceberg_catalog` PostgreSQL database

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
  postgres (first — hosts CDC source + Iceberg catalog DB)
    → kafka → schema-registry → kafka-connect
    → spark-streaming (needs kafka + minio + redis + postgres)
    → spark-batch (needs minio + postgres)
  minio → mc-init
  trino (needs minio + postgres for JDBC catalog)
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
