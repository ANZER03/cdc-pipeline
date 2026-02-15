from pyspark.sql import SparkSession
import os


def test_connectors():
    # Initialize Spark Session with Iceberg configurations
    spark = (
        SparkSession.builder.appName("ConnectorTest")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config("spark.sql.catalog.local", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.local.type", "hadoop")
        .config("spark.sql.catalog.local.warehouse", "/tmp/iceberg-warehouse")
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

    # 2. Test Kafka Connector (loading check)
    print("Testing Kafka Connector loading...")
    try:
        # We don't necessarily need a running Kafka to check if the format is recognized
        # But we'll try to define a read stream from a dummy bootstrap server
        df_kafka = (
            spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", "kafka:9092")
            .option("subscribe", "test-topic")
            .load()
        )
        print("Kafka connector loaded successfully (format 'kafka' recognized).")
    except Exception as e:
        if "Failed to find data source: kafka" in str(e):
            print("Kafka connector NOT found.")
            raise e
        else:
            # It might fail because localhost:9092 is not reachable, but that means the connector IS loaded
            print(
                f"Kafka connector format recognized. (Note: connection might fail as expected: {str(e)[:100]}...)"
            )

    spark.stop()


if __name__ == "__main__":
    test_connectors()
