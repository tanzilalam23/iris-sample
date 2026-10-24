from pathlib import Path
import json
import logging

from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from app.database.models.energy_asset import EnergyAsset
from app.mastr_quality.coordinates import parse_coordinate


logger = logging.getLogger(__name__)


class MaStRParser:
    """
    Parses MaStR JSON into EnergyAsset entities.
    """

    def parse(
        self,
        file_path: str | Path,
    ) -> list[EnergyAsset]:

        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(file_path)

        logger.info("Reading MaStR dataset...")

        with file_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            records = json.load(file)

        assets: list[EnergyAsset] = []

        skipped = 0

        for record in records:

            asset = self._build_entity(record)

            if asset is None:
                skipped += 1
                continue

            assets.append(asset)

        logger.info(
            "Parsed %s energy assets (%s skipped).",
            len(assets),
            skipped,
        )

        return assets

    def _build_entity(
        self,
        record: dict,
    ) -> EnergyAsset | None:

        mastr_number = record.get("mastr_number")

        if not mastr_number:
            return None

        operator = record.get("operator") or {}

        location = record.get("location") or {}

        energy = record.get("energy") or {}

        status = record.get("status") or {}

        # Validate coordinates before storing or creating geometry.
        latitude_result = parse_coordinate(location.get("latitude"), "lat")
        longitude_result = parse_coordinate(location.get("longitude"), "lon")
        latitude = latitude_result.value
        longitude = longitude_result.value

        geometry = None

        if (
            latitude is not None
            and longitude is not None
        ):
            geometry = from_shape(
                Point(
                    longitude,
                    latitude,
                ),
                srid=4326,
            )

        return EnergyAsset(
            id=record.get("id"),
            source=record.get(
                "source",
                "mastr",
            ),

            mastr_number=mastr_number,

            name=record.get(
                "name",
                "",
            ),

            operator_name=operator.get(
                "name"
            ),

            operator_mastr_number=operator.get(
                "mastr_number"
            ),

            location_id=location.get(
                "location_id"
            ),

            city=location.get(
                "city"
            ),

            postal_code=location.get(
                "postal_code"
            ),

            energy_type=energy.get(
                "type"
            ),

            gross_power_kw=energy.get(
                "gross_power_kw"
            ),

            net_power_kw=energy.get(
                "net_power_kw"
            ),

            status=status.get(
                "name"
            ),

            latitude=latitude,

            longitude=longitude,

            geometry=geometry,
        )