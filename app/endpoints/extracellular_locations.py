from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import user_verified
from app.logger import L
from obi_one.scientific.library.extracellular_locations import (
    extracellular_locations_block_dictionary_summary,
    extracellular_locations_block_summary,
)
from obi_one.scientific.unions.unions_extracellular_locations import (
    ExtracellularLocationsUnion,
)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.post(
    "/extracellular-locations/block_summary",
    summary="Extracellular-locations block summary",
    description=(
        "Return a patterned extracellular array's electrode positions in world (global) "
        "coordinates (origin and direction applied) under `locations`, together with the array's "
        "properties (`type`, origin/direction and the pattern-specific parameters)."
    ),
)
def extracellular_locations_block_summary_endpoint(
    electrode_locations: ExtracellularLocationsUnion,
) -> dict[str, Any]:
    L.info("extracellular_locations_block_summary_endpoint")
    try:
        return extracellular_locations_block_summary(electrode_locations)
    except TypeError as exc:
        # get_global_electrode_xyz_locations expects single values, not parameter-sweep lists.
        raise HTTPException(
            status_code=422,
            detail="All parameters must be single values; parameter-sweep lists are not supported.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/extracellular-locations/block_dictionary_summary",
    summary="Extracellular-locations block-dictionary summary",
    description=(
        "Return, for each named patterned extracellular array in the input dictionary, its "
        "electrode positions in world (global) coordinates under `locations` together with the "
        "array's properties, keyed by the same block names."
    ),
)
def extracellular_locations_block_dictionary_summary_endpoint(
    electrode_locations: dict[str, ExtracellularLocationsUnion],
) -> dict[str, dict[str, Any]]:
    L.info("extracellular_locations_block_dictionary_summary_endpoint")
    try:
        return extracellular_locations_block_dictionary_summary(electrode_locations)
    except TypeError as exc:
        # get_global_electrode_xyz_locations expects single values, not parameter-sweep lists.
        raise HTTPException(
            status_code=422,
            detail="All parameters must be single values; parameter-sweep lists are not supported.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
