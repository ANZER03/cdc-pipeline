"""
main.py
EBAP Streaming — Entry point and orchestrator.

Thin wiring layer: imports all modules, calls functions in order,
and wires foreachBatch callbacks. Contains zero business logic.

Usage (submitted by spark-streaming-submit container):
  spark-submit --master spark://spark-master-streaming:7077 \
    --conf spark.sql.catalog.ebap=... \
    /opt/spark/jobs/main.py
"""

from config import CHECKPOINT_BASE, log
from spark_session import create_spark_session
from iceberg_bootstrap import bootstrap_iceberg_tables
from kafka_sources import read_events_stream, read_cdc_users_stream
from transforms.enrichment import enrich_events
from transforms.windowed_aggregations import build_windowed_metrics
from sinks.redis_sink import write_to_redis
from sinks.iceberg_sink import write_enriched_to_iceberg, write_metrics_to_iceberg


def main() -> None:
    spark = create_spark_session()

    # --- 1. Bootstrap Iceberg tables ---
    bootstrap_iceberg_tables(spark)

    # --- 2. Read source streams ---
    log.info("Starting Kafka source streams...")
    events_df = read_events_stream(spark)
    users_df  = read_cdc_users_stream(spark)

    # --- 3. Stream-stream join: enrich events with user profiles ---
    enriched_df = enrich_events(events_df, users_df)

    # --- 4. Windowed aggregations (on events only — no join needed for KPIs) ---
    windowed = build_windowed_metrics(events_df)

    # --- 5. Hot path: 1-minute metrics → Redis ---
    log.info("Starting Redis (hot path) streaming query...")
    redis_query = (
        windowed["1m"]
        .writeStream
        .outputMode("update")
        .foreachBatch(write_to_redis)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/redis")
        .trigger(processingTime="30 seconds")
        .queryName("redis-hot-path")
        .start()
    )

    # --- 6. Cold path: enriched events → Iceberg ---
    log.info("Starting Iceberg enriched-events (cold path) streaming query...")
    iceberg_events_query = (
        enriched_df
        .writeStream
        .outputMode("append")
        .foreachBatch(write_enriched_to_iceberg)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/iceberg-events")
        .trigger(processingTime="60 seconds")
        .queryName("iceberg-enriched-events")
        .start()
    )

    # --- 7. Cold path: 1-hour windowed metrics → Iceberg ---
    log.info("Starting Iceberg windowed-metrics (cold path) streaming query...")
    iceberg_metrics_query = (
        windowed["1h"]
        .writeStream
        .outputMode("append")
        .foreachBatch(write_metrics_to_iceberg)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/iceberg-metrics")
        .trigger(processingTime="60 seconds")
        .queryName("iceberg-windowed-metrics")
        .start()
    )

    log.info(
        "All streaming queries active: [%s, %s, %s]",
        redis_query.name,
        iceberg_events_query.name,
        iceberg_metrics_query.name,
    )

    # Block until all queries terminate (or SIGTERM for graceful shutdown)
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
