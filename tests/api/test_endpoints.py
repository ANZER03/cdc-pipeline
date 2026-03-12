from api.services.redis_service import _parse_number


def test_parse_number_handles_int_and_float_strings() -> None:
    assert _parse_number("12") == 12
    assert _parse_number("12.5") == 12.5


def test_parse_number_defaults_to_zero() -> None:
    assert _parse_number(None) == 0
    assert _parse_number("") == 0
