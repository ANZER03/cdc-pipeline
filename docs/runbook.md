# Nexus Pipeline — Essential Commands

## 1. Start the Full Stack

```sh
docker compose up -d
```

## 2. Start Infrastructure Only

```sh
docker compose up -d kafka-1 kafka-2 schema-registry postgres redis
```

## 3. Start CDC Services

```sh
docker compose up -d debezium-connect debezium-init
```

## 4. Start Spark Jobs

```sh
docker compose up -d spark-master spark-worker spark-job-transactions spark-job-infrastructure spark-job-derived
```

## 5. Start the API

```sh
docker compose up -d nexus-api
```

## 6. Generate Test Data

```sh
python scripts/generate_test_data.py --mode all --rate 10 --duration 300
```

## 7. Verify Services

```sh
python scripts/health_check.py
```

## 8. Verify Data (Open in Browser)

- Kafka UI: `http://localhost:8080`
- Spark Master: `http://localhost:8082`
- API docs: `http://localhost:8000/docs`
- PGAdmin: `http://localhost:5050`

## 9. Inspect Redis

```sh
docker compose exec redis redis-cli
```

## Stop Everything

```sh
docker compose down -v --remove-orphans
```

---

## Common Fixes

| Error                                       | Fix                                                        |
| ------------------------------------------- | ---------------------------------------------------------- |
| `set: illegal option -`                     | Use `tr -d '\r'` to strip CRLF (already in commands above) |
| API restarting repeatedly                   | Check `docker compose logs nexus-api` for import issues    |
| Kafka topics missing                        | Wait for `kafka-init` to finish, then inspect Kafka UI     |
| Services in `Waiting` state                 | Wait 30 seconds, then run `docker compose ps`              |

**Last Updated:** 2026-03-07
