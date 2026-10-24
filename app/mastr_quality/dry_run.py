"""Dry-run plan: which stored positions WOULD change, and why. Writes nothing to any database.

Inputs
  --units   source units XML (the trusted source fields)
  --state   JSON list of the current stored rows:
            [{"mastr_number": "...", "latitude": ..., "longitude": ...}, ...]
            (export of the target table; this tool never connects to a database)
Output
  a JSON report with one action per source unit plus counts.

Safety rules (each is covered by a test):
  * a stored position that is already valid is NEVER replaced (even if the
    source differs: that is reported as a conflict, not changed)
  * a position is only proposed when BOTH source coordinates parse cleanly
  * nothing is guessed, geocoded or inferred
  * idempotent: after applying the plan, a second plan has zero changes
  * rows missing from the target are reported, never inserted

Run:
    python -m app.mastr_quality.dry_run --units UNITS.xml --state STATE.json --out REPORT.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from app.mastr_quality.coordinates import parse_coordinate
from app.mastr_quality.xml_adapter import (
    LATITUDE,
    LONGITUDE,
    UNIT_ID,
    clean_id,
    field,
    read_units,
)

TOLERANCE = 1e-6  # degrees; differences below this are not "conflicts"


def plan_updates(units: list[dict], state_rows: list[dict]) -> list[dict]:
    """One action per source unit. Pure function: inputs are not modified."""
    state = {str(r["mastr_number"]): r for r in state_rows}
    id_counts = Counter(clean_id(field(u, UNIT_ID)) for u in units)

    actions = []
    for unit in units:
        unit_id = clean_id(field(unit, UNIT_ID))
        base = {"unit_id": unit_id, "changed": False, "conflict": False,
                "reasons": [], "proposed": None}

        if unit_id is None:
            actions.append({**base, "action": "rejected", "reasons": ["missing_unit_id"]})
            continue
        if id_counts[unit_id] > 1:
            actions.append({**base, "action": "duplicate_source_id"})
            continue

        row = state.get(unit_id)
        if row is None:
            actions.append({**base, "action": "not_in_target"})
            continue

        existing_lat = parse_coordinate(row.get("latitude"), "lat")
        existing_lon = parse_coordinate(row.get("longitude"), "lon")
        source_lat = parse_coordinate(field(unit, LATITUDE), "lat")
        source_lon = parse_coordinate(field(unit, LONGITUDE), "lon")

        # 1. a valid stored position is known-good: never touch it
        if existing_lat.value is not None and existing_lon.value is not None:
            conflict = (
                source_lat.value is not None
                and source_lon.value is not None
                and (abs(source_lat.value - existing_lat.value) > TOLERANCE
                     or abs(source_lon.value - existing_lon.value) > TOLERANCE)
            )
            actions.append({**base, "action": "keep_existing", "conflict": conflict})
            continue

        # 2. stored position partly present or invalid: needs a human, no change
        if not (existing_lat.reason == "missing" and existing_lon.reason == "missing"):
            actions.append({**base, "action": "needs_review",
                            "reasons": [f"stored_latitude:{existing_lat.reason or 'ok'}",
                                        f"stored_longitude:{existing_lon.reason or 'ok'}"]})
            continue

        # 3. stored position empty: decide from the source
        rejected = [f"{name}:{r.reason}" for name, r in
                    (("latitude", source_lat), ("longitude", source_lon))
                    if r.reason in ("not_numeric", "out_of_range")]
        if rejected:
            actions.append({**base, "action": "rejected", "reasons": rejected})
        elif source_lat.value is not None and source_lon.value is not None:
            actions.append({**base, "action": "fill", "changed": True,
                            "proposed": {"latitude": source_lat.value,
                                         "longitude": source_lon.value}})
        elif source_lat.value is None and source_lon.value is None:
            actions.append({**base, "action": "no_source_position"})
        else:
            actions.append({**base, "action": "source_incomplete"})
    return actions


def apply_plan(state_rows: list[dict], actions: list[dict]) -> list[dict]:
    """Return a NEW state with the planned fills applied (used by tests and for review).

    The real integration applies the same fills with a guarded UPDATE
    (see README: only where latitude and longitude IS NULL).
    """
    fills = {a["unit_id"]: a["proposed"] for a in actions if a["action"] == "fill"}
    result = []
    for row in state_rows:
        new_row = dict(row)
        proposal = fills.get(str(row["mastr_number"]))
        if proposal is not None:
            new_row.update(proposal)
        result.append(new_row)
    return result


def summarize(actions: list[dict]) -> dict:
    counts = Counter(a["action"] for a in actions)
    reasons = Counter(r for a in actions if a["action"] == "rejected" for r in a["reasons"])
    return {
        "records_checked": len(actions),
        "records_changed": counts["fill"],
        "records_rejected": counts["rejected"],
        "records_kept_existing": counts["keep_existing"],
        "conflicts_kept_not_changed": sum(1 for a in actions if a["conflict"]),
        "needs_review": counts["needs_review"],
        "not_in_target": counts["not_in_target"],
        "no_source_position": counts["no_source_position"],
        "source_incomplete": counts["source_incomplete"],
        "duplicate_source_id": counts["duplicate_source_id"],
        "rejected_reasons": dict(sorted(reasons.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run coordinate repair plan (writes only the report).")
    parser.add_argument("--units", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    units = read_units(args.units)
    state_rows = json.loads(Path(args.state).read_text(encoding="utf-8"))
    actions = plan_updates(units, state_rows)
    report = {"mode": "dry-run (nothing was written to any database)",
              "summary": summarize(actions), "actions": actions}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for key, value in report["summary"].items():
        if key != "rejected_reasons":
            print(f"{key:30} {value}")
    print(f"report written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
