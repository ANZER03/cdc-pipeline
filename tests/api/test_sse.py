from api.services.sse_manager import SSEManager


def test_encode_event_formats_sse_payload() -> None:
    encoded = SSEManager.encode_event("metrics", {"activeUsers": 1})
    assert encoded == 'event: metrics\ndata: {"activeUsers":1}\n\n'
