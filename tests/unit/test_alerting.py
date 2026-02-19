"""
tests/unit/test_alerting.py
Unit tests for the alerting state machine in src/streaming/sinks/redis_sink.py.
The _alert_state function is a pure function — no Spark or Redis required.
"""

from src.streaming.sinks.redis_sink import _alert_state
from src.streaming.config import ALERT_ERROR_RATE_THRESHOLD, ALERT_PENDING_DURATION_S


def test_normal_when_error_rate_below_threshold():
    state = _alert_state(
        error_rate=0.0,
        pending_since_epoch=0.0,
        now_epoch=100.0,
    )
    assert state == "Normal"


def test_normal_at_exact_threshold_minus_epsilon():
    state = _alert_state(
        error_rate=ALERT_ERROR_RATE_THRESHOLD - 0.001,
        pending_since_epoch=0.0,
        now_epoch=100.0,
    )
    assert state == "Normal"


def test_pending_when_error_rate_at_threshold_and_duration_short():
    state = _alert_state(
        error_rate=ALERT_ERROR_RATE_THRESHOLD,
        pending_since_epoch=90.0,   # only 10s elapsed
        now_epoch=100.0,
    )
    assert state == "Pending"


def test_firing_when_error_rate_at_threshold_and_duration_exceeded():
    state = _alert_state(
        error_rate=ALERT_ERROR_RATE_THRESHOLD,
        pending_since_epoch=0.0,   # 100s elapsed > ALERT_PENDING_DURATION_S (60s)
        now_epoch=100.0,
    )
    assert state == "Firing"


def test_firing_at_exact_pending_duration_boundary():
    state = _alert_state(
        error_rate=ALERT_ERROR_RATE_THRESHOLD,
        pending_since_epoch=100.0 - ALERT_PENDING_DURATION_S,
        now_epoch=100.0,
    )
    assert state == "Firing"
