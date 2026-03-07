from streaming.kafka_sources import (
    read_orders,
    read_postgres_table_snapshot,
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
    spark = create_spark_session("nexus-transactions")
    orders = read_orders(spark)
    sessions = read_sessions(spark)
    user_events = read_user_events(spark)
    products = read_products(spark)
    request_log = read_request_log(spark)
    users_snapshot = read_postgres_table_snapshot(spark, "users")
    orders_snapshot = read_postgres_table_snapshot(spark, "orders")

    queries = [
        start_kpi_aggregator(orders, sessions, request_log),
        start_activity_enricher(user_events, users_snapshot, orders_snapshot),
    ]
    region_query, flow_query = start_region_aggregator(orders, request_log, products)
    queries.extend([region_query, flow_query])
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
