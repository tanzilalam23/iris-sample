"""Read MaStR bulk-export style XML into plain dicts, without cleaning.

Source fields are preserved exactly as text (including "11,234", blanks
and bad values). Parsing and judging values happens later, in the audit
and dry-run, using the dedicated coordinate and capacity parsers.

TAG NAMES, as given in the MaStR Gesamtdatenexport documentation (revision 26.2,
1 October 2026, checked by the author). Defined here in one place; lookups are
case-insensitive. The linked-units list is documented as a comma-separated string.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from app.mastr_quality.coordinates import parse_coordinate

# --- units file (modelled on EinheitenStromSpeicher.xml) -------------------
UNIT_ID = "EinheitMastrNummer"
LATITUDE = "Breitengrad"
LONGITUDE = "Laengengrad"
STORAGE_LINK = "SpeMaStRNummer"

# --- storage file (modelled on AnlagenStromSpeicher.xml) -------------------
STORAGE_ID = "MaStRNummer"
CAPACITY = "NutzbareSpeicherkapazitaet"
LINKED_UNITS = "VerknuepfteEinheitenMaStRNummern"


def field(record: dict, name: str):
    """Case-insensitive field lookup (guards against SpeMaStRNummer vs SpeMastrNummer)."""
    wanted = name.lower()
    for key, value in record.items():
        if key.lower() == wanted:
            return value
    return None


def clean_id(value) -> str | None:
    """Identifier text -> stripped string, or None when blank/absent."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def prefix_of(identifier: str | None) -> str:
    """First three letters of a MaStR number (SEE, SME, SSE...), else UNKNOWN."""
    if identifier and re.match(r"^[A-Za-z]{3}", identifier):
        return identifier[:3].upper()
    return "UNKNOWN"


def split_id_list(value) -> list[str]:
    """'A;B', 'A, B' or 'A B' -> ['A', 'B'] (empty/None -> [])."""
    if value is None:
        return []
    return [p for p in re.split(r"[;,\s]+", str(value)) if p]


def _record_to_dict(record: ET.Element) -> dict:
    out: dict = {}
    for child in record:
        if len(child):  # nested list elements -> joined with ';'
            parts = [(c.text or "").strip() for c in child]
            out[child.tag] = ";".join(p for p in parts if p)
        else:
            out[child.tag] = child.text  # None when the element is empty
    return out


def iter_records(path: str | Path):
    """Yield each direct child of the XML root as a dict of tag -> raw text.

    Uses iterparse and clears elements, so large exports do not need to fit
    in memory. Note: Python's stdlib XML parser is fine for trusted files;
    for untrusted XML use the defusedxml package.
    """
    depth = 0
    for event, elem in ET.iterparse(str(path), events=("start", "end")):
        if event == "start":
            depth += 1
            continue
        depth -= 1
        if depth == 1:  # a record directly under the root just closed
            record = _record_to_dict(elem)
            elem.clear()
            yield record


def read_units(path: str | Path) -> list[dict]:
    return list(iter_records(path))


def read_storage_objects(path: str | Path) -> dict[str, dict]:
    """Storage objects keyed by their identifier. Records without an ID are skipped."""
    storages: dict[str, dict] = {}
    for record in iter_records(path):
        storage_id = clean_id(field(record, STORAGE_ID))
        if storage_id is not None:
            storages[storage_id] = record
    return storages


def to_pipeline_record(unit: dict) -> dict:
    """Shape a unit like the existing pipeline's merged.json records.

    The existing transformer copies Breitengrad/Laengengrad straight through.
    This function is the safe replacement: parsed floats, or None with the
    rejection reason kept, never a guessed value.
    """
    lat = parse_coordinate(field(unit, LATITUDE), "lat")
    lon = parse_coordinate(field(unit, LONGITUDE), "lon")
    return {
        "MaStRNummer": clean_id(field(unit, UNIT_ID)),
        "Breitengrad": lat.value,
        "Laengengrad": lon.value,
        "coordinate_rejections": {
            "Breitengrad": lat.reason,
            "Laengengrad": lon.reason,
        },
    }
