# Kafka & Debezium Ingestion Demo Guide

This guide provides step-by-step instructions to test the CDC (Change Data Capture) pipeline, covering **PostgreSQL -> Debezium -> Kafka**. You will learn how to perform database operations (Insert, Update, Delete) and observe the corresponding events in Kafka.

## 1. Start Ingestion Services

To start only the services required for this ingestion demo (PostgreSQL, Kafka, and Debezium), run:

```bash
docker compose up -d \
  postgres \
  kafka \
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

You should see `postgres`, `kafka`, `debezium-connect`, and `kafka-ui` in a healthy state.

## 3. Verify Setup

### Check Debezium Connector

Verify that the Debezium connector is registered and running:

```bash
curl -s http://localhost:8083/connectors/ebap-postgres-cdc/status | jq
```

Expected output:
```json
{
  "name": "ebap-postgres-cdc",
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

List the topics to ensure the CDC topic exists:

```bash
docker exec -it ebap-kafka kafka-topics --bootstrap-server kafka:9092 --list
```

You should see `ebap.cdc.users`.

## 4. Database Operations (PostgreSQL)

You can connect to the PostgreSQL database using the `docker exec` command:

```bash
docker exec -it ebap-postgres psql -U admin -d ebap_db
```

Once inside the SQL prompt (`ebap_db=#`), you can run the following commands.

### A. Insert a New User

```sql
INSERT INTO users (user_id, username, email, tier, region)
VALUES ('usr_999', 'demo_user', 'demo@example.com', 'free', 'us-east-1');
```

### B. Update an Existing User

Update the `tier` for the user we just created:

```sql
UPDATE users SET tier = 'premium' WHERE user_id = 'usr_999';
```

### C. Delete a User

Delete the user:

```sql
DELETE FROM users WHERE user_id = 'usr_999';
```

### D. Verify Data

To see the current data in the table:

```sql
SELECT * FROM users ORDER BY id DESC LIMIT 5;
```

Exit the SQL prompt with `\q`.

## 5. Observing Changes in Kafka

You can observe the CDC events in real-time using the Kafka Console Consumer or Kafka UI.

### Option 1: Kafka Console Consumer

Open a new terminal and run:

```bash
docker exec -it ebap-kafka kafka-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic ebap.cdc.users \
  --from-beginning
```

**What to look for:**

- **Insert**: You will see a JSON message with `"op": "c"` (create) and the `after` field containing the new user data.
- **Update**: You will see a message with `"op": "u"` (update), containing `before` (previous state) and `after` (new state) fields.
- **Delete**: You will see a message with `"op": "d"` (delete) and the `before` field containing the deleted user data.

### Option 2: Kafka UI

1. Open your browser and go to [http://localhost:8084](http://localhost:8084).
2. Navigate to **Topics** -> **ebap.cdc.users**.
3. Click on the **Messages** tab.
4. You will see the live stream of messages as you perform operations in the database.

---

## 6. Message Structure Example

A typical Debezium CDC message looks like this (simplified):

```json
{
  "before": null,
  "after": {
    "id": 11,
    "user_id": "usr_999",
    "username": "demo_user",
    "email": "demo@example.com",
    "tier": "free",
    "region": "us-east-1",
    "created_at": 1715629400000,
    "updated_at": 1715629400000
  },
  "source": {
    "version": "2.3.0.Final",
    "connector": "postgresql",
    "name": "ebap.cdc",
    "ts_ms": 1715629400123,
    "snapshot": "false",
    "db": "ebap_db",
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
