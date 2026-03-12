from streaming.redis_client import _stringify_mapping


def test_stringify_mapping_handles_none_values() -> None:
    payload = _stringify_mapping({"a": 1, "b": None, "c": 2.5})
    assert payload == {"a": "1", "b": "", "c": "2.5"}
