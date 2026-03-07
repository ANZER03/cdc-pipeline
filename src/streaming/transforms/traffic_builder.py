"""Traffic time-series query for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import (
    CHANNEL_TRAFFIC,
    CHECKPOINT_BASE,
    REDIS_KEY_TRAFFIC_TS,
    TRAFFIC_WINDOW_DURATION,
    TRIGGER_INFRASTRUCTURE,
)
from streaming.redis_client import NexusRedisWriter


def write_traffic_batch(batch_df: DataFrame, batch_id: int) -> None:
    del batch_id
    rows = batch_df.orderBy(F.col("timestamp").desc()).limit(1).collect()
    if not rows:
        return

    writer = NexusRedisWriter()
    point = rows[0].asDict(recursive=True)
    payload = {
        "timestamp": int(point["timestamp"]),
        "value": int(point["value"]),
        "label": str(point["label"]),
    }
    writer.push_to_list(REDIS_KEY_TRAFFIC_TS, payload, max_len=21, channel=CHANNEL_TRAFFIC)


def build_traffic_points(request_log_df: DataFrame) -> DataFrame:
    return (
        request_log_df.groupBy(F.window("created_at", TRAFFIC_WINDOW_DURATION))
        .agg(F.count("*").alias("value"))
        .select(
            (F.col("window.end").cast("double") * 1000).cast("long").alias("timestamp"),
            F.col("value"),
            F.date_format(F.col("window.end"), "hh:mm:ss a").alias("label"),
        )
    )


def start_traffic_builder(request_log_df: DataFrame) -> StreamingQuery:
    frame = build_traffic_points(request_log_df)
    return (
        frame.writeStream.outputMode("complete")
        .foreachBatch(write_traffic_batch)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/traffic")
        .trigger(processingTime=TRIGGER_INFRASTRUCTURE)
        .start()
    )
