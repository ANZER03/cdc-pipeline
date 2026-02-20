"""
sinks/redis_sink.py
EBAP Streaming — Redis hot-path foreachBatch writer + alerting state machine.

Writes 1-minute windowed KPIs to Redis with 24h TTL.
Also drives the per-region alerting state machine (Normal → Pending → Firing).

Redis key patterns:
  kpi:active_users                       → total event count in last 1m (all regions)
  kpi:purchase_count                     → purchase count in last 1m
  kpi:total_revenue                      → sum of purchase amounts in last 1m
  region:{region}:event_count            → event count per region (1m window)
  region:{region}:health_intensity       → 0-100 load proxy for App geo-map
  alert:{region}:state                   → Normal / Pending / Firing
"""

from datetime import datetime, timezone

from pyspark.sql import DataFrame

from config import (
    REDIS_TTL_SECONDS,
    ALERT_ERROR_RATE_THRESHOLD,
    ALERT_PENDING_DURATION_S,
    log,
)

# ---------------------------------------------------------------------------
# Alerting state machine
# ---------------------------------------------------------------------------

def _alert_state(error_rate: float, pending_since_epoch: float, now_epoch: float) -> str:
    """
    Pure function implementing the alerting state machine:
      Normal  → error_rate < threshold
      Pending → error_rate >= threshold, duration < ALERT_PENDING_DURATION_S
      Firing  → error_rate >= threshold, duration >= ALERT_PENDING_DURATION_S
    """
    if error_rate < ALERT_ERROR_RATE_THRESHOLD:
        return "Normal"
    elapsed = now_epoch - pending_since_epoch
    if elapsed < ALERT_PENDING_DURATION_S:
        return "Pending"
    return "Firing"


# Module-level dict to track alert pending timestamps (per-region)
# In a real deployment this would live in Redis or Spark state store.
_alert_pending_since: dict = {}


# ---------------------------------------------------------------------------
# foreachBatch writer
# ---------------------------------------------------------------------------

def write_to_redis(batch_df: DataFrame, epoch_id: int) -> None:
    """
    foreachBatch sink for the 1-minute windowed metrics → Redis.
    """
    import redis as redis_lib

    r = redis_lib.Redis(host="redis", port=6379, decode_responses=True)
    pipe = r.pipeline()

    rows = batch_df.collect()
    now_epoch = datetime.now(timezone.utc).timestamp()

    # Aggregate totals for global KPIs
    total_events   = 0
    purchase_count = 0
    total_revenue  = 0.0

    region_stats: dict = {}

    for row in rows:
        region = row["region"] or "unknown"
        action = row["action"] or "unknown"
        count  = int(row["event_count"] or 0)
        amount = float(row["total_amount"] or 0.0)

        total_events += count
        if action == "purchase":
            purchase_count += count
            total_revenue  += amount

        if region not in region_stats:
            region_stats[region] = {"event_count": 0, "revenue": 0.0, "errors": 0}
        region_stats[region]["event_count"] += count
        if action in ("error", "checkout_fail"):
            region_stats[region]["errors"] += count

    # Global KPIs
    pipe.set("kpi:active_users",    total_events,    ex=REDIS_TTL_SECONDS)
    pipe.set("kpi:purchase_count",  purchase_count,  ex=REDIS_TTL_SECONDS)
    pipe.set("kpi:total_revenue",   f"{total_revenue:.2f}", ex=REDIS_TTL_SECONDS)
    pipe.set("kpi:last_updated",    datetime.now(timezone.utc).isoformat(), ex=REDIS_TTL_SECONDS)

    # Per-region KPIs + alerting state machine
    for region, stats in region_stats.items():
        ec     = stats["event_count"]
        errors = stats["errors"]
        error_rate = errors / ec if ec > 0 else 0.0

        # Health intensity: scale event count to 0-100 (cap at 1000 events/min → 100%)
        intensity = min(100, int((ec / 1000) * 100))

        pipe.set(f"region:{region}:event_count",      ec,        ex=REDIS_TTL_SECONDS)
        pipe.set(f"region:{region}:health_intensity", intensity, ex=REDIS_TTL_SECONDS)
        pipe.set(f"region:{region}:revenue",          f"{stats['revenue']:.2f}", ex=REDIS_TTL_SECONDS)

        # Alerting state machine
        if error_rate < ALERT_ERROR_RATE_THRESHOLD:
            # Back to Normal — reset pending timer
            _alert_pending_since.pop(region, None)
            alert_state = "Normal"
        else:
            if region not in _alert_pending_since:
                _alert_pending_since[region] = now_epoch  # start pending clock
            alert_state = _alert_state(error_rate, _alert_pending_since[region], now_epoch)

        pipe.set(f"alert:{region}:state",      alert_state, ex=REDIS_TTL_SECONDS)
        pipe.set(f"alert:{region}:error_rate", f"{error_rate:.4f}", ex=REDIS_TTL_SECONDS)

    pipe.execute()
    log.info(
        "[epoch %d] Redis write: %d total events, %d purchases, revenue=%.2f, regions=%s",
        epoch_id, total_events, purchase_count, total_revenue, list(region_stats.keys())
    )
