import json
import re
from datetime import datetime, timezone

from app.config.paths import DataPaths
from app.mastr_quality.coordinates import parse_coordinate


class MaStRTransformer:
    """
    Transforms merged MaStR records into the
    clean internal power-generation schema.

    Input:
        <run>/raw/mastr/merged.json

    Output:
        <run>/processed/mastr/power_generation.json

    DataPaths controls the workspace so each pipeline
    execution remains isolated.
    """

    def __init__(
        self,
        country_code: str = "DE",
        paths: DataPaths | None = None,
    ):

        self.country_code = (
            country_code.upper()
        )

        self.paths = paths or DataPaths()

        # -------------------------------------------------
        # Run-specific paths
        # -------------------------------------------------

        self.input_file = (
            self.paths.mastr_raw
            / "merged.json"
        )

        self.output_dir = (
            self.paths.mastr_processed
        )

        self.output_file = (
            self.output_dir
            / "power_generation.json"
        )

    # =====================================================
    # TRANSFORM
    # =====================================================

    def transform(self):
        """
        Transform merged MaStR records into
        the clean internal schema.
        """

        if not self.input_file.exists():

            raise FileNotFoundError(
                f"MaStR input file not found: "
                f"{self.input_file}"
            )

        with self.input_file.open(
            "r",
            encoding="utf-8",
        ) as file:

            records = json.load(file)

        if not isinstance(
            records,
            list,
        ):

            raise ValueError(
                "Expected MaStR merged data "
                "to contain a list of records."
            )

        transformed = [
            self.transform_record(
                record
            )
            for record in records
        ]

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.output_file.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                transformed,
                file,
                ensure_ascii=False,
                indent=2,
            )

        print("--------------------------------")
        print(
            f"Input Records  : "
            f"{len(records)}"
        )

        print(
            f"Output Records : "
            f"{len(transformed)}"
        )

        print(
            f"Saved          : "
            f"{self.output_file}"
        )

        return transformed

    # =====================================================
    # TRANSFORM RECORD
    # =====================================================

    def transform_record(
        self,
        record: dict,
    ):

        latitude = parse_coordinate(record.get("Breitengrad"), "lat")
        longitude = parse_coordinate(record.get("Laengengrad"), "lon")

        return {
            "source": "mastr",

            "country_code": (
                self.country_code
            ),

            "id": record.get(
                "Id"
            ),

            "mastr_number": record.get(
                "MaStRNummer"
            ),

            "name": record.get(
                "EinheitName"
            ),

            "operator": {
                "id": record.get(
                    "AnlagenbetreiberId"
                ),

                "mastr_number": record.get(
                    "AnlagenbetreiberMaStRNummer"
                ),

                "name": record.get(
                    "AnlagenbetreiberName"
                ),
            },

            "location": {
                "location_id": record.get(
                    "LokationId"
                ),

                "city": record.get(
                    "Ort"
                ),

                "postal_code": record.get(
                    "Plz"
                ),

                "parcel": record.get(
                    "Flurstueck"
                ),

                "latitude": latitude.value,

                "longitude": longitude.value,
            },

            "energy": {
                "type": record.get(
                    "EnergietraegerName"
                ),

                "gross_power_kw": record.get(
                    "Bruttoleistung"
                ),

                "net_power_kw": record.get(
                    "Nettonennleistung"
                ),

                "solar_modules": record.get(
                    "AnzahlSolarModule"
                ),
            },

            "status": {
                "id": record.get(
                    "BetriebsStatusId"
                ),

                "name": record.get(
                    "BetriebsStatusName"
                ),
            },

            "dates": {
                "registered": self.parse_date(
                    record.get(
                        "EinheitMeldeDatum"
                    )
                ),

                "commissioned": self.parse_date(
                    record.get(
                        "InbetriebnahmeDatum"
                    )
                ),

                "updated": self.parse_date(
                    record.get(
                        "DatumLetzteAktualisierung"
                    )
                ),
            },

            "flags": {
                "is_anonymized": record.get(
                    "IsAnonymisiert"
                ),

                "is_pilot_wind": record.get(
                    "IsPilotwindanlage"
                ),
            },

            "type": record.get(
                "Typ"
            ),

            "person_type_id": record.get(
                "PersonenArtId"
            ),
        }

    # =====================================================
    # DATE PARSER
    # =====================================================

    def parse_date(
        self,
        value,
    ):
        """
        Convert a MaStR .NET-style date:

            /Date(1785481538132)/

        into:

            2026-07-30T13:45:38+00:00
        """

        if not value:

            return None

        match = re.search(
            r"\d+",
            str(value),
        )

        if not match:

            return None

        timestamp = (
            int(match.group())
            / 1000
        )

        return datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        ).isoformat()