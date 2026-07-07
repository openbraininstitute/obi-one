from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import user_verified
from app.logger import L
from obi_one.scientific.unions.unions_extracellular_locations import (
    ExtracellularLocationsUnion,
)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.post(
    "/extracellular-locations/global-coordinates",
    summary="Extracellular electrode global coordinates",
    description=(
        "Return the electrode positions of a patterned extracellular array in world (global) "
        "coordinates, i.e. with the array's origin and direction applied."
    ),
)
def extracellular_global_coordinates_endpoint(
    electrode_locations: ExtracellularLocationsUnion,
) -> list[tuple[float, float, float]]:
    L.info("extracellular_global_coordinates_endpoint")
    try:
        return electrode_locations.get_global_electrode_xyz_locations()
    except TypeError as exc:
        # get_global_electrode_xyz_locations expects single values, not parameter-sweep lists.
        raise HTTPException(
            status_code=422,
            detail="All parameters must be single values; parameter-sweep lists are not supported.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
