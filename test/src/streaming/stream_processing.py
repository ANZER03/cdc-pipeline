"""
stream_processing.py
EBAP Spark Structured Streaming Job

Reads from Kafka topics (ebap.events.raw, ebap.cdc.users),
performs windowed aggregations and stream-stream joins,
then dual-writes:
  - Hot path: aggregated metrics → Redis (TTL 24h)
  - Cold path: enriched events  → MinIO/Iceberg (partitioned by day/region)

Usage:
  spark-submit --master spark://spark-master-streaming:7077 stream_processing.py
"""

# TODO: Implement Phase 5 of PLAN.md
# - Read streams from Kafka
# - Schema enforcement (StructType matching PRD schemas)
# - Watermark: 10 minutes for late data handling
# - Stream-Stream join: events + CDC users on user_id
# - Tumbling window aggregations: 1m, 5m, 1h
# - Alerting state machine: Normal → Pending → Firing
# - foreachBatch sink to Redis (SET with TTL)
# - Iceberg sink to s3a://ebap-silver/ (partitioned by day, region)
# - Checkpoint to s3a://ebap-checkpoints/streaming/
