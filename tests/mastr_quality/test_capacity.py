import pytest
from app.mastr_quality.capacity import parse_capacity
from app.mastr_quality.coordinates import parse_coordinate


@pytest.mark.parametrize("raw, expected", [
    ("5000", 5000.0),
    ("5000.5", 5000.5),      # XML decimals use a dot
    ("5000,5", 5000.5),
    ("1.250,5", 1250.5),     # German: dot = thousands, comma = decimal
    ("1,250.5", 1250.5),     # English style
    ("1.250.000", 1250000.0),
    ("1.250", 1.25),         # single dot = decimal (documented choice)
    (" 12 ", 12.0),
    ("0", 0.0),              # zero is a real value
    (0, 0.0),
    (7.5, 7.5),
])
def test_valid_capacity(raw, expected):
    result = parse_capacity(raw)
    assert result.reason is None
    assert result.value == pytest.approx(expected)


@pytest.mark.parametrize("raw, reason", [
    (None, "missing"),
    ("", "missing"),
    ("   ", "missing"),
    ("abc", "not_numeric"),
    ("1.2.3", "not_numeric"),
    ("1,25,5", "not_numeric"),
    ("1.234,56,7", "not_numeric"),
    (float("nan"), "not_numeric"),
    ("-5", "negative"),
])
def test_rejected_capacity(raw, reason):
    result = parse_capacity(raw)
    assert result.value is None
    assert result.reason == reason


def test_capacity_and_coordinate_parsers_are_independent():
    # Fine as a capacity, impossible as a coordinate
    assert parse_capacity("1.250,5").value == pytest.approx(1250.5)
    assert parse_coordinate("1.250,5", "lat").reason == "not_numeric"