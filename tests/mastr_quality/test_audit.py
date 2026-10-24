import csv
import json

import pytest

from app.mastr_quality.audit import build_audit, main, write_audit
from app.mastr_quality.xml_adapter import read_storage_objects, read_units


@pytest.fixture
def audit(units_xml, storage_xml):
    return build_audit(read_units(units_xml), read_storage_objects(storage_xml))


def test_linked_storage_is_separated_from_other_records(audit):
    summary, rows = audit
    status = {r["unit_id"]: r["link_status"] for r in rows}
    assert status["SEE9000000001"] == "linked"
    assert status["SEE9000000006"] == "unlinked"        # generation unit, no storage
    assert status["SME9000000005"] == "unlinked"        # migrated unit
    assert status["SEE9000000007"] == "dangling_link"   # storage id not in storage file
    overall = summary["overall"]
    assert (overall["linked"], overall["dangling_link"], overall["unlinked"]) == (5, 1, 2)


def test_totals_by_source_prefix(audit):
    by_prefix = audit[0]["by_prefix"]
    assert set(by_prefix) == {"SEE", "SME"}
    assert by_prefix["SEE"]["units"] == 7
    assert by_prefix["SME"]["units"] == 1
    assert by_prefix["SME"]["linked"] == 0
    assert by_prefix["SEE"]["precise"] == 4
    assert by_prefix["SEE"]["rejected"] == 2
    assert by_prefix["SEE"]["missing"] == 1
    assert by_prefix["SME"]["partial"] == 1


def test_zero_safe_null_treatment(audit):
    overall = audit[0]["overall"]
    assert overall["positive_capacity"] == 3
    assert overall["zero_capacity"] == 1     # real 0 is not NULL
    assert overall["null_capacity"] == 1     # absent element is NULL, not 0
    rows = {r["unit_id"]: r for r in audit[1]}
    assert rows["SEE9000000004"]["capacity_kwh"] == 0.0
    assert rows["SEE9000000008"]["capacity_kwh"] is None


def test_storage_ready_without_geometry_population(audit):
    # linked + positive capacity + no precise position: only unit 3 in the fixture
    flagged = [r["unit_id"] for r in audit[1] if r["storage_ready_without_geometry"]]
    assert flagged == ["SEE9000000003"]
    assert audit[0]["overall"]["storage_ready_without_geometry"] == 1


def test_rejected_reasons_are_counted(audit):
    assert audit[0]["coordinate_value_reasons"] == {
        "missing": 3, "not_numeric": 1, "out_of_range": 1,
    }


def test_one_to_many_relationship_is_documented_in_the_numbers(audit):
    rel = audit[0]["relationships"]
    assert rel["storage_objects"] == 5
    assert rel["storage_objects_with_multiple_units"] == 1   # SSE9000000001 serves 2 units
    assert rel["max_units_per_storage_object"] == 2
    assert rel["orphan_storage_objects"] == 1                # SSE9000000005
    assert rel["link_vs_list_mismatches"] == 0
    # naive per-unit sum counts the shared 5000.5 kWh twice
    assert rel["capacity_kwh_counted_once_per_storage_object"] == pytest.approx(6551.0)
    assert rel["capacity_kwh_naive_sum_per_unit"] == pytest.approx(11251.5)


def test_mismatch_between_link_and_list_is_detected():
    units = [{"EinheitMastrNummer": "SEE1", "SpeMaStRNummer": "SSE1"}]
    storages = {"SSE1": {"MaStRNummer": "SSE1", "NutzbareSpeicherkapazitaet": "10",
                         "VerknuepfteEinheitenMaStRNummern": "SEE1;SEE2"}}
    summary, _ = build_audit(units, storages)
    assert summary["relationships"]["link_vs_list_mismatches"] == 1


def test_inputs_are_not_modified(units_xml, storage_xml):
    units = read_units(units_xml)
    storages = read_storage_objects(storage_xml)
    before = json.dumps([units, storages], sort_keys=True)
    build_audit(units, storages)
    assert json.dumps([units, storages], sort_keys=True) == before


def test_report_files_are_written(units_xml, storage_xml, tmp_path):
    rc = main(["--units", str(units_xml), "--storage", str(storage_xml),
               "--out-dir", str(tmp_path)])
    assert rc == 0
    data = json.loads((tmp_path / "audit.json").read_text())
    assert data["overall"]["units"] == 8
    with (tmp_path / "audit_by_prefix.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert [r["prefix"] for r in rows] == ["SEE", "SME", "SSE", "ALL"]
    assert [r["record_type"] for r in rows] == ["unit", "unit", "storage_object", "all_units"]
    with (tmp_path / "audit_units.csv").open() as fh:
        unit_rows = list(csv.DictReader(fh))
    assert len(unit_rows) == 8
    # NULL is an empty cell, a real zero is "0.0"
    by_id = {r["unit_id"]: r for r in unit_rows}
    assert by_id["SEE9000000008"]["capacity_kwh"] == ""
    assert by_id["SEE9000000004"]["capacity_kwh"] == "0.0"


def test_spe_storage_ids_exact_case_tags_and_comma_lists_are_accepted():
    # Variant seen in newer export documentation: SPE storage ids,
    # SpeMaStRNummer / MaStRNummer spelling, comma-separated linked units.
    units = [
        {"EinheitMastrNummer": "SEE9000000001", "SpeMaStRNummer": "SPE9000000001",
         "Breitengrad": "48.123", "Laengengrad": "11.234"},
        {"EinheitMastrNummer": "SEE9000000002", "SpeMaStRNummer": "SPE9000000001"},
    ]
    storages = {"SPE9000000001": {
        "MaStRNummer": "SPE9000000001", "NutzbareSpeicherkapazitaet": "100",
        "VerknuepfteEinheitenMaStRNummern": "SEE9000000001, SEE9000000002"}}
    summary, rows = build_audit(units, storages)
    assert summary["overall"]["linked"] == 2
    assert summary["relationships"]["link_vs_list_mismatches"] == 0
    assert summary["relationships"]["storage_objects_with_multiple_units"] == 1
    assert rows[0]["location_quality"] == "precise"


def test_storage_object_prefix_totals_include_sse(audit):
    sse = audit[0]["storage_objects_by_prefix"]["SSE"]
    assert sse["storage_objects"] == 5
    assert sse["storage_positive_capacity"] == 3
    assert sse["storage_zero_capacity"] == 1
    assert sse["storage_null_capacity"] == 1
    assert sse["storage_linked_units"] == 5          # 2 + 1 + 1 + 1 + 0 referencing units
    assert sse["storage_with_multiple_units"] == 1
    assert sse["storage_orphan"] == 1


def test_rejection_reasons_are_reported_per_prefix(audit):
    see = audit[0]["by_prefix"]["SEE"]
    assert (see["coord_value_missing"], see["coord_value_not_numeric"],
            see["coord_value_out_of_range"]) == (2, 1, 1)
    sme = audit[0]["by_prefix"]["SME"]
    assert sme["coord_value_missing"] == 1
