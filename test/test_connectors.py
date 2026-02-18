from pyspark.sql import SparkSession
import os


def test_connectors():
    # Initialize Spark Session with Iceberg and S3A configurations
    spark = (
        SparkSession.builder.appName("ConnectorTest")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config("spark.sql.catalog.local", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.local.type", "hadoop")
        .config("spark.sql.catalog.local.warehouse", "/tmp/iceberg-warehouse")
        # Lakehouse Catalog (Iceberg on MinIO)
        .config("spark.sql.catalog.lakehouse", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.lakehouse.type", "hadoop")
        .config("spark.sql.catalog.lakehouse.warehouse", "s3a://spark-test/lakehouse")
        # S3A / MinIO Configurations
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000")
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin")
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin")
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .getOrCreate()
    )

    print("Spark Session created successfully.")

    # 1. Test Iceberg
    print("Testing Iceberg...")
    spark.sql(
        "CREATE TABLE IF NOT EXISTS local.db.test_table (id bigint, data string) USING iceberg"
    )
    spark.sql("INSERT INTO local.db.test_table VALUES (1, 'iceberg works')")
    df_iceberg = spark.table("local.db.test_table")
    df_iceberg.show()
    print("Iceberg test passed.")

    # 2. Test Kafka Connector (Production and Consumption)
    print("Testing Kafka Connector Production...")
    try:
        data = [("1", "hello kafka from spark")]
        df_to_kafka = spark.createDataFrame(data, ["key", "value"])

        df_to_kafka.write.format("kafka").option(
            "kafka.bootstrap.servers", "kafka:9092"
        ).option("topic", "test-topic").save()
        print("Kafka production successful.")

        print("Testing Kafka Connector Consumption...")
        df_from_kafka = (
            spark.read.format("kafka")
            .option("kafka.bootstrap.servers", "kafka:9092")
            .option("subscribe", "test-topic")
            .option("startingOffsets", "earliest")
            .load()
        )

        print("--- KAFKA DATA START ---")
        df_from_kafka.selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)").show()
        print("--- KAFKA DATA END ---")
        print("Kafka consumption successful.")

    except Exception as e:
        print(f"Kafka test failed: {str(e)}")
        raise e

    # 3. Test MinIO (S3A)
    print("Testing MinIO (S3A) Integration...")
    try:
        s3_path = "s3a://spark-test/test-file.parquet"
        data_s3 = [("s3", "minio integration works")]
        df_s3 = spark.createDataFrame(data_s3, ["source", "status"])

        print(f"Attempting to write to {s3_path}...")
        df_s3.write.mode("overwrite").parquet(s3_path)
        print("Write to MinIO successful.")

        print("Attempting to read from MinIO...")
        df_read_s3 = spark.read.parquet(s3_path)
        df_read_s3.show()
        print("MinIO integration test passed.")

    except Exception as e:
        print(f"MinIO test failed: {str(e)}")
        raise e

    # 4. Lakehouse Test (Iceberg on MinIO)
    print("Testing Lakehouse Architecture (Iceberg on MinIO)...")
    try:
        spark.sql(
            "CREATE TABLE IF NOT EXISTS lakehouse.db.lakehouse_table (id bigint, data string, source string) USING iceberg"
        )
        spark.sql(
            "INSERT INTO lakehouse.db.lakehouse_table VALUES (1, 'lakehouse works', 'minio')"
        )
        print("Write to Iceberg table in MinIO successful.")

        df_lakehouse = spark.table("lakehouse.db.lakehouse_table")
        df_lakehouse.show()
        print("Lakehouse integration test passed.")
    except Exception as e:
        print(f"Lakehouse test failed: {str(e)}")
        raise e

    spark.stop()


if __name__ == "__main__":
    test_connectors()
