import shutil

from streaming.config import CHECKPOINT_BASE
from streaming.kafka_sources import read_sessions
from streaming.spark_session import create_spark_session
from streaming.transforms.device_platform import start_device_platform_aggregator


def main() -> None:
    shutil.rmtree(CHECKPOINT_BASE, ignore_errors=True)
    spark = create_spark_session("nexus-derived")
    sessions = read_sessions(spark)

    queries = [
        start_device_platform_aggregator(sessions),
    ]
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
