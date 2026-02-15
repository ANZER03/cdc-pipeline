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

    # 2. Test Kafka Connector (Production and Consumption)
    print("Testing Kafka Connector Production...")
    try:
        # Create a simple dataframe to write to Kafka
        # Kafka expects 'key' and 'value' columns (both string or binary)
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

        # Show the data (it will have key, value, topic, partition, offset, timestamp, timestampType)
        print("--- KAFKA DATA START ---")
        df_from_kafka.selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)").show()
        print("--- KAFKA DATA END ---")
        print("Kafka consumption successful.")

    except Exception as e:
        print(f"Kafka test failed: {str(e)}")
        raise e

    spark.stop()


if __name__ == "__main__":
    test_connectors()
