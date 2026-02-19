"""
sinks/iceberg_sink.py
EBAP Streaming — Iceberg cold-path foreachBatch writers.

Two writers:
  - write_enriched_to_iceberg: upserts enriched events (MERGE INTO on event_id)
  - write_metrics_to_iceberg: appends windowed metrics (windows are immutable once closed)
"""

from pyspark.sql import DataFrame

from config import ICEBERG_TABLE_EVENTS, ICEBERG_TABLE_METRICS, log


def write_enriched_to_iceberg(batch_df: DataFrame, epoch_id: int) -> None:
    """
    foreachBatch sink for enriched events → Iceberg (ebap-silver).
    Uses merge-on-read upsert keyed on event_id to satisfy exactly-once semantics.
    """
    if batch_df.isEmpty():
        return

    count = batch_df.count()

    # Register as a temp view so we can use SQL MERGE
    batch_df.createOrReplaceTempView("batch_enriched_events")

    batch_df.sparkSession.sql(f"""
        MERGE INTO {ICEBERG_TABLE_EVENTS} t
        USING batch_enriched_events s
        ON t.event_id = s.event_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)

    log.info("[epoch %d] Iceberg enriched_events upserted %d rows", epoch_id, count)


def write_metrics_to_iceberg(batch_df: DataFrame, epoch_id: int) -> None:
    """
    foreachBatch sink for windowed metrics → Iceberg (ebap-silver).
    Appends — windows are immutable once closed.
    """
    if batch_df.isEmpty():
        return

    count = batch_df.count()
    batch_df.writeTo(ICEBERG_TABLE_METRICS).append()
    log.info("[epoch %d] Iceberg windowed_metrics appended %d rows", epoch_id, count)
