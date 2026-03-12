"""Spark session factory for Nexus streaming jobs."""

import os

from pyspark.sql import SparkSession

from streaming.config import SCHEMA_REGISTRY_URL, log


def create_spark_session(app_name: str) -> SparkSession:
    spark = (
        SparkSession.builder.appName(app_name)
        .master(os.getenv("SPARK_MASTER_URL", "local[2]"))
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.streaming.stopGracefullyOnShutdown", "true")
        .config("spark.sql.avro.schemaRegistryUrl", SCHEMA_REGISTRY_URL)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    log.info("SparkSession created for %s", app_name)
    return spark
