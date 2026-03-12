"""Shared pytest fixtures for Nexus tests."""

import pytest


@pytest.fixture(scope="session")
def spark():
    """
    Provide a local SparkSession for tests.
    Uses in-memory catalog — no external services required for unit tests.
    """
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.master("local[2]")
        .appName("nexus-tests")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    yield spark
    spark.stop()
