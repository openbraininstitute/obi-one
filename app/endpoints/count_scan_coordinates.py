import numpy as np
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import user_verified
from app.logger import L
from obi_one.core.parametric_multi_values import (
    MAX_N_COORDINATES,
)
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.unions.unions_scan_configs import (
    ScanConfigsUnion,
)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.post(
    "/scan_config/grid-scan-coordinate-count",
    summary="Grid scan coordinate count",
    description=("This calculates the number of coordinates for a grid scan configuration."),
)
def grid_scan_parameters_count_endpoint(
    scan_config: ScanConfigsUnion,
) -> int:
    L.info("grid_scan_parameters_endpoint")
    grid_scan = GridScanGenerationTask(
        form=scan_config,
        output_root="",
        coordinate_directory_option="ZERO_INDEX",
    )

    n_grid_scan_coordinates = np.prod(
        [len(mv.values) for mv in grid_scan.multiple_value_parameters()]
    )
    if n_grid_scan_coordinates > MAX_N_COORDINATES:
        raise HTTPException(
            status_code=400,
            detail=f"Number of grid scan coordinates {n_grid_scan_coordinates} exceeds\
                maximum allowed {MAX_N_COORDINATES}.",
        )

    n_grid_scan_coordinates = max(1, n_grid_scan_coordinates)  # Ensure at least 1 coordinate

    return n_grid_scan_coordinates
