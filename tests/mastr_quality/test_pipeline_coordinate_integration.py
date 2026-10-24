from types import SimpleNamespace

from app.database.repositories.energy_asset_repository import EnergyAssetRepository
from app.parsers.mastr_parser import MaStRParser
from app.transformers.mastr_transformer import MaStRTransformer


def _transformer():
    transformer = object.__new__(MaStRTransformer)
    transformer.country_code = "DE"
    return transformer


def _asset(**overrides):
    values = {
        "source": "mastr",
        "name": "synthetic test asset",
        "location_id": None,
        "operator_name": None,
        "operator_mastr_number": None,
        "city": None,
        "postal_code": None,
        "energy_type": None,
        "gross_power_kw": None,
        "net_power_kw": None,
        "status": None,
        "latitude": None,
        "longitude": None,
        "geometry": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_transformer_parses_decimal_dot_and_comma():
    result = _transformer().transform_record({
        "MaStRNummer": "SEE-SYNTHETIC-1",
        "Breitengrad": "48.123",
        "Laengengrad": "11,234",
    })
    assert result["location"]["latitude"] == 48.123
    assert result["location"]["longitude"] == 11.234


def test_transformer_rejects_out_of_range_coordinate():
    result = _transformer().transform_record({
        "MaStRNummer": "SEE-SYNTHETIC-2",
        "Breitengrad": "148,5",
        "Laengengrad": "9.0",
    })
    assert result["location"]["latitude"] is None
    assert result["location"]["longitude"] == 9.0


def test_entity_parser_does_not_create_geometry_from_invalid_latitude():
    asset = MaStRParser()._build_entity({
        "mastr_number": "SEE-SYNTHETIC-3",
        "location": {"latitude": "148.5", "longitude": "9.0"},
    })
    assert asset is not None
    assert asset.latitude is None
    assert asset.longitude == 9.0
    assert asset.geometry is None


def test_repository_does_not_erase_existing_position_when_incoming_is_missing():
    repository = object.__new__(EnergyAssetRepository)
    stored_geometry = object()
    existing = _asset(latitude=51.0, longitude=6.0, geometry=stored_geometry)
    incoming = _asset()

    repository.update_from_entity(existing, incoming)

    assert existing.latitude == 51.0
    assert existing.longitude == 6.0
    assert existing.geometry is stored_geometry


def test_repository_does_not_replace_existing_position_with_conflicting_position():
    repository = object.__new__(EnergyAssetRepository)
    stored_geometry = object()
    existing = _asset(latitude=51.0, longitude=6.0, geometry=stored_geometry)
    incoming = _asset(
        latitude=48.123,
        longitude=11.234,
        geometry=object(),
    )

    repository.update_from_entity(existing, incoming)

    assert existing.latitude == 51.0
    assert existing.longitude == 6.0
    assert existing.geometry is stored_geometry


def test_repository_fills_only_a_completely_empty_position():
    repository = object.__new__(EnergyAssetRepository)
    incoming_geometry = object()
    existing = _asset()
    incoming = _asset(
        latitude=48.123,
        longitude=11.234,
        geometry=incoming_geometry,
    )

    repository.update_from_entity(existing, incoming)

    assert existing.latitude == 48.123
    assert existing.longitude == 11.234
    assert existing.geometry is incoming_geometry


def test_repository_does_not_auto_replace_a_partial_position():
    repository = object.__new__(EnergyAssetRepository)
    existing = _asset(latitude=51.0, longitude=None)
    incoming = _asset(
        latitude=48.123,
        longitude=11.234,
        geometry=object(),
    )

    repository.update_from_entity(existing, incoming)

    assert existing.latitude == 51.0
    assert existing.longitude is None
    assert existing.geometry is None
