from streaming.kafka_sources import read_request_log, read_system_metrics
from streaming.spark_session import create_spark_session
from streaming.transforms.geo_header import start_geo_header_aggregator
from streaming.transforms.health_aggregator import start_health_aggregator
from streaming.transforms.traffic_builder import start_traffic_builder


def main() -> None:
    spark = create_spark_session("nexus-infrastructure")
    request_log = read_request_log(spark)
    system_metrics = read_system_metrics(spark)

    queries = [
        start_traffic_builder(request_log),
        start_health_aggregator(system_metrics),
        start_geo_header_aggregator(system_metrics, request_log),
    ]
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
