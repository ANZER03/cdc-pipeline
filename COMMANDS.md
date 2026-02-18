# EBAP Pipeline — Essential Commands

## 1. Build Spark Image

```cmd
docker build -t custom-spark:latest .
```

## 2. Start Core Services

```cmd
docker compose up -d kafka kafka-2 postgres debezium-connect redis minio spark-master-streaming spark-worker minio-init
```

## 3. Create Kafka Topics

```cmd
docker compose run --rm --no-deps --entrypoint bash kafka-init -lc "tr -d '\r' < /scripts/create-topics.sh | bash"
```

## 4. Register Debezium Connector

```cmd
docker compose run --rm --no-deps --entrypoint sh debezium-init -c "tr -d '\r' < /scripts/register-debezium.sh | sh"
```

## 5. Create Iceberg Catalog Database

```cmd
docker exec -it ebap-postgres psql -U admin -d postgres -c "CREATE DATABASE iceberg_catalog OWNER admin;"
```

## 6. Seed PostgreSQL Users Table

```cmd
docker exec -i ebap-postgres sh -c "tr -d '\r' < /dev/stdin | psql -U admin -d ebap_db" < init-scripts/seed-postgres.sql
```

## 7. Produce Test Events

```cmd
(echo {"id":"evt-001","user_id":"usr_001","action":"purchase","metadata":{"amount":"99.99","item_id":"item-123"},"location":"us-east-1","timestamp":"2026-02-18T12:00:00Z"}) | docker exec -i ebap-kafka kafka-console-producer --bootstrap-server localhost:9092 --topic ebap.events.raw
```

Run the same command again with different `id`/`action`/`amount` values to send more events.

## 8. Start Spark Streaming Job

```cmd
docker compose up --no-deps spark-streaming-submit
```

## 9. Verify Data (Open in Browser)

- Kafka UI: `http://localhost:8084`
- Spark Master: `http://localhost:8082`
- Spark App: `http://localhost:4040`
- MinIO: `http://localhost:9001` (login: admin/password)

## 10. Check Redis KPIs

```cmd
docker exec ebap-redis redis-cli GET kpi:total_revenue
```

## Stop Everything

```cmd
docker compose down -v
```

---

## Common Fixes

| Error                                       | Fix                                                        |
| ------------------------------------------- | ---------------------------------------------------------- |
| `set: illegal option -`                     | Use `tr -d '\r'` to strip CRLF (already in commands above) |
| `database "iceberg_catalog" does not exist` | Run command #5                                             |
| `relation "users" already exists`           | Continue (harmless)                                        |
| Services in `Waiting` state                 | Wait 30 seconds, check: `docker compose ps`                |

**Last Updated:** 2026-02-18
