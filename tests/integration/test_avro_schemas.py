import json

from scripts.generate_test_data import REQUEST_LOG_SCHEMA, SYSTEM_METRIC_SCHEMA, _encode_avro_json


def test_request_log_union_encoding() -> None:
    payload = {
        "id": 1,
        "endpoint": "/api/products",
        "method": "GET",
        "status_code": 200,
        "latency_ms": 120,
        "user_id": 5,
        "session_id": None,
        "region_name": "Japan",
        "created_at": 1709654400000,
    }

    encoded = _encode_avro_json(payload, REQUEST_LOG_SCHEMA)
    assert encoded["endpoint"] == {"string": "/api/products"}
    assert encoded["method"] == {"string": "GET"}
    assert encoded["user_id"] == {"long": 5}
    assert encoded["session_id"] is None


def test_system_metric_schema_serializes_to_json() -> None:
    payload = {
        "id": 1,
        "node_name": "api-node-1",
        "metric_name": "cpu_percent",
        "metric_value": 42.5,
        "recorded_at": 1709654400000,
    }
    encoded = _encode_avro_json(payload, SYSTEM_METRIC_SCHEMA)
    assert json.loads(json.dumps(encoded))["metric_name"] == "cpu_percent"
