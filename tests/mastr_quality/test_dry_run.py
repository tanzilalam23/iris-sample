import json

from app.mastr_quality.dry_run import apply_plan, main, plan_updates, summarize
from app.mastr_quality.xml_adapter import read_units


def _state(path):
    return json.loads(path.read_text())


def _by_id(actions):
    return {a["unit_id"]: a for a in actions}


def test_dry_run_reports_changed_and_rejected(units_xml, state_json):
    actions = plan_updates(read_units(units_xml), _state(state_json))
    summary = summarize(actions)
    assert summary["records_checked"] == 8
    assert summary["records_changed"] == 1
    assert summary["records_rejected"] == 2
    assert summary["rejected_reasons"] == {
        "latitude:not_numeric": 1, "latitude:out_of_range": 1,
    }
    by_id = _by_id(actions)
    assert by_id["SEE9000000001"]["proposed"] == {"latitude": 48.123, "longitude": 11.234}
    assert by_id["SEE9000000007"]["action"] == "not_in_target"   # never inserted
    assert by_id["SEE9000000003"]["action"] == "no_source_position"  # nothing invented


def test_known_valid_geometry_is_never_replaced(units_xml, state_json):
    state = _state(state_json)
    actions = plan_updates(read_units(units_xml), state)
    by_id = _by_id(actions)
    # source says 51.2 / 6.8 but a valid position (51.0 / 6.0) is stored
    assert by_id["SEE9000000006"]["action"] == "keep_existing"
    assert by_id["SEE9000000006"]["conflict"] is True
    assert by_id["SEE9000000006"]["changed"] is False
    new_state = apply_plan(state, actions)
    for before, after in zip(state, new_state):
        if before["latitude"] is not None and before["longitude"] is not None:
            assert after == before


def test_partial_stored_position_goes_to_review_not_overwritten(units_xml, state_json):
    by_id = _by_id(plan_updates(read_units(units_xml), _state(state_json)))
    assert by_id["SME9000000005"]["action"] == "needs_review"
    assert by_id["SME9000000005"]["changed"] is False


def test_dry_run_is_idempotent(units_xml, state_json):
    units, state = read_units(units_xml), _state(state_json)
    first = plan_updates(units, state)
    state_after = apply_plan(state, first)
    second = plan_updates(units, state_after)
    assert summarize(first)["records_changed"] == 1
    assert summarize(second)["records_changed"] == 0
    # applying twice gives the same state
    assert apply_plan(state_after, second) == state_after


def test_plan_does_not_modify_its_inputs(units_xml, state_json):
    units, state = read_units(units_xml), _state(state_json)
    before = json.dumps([units, state], sort_keys=True)
    plan_updates(units, state)
    assert json.dumps([units, state], sort_keys=True) == before


def test_zero_coordinates_are_values_not_missing():
    units = [{"EinheitMastrNummer": "SEE1", "Breitengrad": "10", "Laengengrad": "10"}]
    state = [{"mastr_number": "SEE1", "latitude": 0.0, "longitude": 0.0}]
    action = plan_updates(units, state)[0]
    assert action["action"] == "keep_existing"       # 0.0 is a stored value


def test_source_with_one_coordinate_is_not_filled():
    units = [{"EinheitMastrNummer": "SEE1", "Breitengrad": "10.5", "Laengengrad": "  "}]
    state = [{"mastr_number": "SEE1", "latitude": None, "longitude": None}]
    action = plan_updates(units, state)[0]
    assert action["action"] == "source_incomplete"
    assert action["changed"] is False


def test_duplicate_source_ids_are_not_applied():
    units = [
        {"EinheitMastrNummer": "SEE1", "Breitengrad": "10.5", "Laengengrad": "9.5"},
        {"EinheitMastrNummer": "SEE1", "Breitengrad": "20.5", "Laengengrad": "9.5"},
    ]
    state = [{"mastr_number": "SEE1", "latitude": None, "longitude": None}]
    actions = plan_updates(units, state)
    assert {a["action"] for a in actions} == {"duplicate_source_id"}
    assert apply_plan(state, actions) == state


def test_cli_writes_only_the_report(units_xml, state_json, tmp_path):
    state_before = state_json.read_text()
    out = tmp_path / "report.json"
    rc = main(["--units", str(units_xml), "--state", str(state_json), "--out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["summary"]["records_changed"] == 1
    assert "nothing was written" in report["mode"]
    assert state_json.read_text() == state_before     # input state untouched
