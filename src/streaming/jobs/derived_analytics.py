from streaming.kafka_sources import read_aggregated_kpis, read_sessions
from streaming.spark_session import create_spark_session
from streaming.transforms.alert_evaluator import start_alert_evaluator
from streaming.transforms.device_platform import start_device_platform_aggregator


def main() -> None:
    spark = create_spark_session("nexus-derived")
    sessions = read_sessions(spark)
    kpis_stream = read_aggregated_kpis(spark)

    queries = [
        start_device_platform_aggregator(sessions),
        start_alert_evaluator(kpis_stream),
    ]
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
