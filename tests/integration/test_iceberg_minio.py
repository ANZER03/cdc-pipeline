from pyspark.sql import SparkSession
import sys


def test_iceberg_minio():
    print("Initializing Spark Session for Iceberg on MinIO test...")
    spark = (
        SparkSession.builder.appName("IcebergMinioTest")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        # Configure a catalog named 'minio' using Hadoop catalog type
        .config("spark.sql.catalog.minio", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.minio.type", "hadoop")
        .config("spark.sql.catalog.minio.warehouse", "s3a://spark-test/iceberg-data")
        # S3A / MinIO Configurations
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000")
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin")
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin")
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .getOrCreate()
    )

    try:
        print("Creating database 'test_db' in minio catalog...")
        spark.sql("CREATE NAMESPACE IF NOT EXISTS minio.test_db")

        table_name = "minio.test_db.iceberg_table"
        print(f"Creating table '{table_name}'...")
        spark.sql(
            f"CREATE TABLE IF NOT EXISTS {table_name} (id bigint, data string) USING iceberg"
        )

        print(f"Inserting data into '{table_name}'...")
        spark.sql(f"INSERT INTO {table_name} VALUES (1, 'Iceberg on MinIO works!')")

        print(f"Reading data from '{table_name}'...")
        df = spark.table(table_name)
        df.show()

        count = df.count()
        if count > 0:
            print(f"SUCCESS: Found {count} rows in Iceberg table on MinIO.")
        else:
            print("FAILURE: No rows found in Iceberg table.")
            sys.exit(1)

    except Exception as e:
        print(f"ERROR during Iceberg MinIO test: {str(e)}")
        sys.exit(1)
    finally:
        spark.stop()


if __name__ == "__main__":
    test_iceberg_minio()
