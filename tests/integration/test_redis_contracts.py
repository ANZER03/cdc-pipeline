import json


def test_traffic_contract_shape() -> None:
    payload = {"timestamp": 1709654400000, "value": 1247, "label": "02:15:30 PM"}
    serialized = json.dumps(payload)
    restored = json.loads(serialized)

    assert set(restored) == {"timestamp", "value", "label"}
    assert isinstance(restored["timestamp"], int)
    assert isinstance(restored["value"], int)
    assert isinstance(restored["label"], str)
