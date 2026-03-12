import shutil

from streaming.config import CHECKPOINT_BASE
from streaming.kafka_sources import (
    read_orders,
    read_products,
    read_request_log,
    read_sessions,
    read_user_events,
)
from streaming.spark_session import create_spark_session
from streaming.transforms.activity_enricher import start_activity_enricher
from streaming.transforms.kpi_aggregator import start_kpi_aggregator
from streaming.transforms.region_aggregator import start_region_aggregator


def main() -> None:
    shutil.rmtree(CHECKPOINT_BASE, ignore_errors=True)
    spark = create_spark_session("nexus-transactions")

    # Each streaming query needs its own independent source DataFrame instances.
    # Sharing a single DataFrame between multiple queries that apply withWatermark
    # causes "Redefining watermark is disallowed" in Spark >= 3.3.
    orders_kpi = read_orders(spark)
    orders_region = read_orders(spark)
    sessions_kpi = read_sessions(spark)
    products = read_products(spark)
    request_log_kpi = read_request_log(spark)
    request_log_region = read_request_log(spark)
    user_events = read_user_events(spark)

    kpi_redis_query, kpi_kafka_query = start_kpi_aggregator(
        orders_kpi, sessions_kpi, request_log_kpi
    )
    queries = [
        kpi_redis_query,
        kpi_kafka_query,
        start_activity_enricher(user_events),
        start_region_aggregator(orders_region, request_log_region, products),
    ]
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
