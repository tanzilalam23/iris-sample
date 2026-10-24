from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session
from geoalchemy2 import Geography

from app.database.models.energy_asset import EnergyAsset
from app.mastr_quality.coordinates import parse_coordinate
from app.database.repositories.base_repository import BaseRepository


class EnergyAssetRepository(BaseRepository[EnergyAsset]):
    """
    Repository for EnergyAsset persistence and domain-specific queries.
    """

    def __init__(self, session: Session):
        super().__init__(session, EnergyAsset)

    # ======================================================
    # MaStR Lookup
    # ======================================================

    def find_by_mastr_number(
        self,
        mastr_number: str,
    ) -> EnergyAsset | None:

        statement = (
            select(EnergyAsset)
            .where(
                EnergyAsset.mastr_number == mastr_number
            )
        )

        return self.session.scalar(statement)

    def exists_by_mastr_number(
        self,
        mastr_number: str,
    ) -> bool:

        statement = (
            select(func.count())
            .select_from(EnergyAsset)
            .where(
                EnergyAsset.mastr_number == mastr_number
            )
        )

        return (
            self.session.scalar(statement) or 0
        ) > 0

    # ======================================================
    # Search
    # ======================================================

    def find_by_operator(
        self,
        operator_name: str,
    ) -> list[EnergyAsset]:

        statement = (
            select(EnergyAsset)
            .where(
                EnergyAsset.operator_name == operator_name
            )
            .order_by(EnergyAsset.name)
        )

        return list(
            self.session.scalars(statement)
        )

    def find_by_city(
        self,
        city: str,
    ) -> list[EnergyAsset]:

        statement = (
            select(EnergyAsset)
            .where(
                EnergyAsset.city == city
            )
            .order_by(EnergyAsset.name)
        )

        return list(
            self.session.scalars(statement)
        )

    def find_by_energy_type(
        self,
        energy_type: str,
    ) -> list[EnergyAsset]:

        statement = (
            select(EnergyAsset)
            .where(
                EnergyAsset.energy_type == energy_type
            )
            .order_by(EnergyAsset.name)
        )

        return list(
            self.session.scalars(statement)
        )

    def find_by_status(
        self,
        status: str,
    ) -> list[EnergyAsset]:

        statement = (
            select(EnergyAsset)
            .where(
                EnergyAsset.status == status
            )
            .order_by(EnergyAsset.name)
        )

        return list(
            self.session.scalars(statement)
        )

    # ======================================================
    # Renewable Energy Spatial Intelligence
    # ======================================================

    def find_energy_capacity(
        self,
        latitude: float,
        longitude: float,
    ) -> dict:
        """
        Returns renewable energy assets within 10 km
        of the given location and aggregates their capacity.
        """

        point = func.ST_SetSRID(
            func.ST_Point(
                longitude,
                latitude,
            ),
            4326,
        )

        distance = func.ST_Distance(
            func.cast(
                EnergyAsset.geometry,
                Geography,
            ),
            func.cast(
                point,
                Geography,
            ),
        )

        statement = (
            select(EnergyAsset)
            .where(
                EnergyAsset.geometry.is_not(None),
                distance <= 10_000,
            )
        )

        assets = list(
            self.session.scalars(statement)
        )

        solar_kw = 0.0
        wind_kw = 0.0

        for asset in assets:

            power = asset.gross_power_kw or 0

            energy_type = (
                asset.energy_type or ""
            ).lower()

            if "solar" in energy_type:
                solar_kw += power

            elif "wind" in energy_type:
                wind_kw += power

        return {
            "asset_count": len(assets),
            "solar_kw": round(
                solar_kw,
                2,
            ),
            "wind_kw": round(
                wind_kw,
                2,
            ),
        }

    # ======================================================
    # Update Existing MaStR Asset
    # ======================================================

    def update_from_entity(
        self,
        existing: EnergyAsset,
        incoming: EnergyAsset,
    ) -> EnergyAsset:
        """
        Updates an existing EnergyAsset using
        the latest MaStR data.

        The mastr_number remains unchanged because
        it is the unique business identifier.
        """

        existing.source = incoming.source
        existing.name = incoming.name

        existing.location_id = (
            incoming.location_id
        )

        existing.operator_name = (
            incoming.operator_name
        )

        existing.operator_mastr_number = (
            incoming.operator_mastr_number
        )

        existing.city = incoming.city
        existing.postal_code = incoming.postal_code

        existing.energy_type = (
            incoming.energy_type
        )

        existing.gross_power_kw = (
            incoming.gross_power_kw
        )

        existing.net_power_kw = (
            incoming.net_power_kw
        )

        existing.status = incoming.status

        # Treat coordinates and geometry as one position.
        # Never automatically overwrite a stored or partial position.
        existing_lat = parse_coordinate(existing.latitude, "lat")
        existing_lon = parse_coordinate(existing.longitude, "lon")
        incoming_lat = parse_coordinate(incoming.latitude, "lat")
        incoming_lon = parse_coordinate(incoming.longitude, "lon")

        existing_pair_is_valid = (
            existing_lat.reason is None and existing_lon.reason is None
        )
        existing_has_any_position = (
            existing.latitude is not None
            or existing.longitude is not None
            or existing.geometry is not None
        )
        incoming_position_is_valid = (
            incoming_lat.reason is None
            and incoming_lon.reason is None
            and incoming.geometry is not None
        )

        if existing_pair_is_valid:
            # Fill missing geometry only if the coordinates match.
            if (
                existing.geometry is None
                and incoming_position_is_valid
                and incoming_lat.value == existing_lat.value
                and incoming_lon.value == existing_lon.value
            ):
                existing.geometry = incoming.geometry
        elif not existing_has_any_position and incoming_position_is_valid:
            # Only fill a completely empty position with a valid complete one.
            existing.latitude = incoming_lat.value
            existing.longitude = incoming_lon.value
            existing.geometry = incoming.geometry

        return existing