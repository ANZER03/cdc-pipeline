"""Region and flow aggregation for Nexus."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery

from streaming.config import (
    CHANNEL_FLOWS,
    CHANNEL_REGIONS,
    CHECKPOINT_BASE,
    REDIS_KEY_FLOWS_CURRENT,
    REDIS_KEY_REGIONS_CURRENT,
    REGIONS,
    REGION_SLIDE_INTERVAL,
    REGION_WINDOW_DURATION,
    TRIGGER_TRANSACTIONS,
)
from streaming.redis_client import NexusRedisWriter


REGION_COORDS = {region["name"]: region["coords"] for region in REGIONS}


def write_region_batch(batch_df: DataFrame, batch_id: int) -> None:
    del batch_id
    rows = batch_df.collect()
    if not rows:
        return

    latest_window_end = max(row["window"]["end"] for row in rows)

    payload = []
    for row in rows:
        item = row.asDict(recursive=True)
        if item["window"]["end"] != latest_window_end:
            continue
        region_name = str(item["region_name"])
        payload.append(
            {
                "name": region_name,
                "coords": REGION_COORDS.get(region_name, [0, 0]),
                "intensity": round(float(item["intensity"] or 0.0), 1),
                "sales": round(float(item["sales"] or 0.0), 2),
            }
        )

    payload.sort(key=lambda entry: entry["name"])
    writer = NexusRedisWriter()
    writer.write_json(REDIS_KEY_REGIONS_CURRENT, payload, channel=CHANNEL_REGIONS)

    ranked_payload = sorted(payload, key=lambda entry: float(entry["intensity"]), reverse=True)
    if len(ranked_payload) >= 2:
        hub_region = ranked_payload[0]
        flows_payload = [
            {
                "id": f"flow_{index}",
                "source": entry["coords"],
                "target": hub_region["coords"],
                "value": float(entry["intensity"]),
            }
            for index, entry in enumerate(ranked_payload[1:6], start=1)
        ]
        writer.write_json(REDIS_KEY_FLOWS_CURRENT, flows_payload, channel=CHANNEL_FLOWS)


def write_flow_batch(batch_df: DataFrame, batch_id: int) -> None:
    del batch_id
    rows = batch_df.collect()
    if not rows:
        return

    latest_window_end = max(row["window"]["end"] for row in rows)
    current_rows = [row for row in rows if row["window"]["end"] == latest_window_end]
    if len(current_rows) < 2:
        return

    ranked_rows = sorted(
        current_rows,
        key=lambda row: float(row["intensity"] or 0.0),
        reverse=True,
    )
    hub_region = str(ranked_rows[0]["region_name"])
    payload = []
    for index, row in enumerate(ranked_rows[1:6], start=1):
        source = str(row["region_name"])
        target = hub_region
        payload.append(
            {
                "id": f"flow_{index}",
                "source": REGION_COORDS.get(source, [0, 0]),
                "target": REGION_COORDS.get(target, [0, 0]),
                "value": round(float(row["intensity"] or 0.0), 1),
            }
        )

    NexusRedisWriter().write_json(REDIS_KEY_FLOWS_CURRENT, payload, channel=CHANNEL_FLOWS)


def build_region_snapshot(orders_df: DataFrame, request_log_df: DataFrame) -> DataFrame:
    order_events = orders_df.filter(F.col("status") == "completed").select(
        F.col("updated_at").alias("event_time"),
        F.coalesce(F.col("region_name"), F.lit("Unknown")).alias("region_name"),
        F.col("total_amount").cast("double").alias("sales"),
        F.lit(0).alias("request_count"),
    )
    request_events = request_log_df.select(
        F.col("created_at").alias("event_time"),
        F.coalesce(F.col("region_name"), F.lit("Unknown")).alias("region_name"),
        F.lit(0.0).alias("sales"),
        F.lit(1).alias("request_count"),
    )

    return (
        order_events.unionByName(request_events)
        .withWatermark("event_time", "10 minutes")
        .groupBy(
            F.window("event_time", REGION_WINDOW_DURATION, REGION_SLIDE_INTERVAL), "region_name"
        )
        .agg(
            F.sum("sales").alias("sales"),
            F.sum("request_count").alias("request_count"),
        )
        .select(
            "window",
            "region_name",
            "sales",
            F.least(F.col("request_count") * F.lit(5.0), F.lit(100.0)).alias("intensity"),
        )
    )


def start_region_aggregator(
    orders_df: DataFrame, request_log_df: DataFrame, products_df: DataFrame
) -> StreamingQuery:
    del products_df
    regions = build_region_snapshot(orders_df, request_log_df)
    region_query = (
        regions.writeStream.outputMode("complete")
        .foreachBatch(write_region_batch)
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/regions-v2")
        .trigger(processingTime=TRIGGER_TRANSACTIONS)
        .start()
    )
    return region_query
