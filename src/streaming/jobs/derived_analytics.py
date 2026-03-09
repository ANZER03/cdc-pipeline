from streaming.kafka_sources import read_postgres_table_snapshot, read_sessions
from streaming.spark_session import create_spark_session
from streaming.transforms.device_platform import seed_platform_breakdown, start_device_platform_aggregator


def main() -> None:
    spark = create_spark_session("nexus-derived")
    sessions = read_sessions(spark)
    users_snapshot = read_postgres_table_snapshot(spark, "users")
    seed_platform_breakdown(users_snapshot)

    queries = [
        start_device_platform_aggregator(sessions),
    ]
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
