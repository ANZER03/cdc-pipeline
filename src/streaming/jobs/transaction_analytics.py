from streaming.kafka_sources import (
    read_orders,
    read_postgres_table_snapshot,
    read_products,
    read_request_log,
    read_sessions,
)
from streaming.spark_session import create_spark_session
from streaming.transforms.activity_enricher import start_activity_enricher
from streaming.transforms.alert_evaluator import start_alert_evaluator
from streaming.transforms.kpi_aggregator import build_kpi_frame
from streaming.transforms.kpi_aggregator import start_kpi_aggregator
from streaming.transforms.region_aggregator import start_region_aggregator


def main() -> None:
    spark = create_spark_session("nexus-transactions")
    orders = read_orders(spark)
    sessions = read_sessions(spark)
    products = read_products(spark)
    request_log = read_request_log(spark)
    users_snapshot = read_postgres_table_snapshot(spark, "users")
    orders_snapshot = read_postgres_table_snapshot(spark, "orders")
    kpi_frame = build_kpi_frame(orders, sessions, request_log)

    kpi_redis_query, kpi_kafka_query = start_kpi_aggregator(orders, sessions, request_log)
    queries = [
        kpi_redis_query,
        kpi_kafka_query,
        start_alert_evaluator(kpi_frame),
        start_activity_enricher(request_log, users_snapshot, orders_snapshot),
        start_region_aggregator(orders, request_log, products),
    ]
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
