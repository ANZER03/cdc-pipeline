# Spark with Kafka & Iceberg (KRaft Mode)

This project provides a custom Spark Docker image pre-configured with Apache Iceberg and Kafka connectors, along with a KRaft-mode Kafka orchestration for end-to-end testing.

## 1. Spark Image Details
- **Base Image**: `apache/spark:3.5.3`
- **Scala Version**: `2.12`
- **Connectors Included**:
    - **Iceberg**: `iceberg-spark-runtime-3.5_2.12:1.7.1`
    - **Kafka**: `spark-sql-kafka-0-10_2.12:3.5.3` (plus dependencies: `kafka-clients`, `commons-pool2`, `spark-token-provider-kafka`)

## 2. Infrastructure (KRaft Mode)
The setup uses **Kafka KRaft mode**, eliminating the need for ZooKeeper. 
- **Image**: `confluentinc/cp-kafka:7.7.7`
- **Node ID**: 1 (combined Broker & Controller)
- **Cluster ID**: `MkU3OEVBNTcwNTJENDM2Qk`

## 3. Verification Test
The `test_connectors.py` script performs end-to-end checks:
1.  **Iceberg**: Creates a Hadoop-catalog based table (`local.db.test_table`), inserts a record, and verifies the read.
2.  **Kafka**: 
    - **Production**: Writes a sample DataFrame with `key` and `value` columns to a Kafka topic (`test-topic`).
    - **Consumption**: Reads the data back from the same topic using the Spark Kafka connector and displays the result.

## 4. How to Run

### Build the Image
```bash
docker build -t custom-spark:latest ./test
```

### Run the Integration Test
```bash
cd test
docker compose up --abort-on-container-exit
```

## 5. Clean up
To remove the environment and volumes:
```bash
docker compose down -v
```
