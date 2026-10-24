"""Audit of MaStR storage units: source prefix, storage link, capacity, location quality.

Reads the SOURCE records (units XML + storage-object XML), because the
existing pipeline drops the storage link before the database.

NULL handling is zero-safe: a value is "missing" only when it is absent or
blank. A real 0 (capacity 0, latitude 0) is a value, never NULL.

Run:
    python -m app.mastr_quality.audit --units UNITS.xml --storage STORAGE.xml --out-dir OUT
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from app.mastr_quality.capacity import parse_capacity
from app.mastr_quality.coordinates import parse_coordinate
from app.mastr_quality.xml_adapter import (
    CAPACITY,
    LATITUDE,
    LINKED_UNITS,
    LONGITUDE,
    STORAGE_LINK,
    UNIT_ID,
    clean_id,
    field,
    prefix_of,
    read_storage_objects,
    read_units,
    split_id_list,
)

REJECTING_REASONS = ("not_numeric", "out_of_range")

CAPACITY_COUNTER = {
    "positive": "positive_capacity",
    "zero": "zero_capacity",
    "null": "null_capacity",
    "invalid": "invalid_capacity",
}


def classify_capacity(storage: dict | None) -> tuple[float | None, str]:
    """(value, status). Status: positive / zero / null / invalid / no_storage_object."""
    if storage is None:
        return None, "no_storage_object"
    result = parse_capacity(field(storage, CAPACITY))
    if result.reason == "missing":
        return None, "null"
    if result.reason is not None:
        return None, "invalid"
    # zero-safe: compare with None-check semantics, never truthiness
    if result.value > 0:
        return result.value, "positive"
    return result.value, "zero"


def classify_unit(unit: dict, storages: dict[str, dict]) -> dict:
    unit_id = clean_id(field(unit, UNIT_ID))
    storage_id = clean_id(field(unit, STORAGE_LINK))

    if storage_id is None:
        link_status, storage = "unlinked", None
    elif storage_id in storages:
        link_status, storage = "linked", storages[storage_id]
    else:
        link_status, storage = "dangling_link", None

    capacity_value, capacity_status = classify_capacity(storage)

    lat = parse_coordinate(field(unit, LATITUDE), "lat")
    lon = parse_coordinate(field(unit, LONGITUDE), "lon")
    if lat.value is not None and lon.value is not None:
        location = "precise"
    elif lat.reason in REJECTING_REASONS or lon.reason in REJECTING_REASONS:
        location = "rejected"
    elif lat.value is None and lon.value is None:
        location = "missing"
    else:
        location = "partial"

    return {
        "unit_id": unit_id,
        "prefix": prefix_of(unit_id),
        "storage_id": storage_id,
        "link_status": link_status,
        "capacity_kwh": capacity_value,
        "capacity_status": capacity_status,
        "latitude": lat.value,
        "longitude": lon.value,
        "latitude_reason": lat.reason,
        "longitude_reason": lon.reason,
        "location_quality": location,
        # the "linked + positive capacity + no usable position" population
        "storage_ready_without_geometry": (
            link_status == "linked"
            and capacity_status == "positive"
            and location != "precise"
        ),
    }


def _blank_counts() -> dict:
    return {
        "units": 0,
        "linked": 0,
        "dangling_link": 0,
        "unlinked": 0,
        "positive_capacity": 0,
        "zero_capacity": 0,
        "null_capacity": 0,
        "invalid_capacity": 0,
        "precise": 0,
        "partial": 0,
        "missing": 0,
        "rejected": 0,
        "coord_value_missing": 0,
        "coord_value_not_numeric": 0,
        "coord_value_out_of_range": 0,
        "storage_ready_without_geometry": 0,
    }


def build_audit(units: list[dict], storages: dict[str, dict]) -> tuple[dict, list[dict]]:
    """Return (summary, per-unit rows). Does not modify its inputs."""
    rows = [classify_unit(u, storages) for u in units]

    by_prefix: dict[str, dict] = {}
    value_reasons: Counter = Counter()
    for row in rows:
        counts = by_prefix.setdefault(row["prefix"], _blank_counts())
        counts["units"] += 1
        counts[row["link_status"]] += 1
        capacity_key = CAPACITY_COUNTER.get(row["capacity_status"])
        if capacity_key:  # units with no storage object have no capacity to count
            counts[capacity_key] += 1
        counts[row["location_quality"]] += 1
        counts["storage_ready_without_geometry"] += int(row["storage_ready_without_geometry"])
        for reason in (row["latitude_reason"], row["longitude_reason"]):
            if reason:
                value_reasons[reason] += 1
                counts[f"coord_value_{reason}"] += 1

    overall = _blank_counts()
    for counts in by_prefix.values():
        for key, value in counts.items():
            overall[key] += value

    # ---- relationships: one storage object can serve many units ----------
    units_by_storage: dict[str, list[str]] = {}
    for row in rows:
        if row["storage_id"] and row["unit_id"]:
            units_by_storage.setdefault(row["storage_id"], []).append(row["unit_id"])

    mismatches = 0
    orphan = 0
    for storage_id, storage in storages.items():
        listed = set(split_id_list(field(storage, LINKED_UNITS)))
        referencing = set(units_by_storage.get(storage_id, []))
        if not listed and not referencing:
            orphan += 1
        elif listed != referencing:
            mismatches += 1

    per_storage_units = [len(v) for k, v in units_by_storage.items() if k in storages]
    unique_capacity = 0.0
    capacity_status_counts: Counter = Counter()
    for storage in storages.values():
        value, status = classify_capacity(storage)
        capacity_status_counts[status] += 1
        if status == "positive":
            unique_capacity += value

    naive_capacity = sum(
        r["capacity_kwh"] for r in rows if r["capacity_status"] == "positive"
    )

    storage_by_prefix: dict[str, dict] = {}
    for storage_id, storage in storages.items():
        sc = storage_by_prefix.setdefault(prefix_of(storage_id), {
            "storage_objects": 0, "storage_positive_capacity": 0, "storage_zero_capacity": 0,
            "storage_null_capacity": 0, "storage_invalid_capacity": 0,
            "storage_linked_units": 0, "storage_with_multiple_units": 0, "storage_orphan": 0,
        })
        sc["storage_objects"] += 1
        _, status = classify_capacity(storage)
        sc[f"storage_{status}_capacity"] += 1
        referencing = len(units_by_storage.get(storage_id, []))
        sc["storage_linked_units"] += referencing
        sc["storage_with_multiple_units"] += int(referencing > 1)
        sc["storage_orphan"] += int(referencing == 0 and not split_id_list(field(storage, LINKED_UNITS)))

    id_counts = Counter(r["unit_id"] for r in rows if r["unit_id"])
    summary = {
        "note": (
            "Computed from source records. Empty/NULL is never counted as 0. "
            "Field names are assumptions modelled on the MaStR bulk export; "
            "see README_MASTR_FIX.md."
        ),
        "overall": overall,
        "by_prefix": dict(sorted(by_prefix.items())),
        "storage_objects_by_prefix": dict(sorted(storage_by_prefix.items())),
        "coordinate_value_reasons": dict(sorted(value_reasons.items())),
        "relationships": {
            "storage_objects": len(storages),
            "storage_objects_by_capacity_status": dict(sorted(capacity_status_counts.items())),
            "storage_objects_with_multiple_units": sum(1 for n in per_storage_units if n > 1),
            "max_units_per_storage_object": max(per_storage_units, default=0),
            "orphan_storage_objects": orphan,
            "link_vs_list_mismatches": mismatches,
            "duplicate_unit_ids": sum(1 for n in id_counts.values() if n > 1),
            "capacity_kwh_counted_once_per_storage_object": round(unique_capacity, 6),
            "capacity_kwh_naive_sum_per_unit": round(naive_capacity, 6),
        },
    }
    return summary, rows


def write_audit(summary: dict, rows: list[dict], out_dir: str | Path) -> list[Path]:
    """Write audit.json, audit_by_prefix.csv, audit_units.csv. Empty CSV cell = NULL."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / "audit.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    prefix_path = out / "audit_by_prefix.csv"
    prefix_rows = [{"record_type": "unit", "prefix": p, **c} for p, c in summary["by_prefix"].items()]
    prefix_rows += [{"record_type": "storage_object", "prefix": p, **c}
                    for p, c in summary["storage_objects_by_prefix"].items()]
    prefix_rows.append({"record_type": "all_units", "prefix": "ALL", **summary["overall"]})
    fieldnames: list[str] = []
    for row in prefix_rows:  # union of columns; a blank cell = not applicable to that row type
        fieldnames += [k for k in row if k not in fieldnames]
    with prefix_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, restval="")
        writer.writeheader()
        writer.writerows(prefix_rows)

    units_path = out / "audit_units.csv"
    with units_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["unit_id"])
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})

    return [json_path, prefix_path, units_path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit MaStR storage units (read-only).")
    parser.add_argument("--units", required=True, help="units XML (EinheitenStromSpeicher style)")
    parser.add_argument("--storage", required=True, help="storage XML (AnlagenStromSpeicher style)")
    parser.add_argument("--out-dir", required=True, help="where to write the audit files")
    args = parser.parse_args(argv)

    summary, rows = build_audit(read_units(args.units), read_storage_objects(args.storage))
    for path in write_audit(summary, rows, args.out_dir):
        print(f"wrote {path}")
    overall = summary["overall"]
    print(
        f"units={overall['units']} linked={overall['linked']} "
        f"storage_ready_without_geometry={overall['storage_ready_without_geometry']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
