# Spark with Kafka & Iceberg (KRaft Mode)

This project provides a custom Spark Docker image pre-configured with Apache Iceberg and Kafka connectors, along with a KRaft-mode Kafka orchestration for end-to-end testing.

## 1. Spark Image Details
- **Base Image**: `apache/spark:3.5.3`
- **Scala Version**: `2.12`
- **Connectors Included**:
    - **Iceberg**: `iceberg-spark-runtime-3.5_2.12:1.7.1`
    - **Kafka**: `spark-sql-kafka-0-10_2.12:3.5.3`
    - **MinIO/S3**: `hadoop-aws:3.3.4` and `aws-java-sdk-bundle:1.12.262`

## 2. Infrastructure
The setup uses a multi-container orchestration:
- **Kafka**: KRaft mode (`confluentinc/cp-kafka:7.7.7`).
- **MinIO**: Object storage for S3A testing (`minio/minio:latest`).

## 3. Verification Test
The `test_connectors.py` script performs end-to-end checks:
1.  **Iceberg**: Creates a Hadoop-catalog based table, inserts a record, and verifies the read.
2.  **Kafka**: Produces a sample record to `test-topic` and consumes it back.
3.  **MinIO (S3A)**: Writes a Parquet file to `s3a://spark-test/` and reads it back.
4.  **Iceberg on MinIO**: (via `test_iceberg_minio.py`) Specifically verifies writing Iceberg tables directly to the MinIO bucket.

## 4. How to Run

### Build the Image
```bash
docker build -t custom-spark:latest ./test
```

### Run the Integration Test
1. Start infrastructure:
```bash
cd test
docker compose up -d kafka minio
```
2. Create the test bucket:
```bash
docker run --rm --network test_default minio/mc alias set myminio http://minio:9000 minioadmin minioadmin
docker run --rm --network test_default minio/mc mb myminio/spark-test
```
3. Run the complete connector test:
```bash
docker compose up spark --abort-on-container-exit
```

4. Run the specific Iceberg-MinIO write test:
```bash
docker run --rm --network test_default \
  -v $(pwd)/test/test_iceberg_minio.py:/test/test_iceberg_minio.py \
  custom-spark:latest \
  /opt/spark/bin/spark-submit /test/test_iceberg_minio.py
```

## 5. Clean up
To remove the environment and volumes:
```bash
docker compose down -v
```
