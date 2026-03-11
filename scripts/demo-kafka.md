# Kafka & Debezium Ingestion Demo Guide

This guide provides step-by-step instructions to test the CDC (Change Data Capture) pipeline, covering **PostgreSQL -> Debezium -> Kafka**. You will learn how to perform database operations (Insert, Update, Delete) and observe the corresponding events in Kafka.

## 1. Start Ingestion Services

To start only the services required for this ingestion demo (PostgreSQL, Kafka, and Debezium), run:

```bash
docker compose up -d \
  postgres \
  kafka-1 \
  kafka-2 \
  kafka-init \
  schema-registry \
  debezium-connect \
  debezium-init \
  kafka-ui
```

Wait for the containers to be healthy. The `debezium-init` and `kafka-init` containers will run once and then exit (status: `Exited (0)`), which is normal as they are only responsible for configuration.

You can track the connector registration progress:

```bash
docker compose logs -f debezium-init
```

## 2. Prerequisites

Ensure all services are running:

```bash
docker compose ps
```

You should see `nexus-postgres`, `nexus-kafka-1`, `debezium-connect`, and `kafka-ui` in a healthy state.

## 3. Verify Setup

### Check Debezium Connector

Verify that the Debezium connector is registered and running:

```bash
curl -s http://localhost:8083/connectors/nexus-postgres-cdc/status | jq
```

Expected output:
```json
{
  "name": "nexus-postgres-cdc",
  "connector": {
    "state": "RUNNING",
    "worker_id": "..."
  },
  "tasks": [
    {
      "id": 0,
      "state": "RUNNING",
      "worker_id": "..."
    }
  ],
  "type": "source"
}
```

### Check Kafka Topics

List the topics to ensure the CDC topics exist:

```bash
docker exec -it nexus-kafka-1 kafka-topics --bootstrap-server localhost:9092 --list
```

You should see topics like `pg.public.users`, `pg.public.orders`, `pg.public.sessions`, etc.

## 4. Database Operations (PostgreSQL)

You can connect to the PostgreSQL database using the `docker exec` command:

```bash
docker exec -it nexus-postgres psql -U admin -d nexus_db
```

Once inside the SQL prompt (`nexus_db=#`), you can run the following commands.

### A. Insert a New User

```sql
INSERT INTO users (username, display_name, email, country_code, city, region_name, platform)
VALUES ('demo_user', 'Demo User', 'demo@example.com', 'US', 'New York', 'North America (East)', 'Desktop');
```

### B. Update an Existing User

Update the `platform` for the user we just created:

```sql
UPDATE users SET platform = 'Mobile' WHERE username = 'demo_user';
```

### C. Delete a User

Delete the user:

```sql
DELETE FROM users WHERE username = 'demo_user';
```

### D. Verify Data

To see the current data in the table:

```sql
SELECT id, username, display_name, country_code, region_name, platform FROM users ORDER BY id DESC LIMIT 5;
```

Exit the SQL prompt with `\q`.

## 5. Observing Changes in Kafka

You can observe the CDC events in real-time using the Kafka Console Consumer or Kafka UI.

### Option 1: Kafka Console Consumer

Open a new terminal and run:

```bash
docker exec -it nexus-kafka-1 kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic pg.public.users \
  --from-beginning
```

**What to look for:**

- **Insert**: You will see a JSON message with `"op": "c"` (create) and the `after` field containing the new user data.
- **Update**: You will see a message with `"op": "u"` (update), containing `before` (previous state) and `after` (new state) fields.
- **Delete**: You will see a message with `"op": "d"` (delete) and the `before` field containing the deleted user data.

### Option 2: Kafka UI

1. Open your browser and go to [http://localhost:8084](http://localhost:8084).
2. Navigate to **Topics** -> **pg.public.users**.
3. Click on the **Messages** tab.
4. You will see the live stream of messages as you perform operations in the database.

---

## 6. Message Structure Example

A typical Debezium CDC message looks like this (simplified, before `ExtractNewRecordState` unwrap):

```json
{
  "before": null,
  "after": {
    "id": 11,
    "username": "demo_user",
    "display_name": "Demo User",
    "email": "demo@example.com",
    "country_code": "US",
    "city": "New York",
    "region_name": "North America (East)",
    "platform": "Desktop",
    "created_at": 1715629400000,
    "updated_at": 1715629400000
  },
  "source": {
    "version": "2.3.0.Final",
    "connector": "postgresql",
    "name": "nexus-postgres-cdc",
    "ts_ms": 1715629400123,
    "snapshot": "false",
    "db": "nexus_db",
    "sequence": "...",
    "schema": "public",
    "table": "users",
    "txId": 500,
    "lsn": 25000
  },
  "op": "c",
  "ts_ms": 1715629400456,
  "transaction": null
}
```

- `op`: Operation type (`c`=create, `u`=update, `d`=delete, `r`=read/snapshot).
- `before`: The row state before the change (null for inserts).
- `after`: The row state after the change (null for deletes).
