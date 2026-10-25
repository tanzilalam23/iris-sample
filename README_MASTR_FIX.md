# IRIS-48H-01: MaStR coordinate parsing and storage classification

This is my 48-hour submission. It fixes how decimal coordinates are read, adds an audit report
for MaStR storage records, and adds a dry-run that shows what would change without changing anything.

It uses synthetic data only. It doesn't touch a database, doesn't scrape anything, uses no
credentials, and contains no real coordinates.

## What's in this branch

| File | What it does |
|---|---|
| `app/mastr_quality/coordinates.py` | Reads latitude and longitude. Accepts dot or comma decimals, spaces and signs. Rejects impossible values and says why. |
| `app/mastr_quality/capacity.py` | Reads capacity. Kept separate from coordinates on purpose. |
| `app/mastr_quality/xml_adapter.py` | Reads MaStR-style XML into plain dicts and keeps the source text as it is. `to_pipeline_record()` turns a unit into the record shape the pipeline already uses. |
| `app/mastr_quality/audit.py` | Counts records by source prefix, storage link, capacity and location quality (JSON and CSV). |
| `app/mastr_quality/dry_run.py` | Plans which positions could be filled, rejected or left alone. Running it twice changes nothing, and it never overwrites a valid position. |
| `app/transformers/mastr_transformer.py` | Now reads and checks coordinates while transforming records. |
| `app/parsers/mastr_parser.py` | Now checks coordinates before building the map point. |
| `app/database/repositories/energy_asset_repository.py` | Now stops an update from overwriting a stored position. |
| `tests/mastr_quality/` | The tests: parsers, XML reader, audit, dry-run, and the changes to the existing code. |
| `tests/fixtures/` | Made-up XML files and a made-up "current table" JSON. |
| `audit_sample/` | Output of the audit and the dry-run on those fixtures. |
| `pytest.ini` | Tells pytest to look only in `tests/` (the `test_map_renderer.py` in the repo root is a manual database script, not a test). |

## What I found in the repository

`_number()` is not in the files I was given. `app/transformers/mastr_transformer.py` copies
`Breitengrad` and `Laengengrad` as they are, and `app/parsers/mastr_parser.py` only checks for
`is not None` before building a `Point`. So the bug from the brief is in code that isn't in this
copy. The existing path also has **no range check**, so a latitude like 148.5 would have gone straight through.

I have now connected the new coordinate parser to the transformer and the entity parser, and the
repository update no longer overwrites a stored position.

The existing pipeline also drops the storage link before the data reaches the database. That is why
the audit reads the source XML.

## Setup (macOS / Linux, isolated environment)

```bash
python3.12 -m venv .venv          # the project needs Python >= 3.12, as declared in pyproject.toml
source .venv/bin/activate
python -m pip install pytest "sqlalchemy>=2.0.51" "geoalchemy2>=0.20.0" "shapely>=2.1.2"
```

## Run the tests

```bash
python -m pytest -v | tee test_results.txt
```

The result of the last run is saved in `test_results.txt`.

## Run the audit (read-only)

```bash
python -m app.mastr_quality.audit \
  --units tests/fixtures/mastr_units_sample.xml \
  --storage tests/fixtures/mastr_storage_sample.xml \
  --out-dir audit_sample
```

It writes `audit.json`, `audit_by_prefix.csv` and `audit_units.csv`. In `audit_units.csv`, an empty
cell means NULL, and a real zero is written as `0.0`.

`audit_by_prefix.csv` has one row per source prefix, with a `record_type` column:
- `unit` rows (SEE, SME): link status, capacity, location quality and coordinate rejection reasons.
- `storage_object` rows (SSE): columns starting with `storage_` (objects, capacity status, linked
  units, objects with several units, orphans).
- one `all_units` row with the totals.

A blank cell means that column doesn't apply to that kind of row.

## Run the dry-run (writes only the report)

```bash
python -m app.mastr_quality.dry_run \
  --units tests/fixtures/mastr_units_sample.xml \
  --state tests/fixtures/current_state_sample.json \
  --out audit_sample/dry_run_report.json
```

`--state` is a JSON export of the stored rows (`mastr_number`, `latitude`, `longitude`). The tool
never connects to a database. The state format has no geometry field, so the dry-run can't find rows
that are missing geometry on its own.

Expected result on the fixtures: 1 changed, 2 rejected, 2 kept (1 of them a conflict that is
reported but not changed), 1 needs review, 1 not in target, 1 without a source position.

## Rules the code follows

1. **Coordinates.** `48.123` and `48,123` both mean 48.123 (never 48123). `-7.123`, `11,234`, `+9.1`
   and padded text work. A latitude outside ±90 or a longitude outside ±180 is rejected with a reason.
   Two separators (`1,234.5`) are rejected as ambiguous instead of guessed.
2. **Capacity** is read separately, because it can legitimately have thousands separators.
3. **Zero-safe NULL.** Absent or blank means missing. `0` is a real value (capacity 0, latitude 0).
4. **Source semantics.** The prefix comes from the identifier (`SEE`, `SME`, `SSE`). The storage link
   comes from the unit record. If the linked storage object isn't in the storage file, the link is
   reported as `dangling_link`, not as linked.
5. **One storage object can serve many units** (in the fixture, `SSE9000000001` has two units).
   Capacity belongs to the storage object, so adding it up per unit counts it twice
   (fixture: 11251.5 kWh that way, 6551.0 kWh counted once). The audit reports both.
6. **Dry-run.** A valid stored position is never replaced. A position is proposed only when both
   source coordinates parse. Rows missing from the target are reported, never inserted. Duplicate
   source IDs are not applied. Planning a second time after applying gives zero changes.

## Assumptions and open points

* **XML tag names** follow the MaStR Gesamtdatenexport documentation (revision 26.2, 1 October 2026).
  Units: `EinheitMastrNummer`, `Breitengrad`, `Laengengrad`, `SpeMaStRNummer`. Storage objects:
  `MaStRNummer`, `NutzbareSpeicherkapazitaet`, `VerknuepfteEinheitenMaStRNummern` (a comma-separated
  string; semicolons and nested elements also work). They are defined once at the top of
  `xml_adapter.py`, and the lookup ignores upper/lower case. The root and record element names in the
  fixtures are modelled on the export's file structure and aren't used for parsing (every record
  directly under the root is read). Re-check the tags if you use a later revision.
* **Prefixes.** The MaStR numbering concept defines SEE (generation unit), SME (migrated unit) and
  SSE (storage). The export documentation's own examples for storage identifiers may use a different
  prefix (SPE). I kept the SSE cases the assessment asks for, and one test also covers SPE
  identifiers with the documented tag spelling. The audit reports whatever prefix it finds and
  doesn't assume SSE only.
* The fixtures are **entirely synthetic**: invented IDs and invented positions. No MaStR records were copied.
* I did not reproduce the 13,790 / 8,718 figures from the brief, because I had no production data.
  `storage_ready_without_geometry` is the same kind of count (linked, positive capacity, no precise
  position), computed on the fixtures: 1 of 8.

## Engineering note

**Trade-offs.** The coordinate and capacity parsing and the XML audit use only the standard library
and never connect to a database. The parts that plug into IRIS import SQLAlchemy, GeoAlchemy2 and
Shapely, and their tests run without opening a database.

The cost of keeping it simple: there is no spatial check beyond the ranges (nothing checks that a
point is in Germany). The coordinate parser rejects ambiguous values instead of guessing, so some
values that could be recovered end up as "rejected" and need a person to decide. A single dot in a
capacity is read as a decimal point, because that is how the XML writes it. A German value that
uses a lone dot as a thousands separator would be misread, so capacity should come from the XML and
not from formatted text.

**Source and licence.** MaStR data is published under the Datenlizenz Deutschland, Namensnennung 2.0
(attribution required). This repository contains only synthetic data. The XML is read with the
standard library parser, which is fine for trusted files; use `defusedxml` for untrusted input. I
modelled a single 1-to-many link. Real exports may have other cases (units without storage objects,
storage objects that list units that no longer exist). The audit counts those but doesn't repair them.

**Safe integration into IRIS.**
1. Coordinate checks are now part of `mastr_transformer.py` and `mastr_parser.py`. The transformer
   parses both source fields and outputs `None` for any invalid coordinate. The entity parser checks
   them again before it creates geometry. The transformed record doesn't keep the rejection reason,
   so when you investigate one, look at the original raw input.
2. For existing rows, export the stored table to the `--state` JSON on a **staging copy**, run the
   dry-run, and review `dry_run_report.json` (changed, rejected, conflicts, needs review).
3. Apply only the `fill` actions, with a guarded update inside a transaction. For example
   (documentation only):
   ```sql
   UPDATE iris_core.energy_assets t
   SET latitude = s.latitude, longitude = s.longitude,
       geometry = ST_SetSRID(ST_MakePoint(s.longitude, s.latitude), 4326)  -- note: lon, lat order
   FROM staging_position_fix s
   WHERE t.mastr_number = s.mastr_number
     AND t.latitude IS NULL AND t.longitude IS NULL AND t.geometry IS NULL;
   ```
   The `IS NULL` guard makes it safe to run again and stops it from overwriting a known position.
4. The repository update method now guards stored positions. It fills a completely empty position
   only when the incoming latitude, longitude and geometry are all valid. A valid stored coordinate
   pair is never overwritten. Missing geometry is filled only when the incoming valid coordinates
   exactly match the stored ones. Partial positions and conflicting values are left alone and need a
   separate review. Even a valid but outdated stored point stays until a reviewed correction is approved.
5. Compare the affected-row count with the dry-run's `records_changed` before and after. Take a
   backup first. Do not re-import the 13,790 records.

**Not done / out of scope.** No national backfill, no production access, no geocoding, and no
storage-link column in `energy_assets` (the table doesn't have one; adding it is a separate
migration decision). I did not check anything against real export files.
