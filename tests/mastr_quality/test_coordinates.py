import pytest
from app.mastr_quality.coordinates import parse_coordinate


@pytest.mark.parametrize("raw, kind, expected", [
    ("48.123", "lat", 48.123),    # dot is a DECIMAL point, not thousands
    ("48,123", "lat", 48.123),    # comma is a decimal mark too
    ("-7.123", "lon", -7.123),
    ("11,234", "lon", 11.234),
    ("  51.5 ", "lat", 51.5),     # whitespace
    ("+9.1", "lon", 9.1),         # explicit plus sign
    (48.123, "lat", 48.123),      # already a float
    ("0", "lat", 0.0),            # zero is a real value, not "missing"
])
def test_valid_values(raw, kind, expected):
    result = parse_coordinate(raw, kind)
    assert result.reason is None
    assert result.value == pytest.approx(expected)


def test_dot_decimal_is_never_read_as_thousands():
    assert parse_coordinate("48.123", "lat").value != 48123
    assert parse_coordinate("48,123", "lat").value != 48123


@pytest.mark.parametrize("raw, kind, reason", [
    ("90.5", "lat", "out_of_range"),
    ("-91", "lat", "out_of_range"),
    ("148,5", "lat", "out_of_range"),
    ("180.1", "lon", "out_of_range"),
    ("abc", "lat", "not_numeric"),
    ("1,234.5", "lat", "not_numeric"),   # two separators: ambiguous, reject
    ("48.123.456", "lat", "not_numeric"),
    (float("nan"), "lat", "not_numeric"),
    ("", "lat", "missing"),
    ("   ", "lon", "missing"),
    (None, "lat", "missing"),
])
def test_rejections_have_a_reason(raw, kind, reason):
    result = parse_coordinate(raw, kind)
    assert result.value is None
    assert result.reason == reason