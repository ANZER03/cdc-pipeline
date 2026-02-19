"""
iceberg_bootstrap.py
EBAP Streaming — Iceberg table DDL bootstrap.

Creates the Iceberg namespace and tables if they don't exist yet.
Runs once at streaming job startup. Can also be invoked standalone
for environment provisioning.
"""

from pyspark.sql import SparkSession

from config import (
    ICEBERG_CATALOG, ICEBERG_DB,
    ICEBERG_TABLE_EVENTS, ICEBERG_TABLE_METRICS,
    log,
)


def bootstrap_iceberg_tables(spark: SparkSession) -> None:
    """Create Iceberg namespace + tables if they don't exist yet."""
    log.info("Bootstrapping Iceberg tables in catalog '%s'", ICEBERG_CATALOG)

    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {ICEBERG_CATALOG}.{ICEBERG_DB}")

    # enriched_events — one row per Kafka event, enriched with user profile
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {ICEBERG_TABLE_EVENTS} (
            event_id        STRING,
            user_id_hashed  STRING,
            action          STRING,
            amount          DOUBLE,
            item_id         STRING,
            location        STRING,
            region          STRING,
            plan            STRING,
            event_ts        TIMESTAMP,
            ingest_ts       TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (days(event_ts), region)
        TBLPROPERTIES (
            'write.format.default' = 'parquet',
            'write.parquet.compression-codec' = 'snappy'
        )
    """)

    # windowed_metrics — aggregated counts per window + region + action
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {ICEBERG_TABLE_METRICS} (
            window_start    TIMESTAMP,
            window_end      TIMESTAMP,
            window_duration STRING,
            region          STRING,
            action          STRING,
            event_count     LONG,
            total_amount    DOUBLE,
            ingest_ts       TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (days(window_start), region)
        TBLPROPERTIES (
            'write.format.default' = 'parquet',
            'write.parquet.compression-codec' = 'snappy'
        )
    """)

    log.info("Iceberg tables ready: %s, %s", ICEBERG_TABLE_EVENTS, ICEBERG_TABLE_METRICS)
