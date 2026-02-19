"""
tests/e2e/test_full_pipeline.py
End-to-end smoke test: produce events → verify Redis KPIs + Iceberg tables.
Requires the full stack to be running (make up + make submit-stream).
"""

import pytest


@pytest.mark.skip(reason="Requires full running stack — run manually with: make test-e2e")
def test_full_pipeline_produces_redis_kpis():
    """
    Produce synthetic events to Kafka, wait for the streaming job to process them,
    then assert that Redis KPIs are populated.
    """
    import redis

    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    kpi = r.get("kpi:active_users")
    assert kpi is not None, "kpi:active_users not found in Redis — pipeline may not be running"


@pytest.mark.skip(reason="Requires full running stack — run manually with: make test-e2e")
def test_full_pipeline_writes_to_iceberg():
    """
    Assert that the Iceberg enriched_events table contains rows after the pipeline runs.
    """
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.appName("e2e-test").getOrCreate()
    count = spark.table("ebap.events_db.enriched_events").count()
    assert count > 0, "No rows found in Iceberg enriched_events table"
    spark.stop()
