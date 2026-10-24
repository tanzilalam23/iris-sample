from app.mastr_quality.xml_adapter import (
    field,
    prefix_of,
    read_storage_objects,
    read_units,
    split_id_list,
    to_pipeline_record,
)


def test_units_are_read_with_source_values_preserved(units_xml):
    units = read_units(units_xml)
    assert len(units) == 8
    first = units[0]
    # nothing is cleaned or converted by the reader
    assert field(first, "Breitengrad") == "48.123"
    assert field(first, "Laengengrad") == "11,234"
    # absent element stays absent, empty element is None, blank text is kept
    assert field(units[2], "Breitengrad") is None
    assert field(units[5], "SpeMaStRNummer") is None
    assert field(units[4], "Laengengrad").strip() == ""


def test_field_lookup_ignores_case():
    assert field({"SpeMaStRNummer": "SSE1"}, "SPEMASTRNUMMER") == "SSE1"


def test_storage_objects_keyed_by_id(storage_xml):
    storages = read_storage_objects(storage_xml)
    assert sorted(storages) == [f"SSE90000000{n:02d}" for n in range(1, 6)]


def test_prefixes_and_id_lists():
    assert prefix_of("SEE9000000001") == "SEE"
    assert prefix_of("sme9000000005") == "SME"
    assert prefix_of(None) == "UNKNOWN"
    assert prefix_of("12345") == "UNKNOWN"
    assert split_id_list("A;B") == ["A", "B"]
    assert split_id_list(" A, B  C ") == ["A", "B", "C"]
    assert split_id_list(None) == []


def test_pipeline_record_gives_floats_not_thousands(units_xml):
    units = read_units(units_xml)
    record = to_pipeline_record(units[0])
    assert record["MaStRNummer"] == "SEE9000000001"
    assert record["Breitengrad"] == 48.123      # NOT 48123
    assert record["Laengengrad"] == 11.234      # NOT 11234
    bad = to_pipeline_record(units[3])           # latitude 148,5
    assert bad["Breitengrad"] is None
    assert bad["coordinate_rejections"]["Breitengrad"] == "out_of_range"
    assert bad["Laengengrad"] == 9.0             # the good half is kept
