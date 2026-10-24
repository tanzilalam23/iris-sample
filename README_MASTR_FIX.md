# IRIS-48H-01 — MaStR coordinate parsing and storage classification

A tested, non-destructive vertical slice. One deterministic fixture, one code path.
No database access, no scraping, no credentials, no fabricated production coordinates.

## What this change contains (quality tools and integration updates)

| File | Purpose |
|---|---|
| `app/mastr_quality/coordinates.py` | Coordinate-only parser (dot/comma decimals, whitespace, signs, range check, reasons) |
| `app/mastr_quality/capacity.py` | Capacity parser, kept independent from coordinates |
| `app/mastr_quality/xml_adapter.py` | Reads MaStR bulk-export style XML into dicts, source text preserved; `to_pipeline_record()` adapter |
| `app/mastr_quality/audit.py` | Audit by source prefix, storage link, capacity, location quality (JSON + CSV) |
| `app/mastr_quality/dry_run.py` | Dry-run repair plan (changed / rejected / kept), idempotent, never overwrites a valid position |
| `app/transformers/mastr_transformer.py` | Parses and validates source coordinates during transformation |
| `app/parsers/mastr_parser.py` | Validates coordinates before creating geometry |
| `app/database/repositories/energy_asset_repository.py` | Protects existing positions during entity updates |
| `tests/mastr_quality/` | pytest suite (parsers, adapter, audit, dry-run, integration) |
| `tests/fixtures/` | Synthetic XML fixtures + a synthetic "current table state" JSON |
| `audit_sample/` | Output of the audit and dry-run on the fixtures |
| `pytest.ini` | Makes `pytest` look only in `tests/` (the repo's top-level `test_map_renderer.py` is a manual database script) |

## Finding about the provided repository

`_number()` does **not exist** in the files provided. `app/transformers/mastr_transformer.py`
copies `Breitengrad` / `Laengengrad` unchanged and `app/parsers/mastr_parser.py` only checks
`is not None` before building a `Point`. So the generic-parser bug described in the brief lives
in code that is not in this copy, and the existing path also performs **no range check**.
The coordinate parser is now integrated into the transformer and entity parser. The repository update path also protects existing positions.
The existing pipeline also drops the storage link before the database, which is why the audit
reads the source XML.

## Setup (macOS / Linux, isolated environment)

```bash
python3.12 -m venv .venv          # project requires Python >= 3.12, as declared in pyproject.toml
source .venv/bin/activate
python -m pip install pytest "sqlalchemy>=2.0.51" "geoalchemy2>=0.20.0" "shapely>=2.1.2"
```

## Run the tests

```bash
python -m pytest -v | tee test_results.txt
```

Result of the last run is stored in `test_results.txt`.

## Run the audit (read-only)

```bash
python -m app.mastr_quality.audit \
  --units tests/fixtures/mastr_units_sample.xml \
  --storage tests/fixtures/mastr_storage_sample.xml \
  --out-dir audit_sample
```

Writes `audit.json`, `audit_by_prefix.csv`, `audit_units.csv`. In `audit_units.csv` an empty cell
means NULL and a real zero is written as `0.0`.

`audit_by_prefix.csv` has one row per source prefix and a `record_type` column:
`unit` rows (SEE, SME; columns for link status, capacity, location quality and coordinate rejection
reasons), `storage_object` rows (SSE; columns starting `storage_`: objects, capacity status, linked
units, objects with several units, orphans) and one `all_units` row. A blank cell means the column
does not apply to that row type.

## Run the dry-run (writes only the report)

```bash
python -m app.mastr_quality.dry_run \
  --units tests/fixtures/mastr_units_sample.xml \
  --state tests/fixtures/current_state_sample.json \
  --out audit_sample/dry_run_report.json
```

`--state` is a JSON export of the stored rows (`mastr_number`, `latitude`, `longitude`).
The tool never connects to a database. Its state format has no geometry field, so it
cannot independently identify database rows with missing geometry. Expected fixture result:
1 changed, 2 rejected, 2 kept (1 of them a conflict that is reported but not changed),
1 needs review, 1 not in target, 1 without a source position.

## Rules the code follows

1. **Coordinates**: `48.123` and `48,123` are 48.123 (never 48123); `-7.123`, `11,234`, `+9.1`,
   padded text work; latitude outside ±90 or longitude outside ±180 is rejected with a reason;
   two separators (`1,234.5`) are rejected as ambiguous instead of guessed.
2. **Capacity** is parsed separately (it may legitimately contain thousands separators).
3. **Zero-safe NULL**: absent/blank = missing; `0` is a value (capacity 0, latitude 0).
4. **Source semantics**: prefix comes from the identifier (`SEE`, `SME`, `SSE`); the storage link
   is taken from the unit record; a link whose storage object is absent is reported as
   `dangling_link`, not as linked.
5. **One storage object can serve many units** (fixture: `SSE9000000001` ↔ two units).
   Capacity is attached to the storage object, so a naive per-unit sum double-counts it
   (fixture: 11251.5 kWh naive vs 6551.0 kWh counted once). The audit reports both.
6. **Dry-run**: a valid stored position is never replaced; a position is proposed only when both
   source coordinates parse; rows missing from the target are reported, never inserted;
   duplicate source IDs are not applied; planning twice after applying gives zero changes.

## Assumptions and open points (please read)

* **XML tag names** follow the MaStR Gesamtdatenexport documentation (revision 26.2, 1 October 2026):
  units `EinheitMastrNummer`, `Breitengrad`, `Laengengrad`, `SpeMaStRNummer`; storage objects
  `MaStRNummer`, `NutzbareSpeicherkapazitaet`, `VerknuepfteEinheitenMaStRNummern` (comma-separated
  string; semicolons and nested elements are also tolerated). They are defined once at the top of
  `xml_adapter.py`, and lookups ignore case. The fixture's root and record element names are
  modelled on the export's file structure and are not used for parsing (every record directly under
  the root is read). Re-check the tags if a later revision is used.
* **Prefixes**: the MaStR numbering concept defines SEE (generation unit), SME (migrated unit)
  and SSE (storage). The export documentation's own examples for storage identifiers may use a different
  prefix (SPE). The assessment's SSE cases are kept as required; a test also covers SPE identifiers
  with the documented tag spelling. The audit reports whatever prefix it finds and does not assume SSE only.
* The fixture is **entirely synthetic**: invented IDs, invented positions. No MaStR records were copied.
* The 13,790 / 8,718 figures from the brief were not reproduced (no production data was available).
  `storage_ready_without_geometry` is the same kind of population (linked + positive capacity +
  no precise position) computed on the fixture: 1 of 8.

## Engineering note

**Trade-offs.** The standalone coordinate/capacity parsing and XML audit utilities use the standard library and do not connect to a database. The integrated application path imports SQLAlchemy, GeoAlchemy2, and Shapely; its synthetic tests exercise that path without opening a database. The cost is
no spatial validation beyond ranges (no check that a point lies in Germany). The coordinate parser
rejects ambiguous inputs instead of guessing, so some recoverable values go to "rejected" and need
a human decision. A single dot in a capacity is read as a decimal (XML convention); a German string
using a lone dot as a thousands separator would be misread, so capacity should come from the XML,
not from formatted display text.

**Source and licence.** MaStR data is published under the Datenlizenz Deutschland — Namensnennung 2.0
(attribution required). This repository ships only synthetic data. XML is read with the stdlib
parser, which is fine for trusted files; use `defusedxml` for untrusted input. A single 1-to-many
link was modelled; real exports may contain further cases (units without storage objects,
storage objects listing units that no longer exist) that the audit counts but does not repair.

**Safe integration into IRIS.**
1. Coordinate validation is now integrated into `mastr_transformer.py` and
   `mastr_parser.py`. The transformer parses both source fields and emits `None`
   for invalid coordinates. The entity parser validates again before creating
   geometry. The ordinary transformed record does not retain rejection reasons;
   consult the original raw input when investigating one.

2. For existing rows, export the stored table to the `--state` JSON on a **staging copy**, run the
   dry-run, and review `dry_run_report.json` (changed / rejected / conflicts / needs review).
3. Apply only `fill` actions with a guarded update, inside a transaction, for example (documentation only):
   ```sql
   UPDATE iris_core.energy_assets t
   SET latitude = s.latitude, longitude = s.longitude,
       geometry = ST_SetSRID(ST_MakePoint(s.longitude, s.latitude), 4326)  -- note: lon, lat order
   FROM staging_position_fix s
   WHERE t.mastr_number = s.mastr_number
     AND t.latitude IS NULL AND t.longitude IS NULL AND t.geometry IS NULL;
   ```
   The `IS NULL` guard makes it idempotent and prevents overwriting a known position.
4. The repository update method now guards stored positions. It fills a
   completely empty position only when incoming latitude, longitude, and geometry
   are all valid. A valid stored coordinate pair is never overwritten. Missing
   geometry is filled only when incoming valid coordinates exactly match stored
   coordinates. Partial positions and conflicting values are not auto-corrected;
   they need separate review. Even a valid-but-outdated stored point is retained
   until a reviewed correction is approved.

5. Compare the affected-row count with the dry-run's `records_changed` before and after; take a
   backup first; do not re-import the 13,790 records.

**Not done / out of scope.** No national backfill, no production access, no geocoding, no storage-link
column in `energy_assets` (the table has none; adding one is a separate migration decision),
no verification against real export files.
