"""
spark_session.py
EBAP Streaming — SparkSession factory.

Centralizes SparkSession construction with Iceberg catalog + S3A/MinIO config.
Importing this module and calling create_spark_session() is the only entry point
for Spark initialization across all streaming jobs.
"""

from pyspark.sql import SparkSession

from config import ICEBERG_CATALOG, log


def create_spark_session() -> SparkSession:
    """Build SparkSession with Iceberg catalog + S3A/MinIO config."""
    spark = (
        SparkSession.builder
        .appName("EBAP-Streaming")
        # Iceberg extensions
        .config("spark.sql.extensions",
                "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        # Iceberg JDBC catalog (shared with Trino via iceberg_catalog PostgreSQL DB)
        .config("spark.sql.catalog.ebap",
                "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.ebap.catalog-impl",
                "org.apache.iceberg.jdbc.JdbcCatalog")
        .config("spark.sql.catalog.ebap.uri",
                "jdbc:postgresql://postgres:5432/iceberg_catalog")
        .config("spark.sql.catalog.ebap.jdbc.user",   "admin")
        .config("spark.sql.catalog.ebap.jdbc.password", "admin")
        .config("spark.sql.catalog.ebap.warehouse",   "s3a://ebap-silver/")
        .config("spark.sql.catalog.ebap.io-impl",
                "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.sql.catalog.ebap.s3.endpoint",  "http://minio:9000")
        .config("spark.sql.catalog.ebap.s3.path-style-access", "true")
        # S3A / MinIO
        .config("spark.hadoop.fs.s3a.endpoint",        "http://minio:9000")
        .config("spark.hadoop.fs.s3a.access.key",      "admin")
        .config("spark.hadoop.fs.s3a.secret.key",      "password")
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl",
                "org.apache.hadoop.fs.s3a.S3AFileSystem")
        # Redis datasource
        .config("spark.redis.host", "redis")
        .config("spark.redis.port", "6379")
        # Reduce logging noise
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    log.info("SparkSession created — Iceberg catalog: %s", ICEBERG_CATALOG)
    return spark
