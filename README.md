# Nexus CDC Pipeline

Real-time e-commerce analytics pipeline built on Change Data Capture. PostgreSQL row changes are captured by Debezium, streamed through Kafka, aggregated by three Spark Structured Streaming jobs, and served from Redis via a FastAPI WebSocket endpoint to the [Nexus Dashboard](../nexus-dash/e-commerce-nexus-dashboard/).

See [`FLOW.md`](FLOW.md) for full architecture details, data flow diagrams, and operational notes.

## Stack

| Component | Technology |
|---|---|
| Source database | PostgreSQL 16 |
| CDC connector | Debezium 2.x (Kafka Connect) |
| Schema registry | Confluent Schema Registry |
| Message broker | Kafka (KRaft mode) |
| Stream processing | Apache Spark 3.5 Structured Streaming (3 jobs) |
| State store | Redis 7 |
| API | FastAPI (REST snapshots + WebSocket push) |

## Quick Start

Start the full stack:

```bash
docker compose up -d
```

Once all services are healthy, start the data generator:

```bash
docker compose exec nexus-data-generator python generate_test_data.py --preset demo
```

The pipeline is live when all 12 Redis keys are populated. You can verify:

```bash
docker compose exec nexus-redis redis-cli keys "nexus:*"
```

## Service Ports

| Service | URL |
|---|---|
| Kafka UI | http://localhost:8084 |
| Spark Master UI | http://localhost:8080 |
| Spark Worker 1 UI | http://localhost:8091 |
| Spark Worker 2 UI | http://localhost:8092 |
| Spark Job: nexus-transactions | http://localhost:4040 |
| Spark Job: nexus-infrastructure | http://localhost:4041 |
| Spark Job: nexus-derived | http://localhost:4042 |
| FastAPI (REST + WebSocket) | http://localhost:8000 |
| Redis | localhost:6379 |

## API Endpoints

The dashboard connects via WebSocket at `ws://localhost:8000/ws`. On connect it receives a full snapshot of all 9 data types, then incremental updates as Redis pub/sub fires.

REST snapshot endpoints are also available at `/api/metrics`, `/api/traffic`, `/api/activities`, `/api/regions`, `/api/flows`, `/api/alerts`, `/api/platform`, `/api/health`, and `/api/geo`.

## Tear Down

```bash
docker compose down -v
```
