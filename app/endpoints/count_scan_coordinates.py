import numpy as np
from fastapi import APIRouter, Depends

from app.dependencies.auth import user_verified
from app.errors import internal_error, invalid_config_error
from app.logger import L
from obi_one.core.exception import ConfigValidationError
from obi_one.core.parametric_multi_values import (
    MAX_N_COORDINATES,
)
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.unions_and_references.scan_configs import (
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

    # Counting is wrapped so that a failure here answers with the same error body as every other
    # path. Left bare it escaped as Starlette's plain-text "Internal Server Error", which is not
    # even JSON -- callers that parse the body before inspecting it fail on the parse instead of
    # reporting the error.
    try:
        grid_scan = GridScanGenerationTask(
            form=scan_config,
            output_root="",  # ty:ignore[invalid-argument-type]
            coordinate_directory_option="ZERO_INDEX",
        )

        n_grid_scan_coordinates = np.prod(
            [len(mv.values) for mv in grid_scan.multiple_value_parameters()]
        )
    except ConfigValidationError as e:
        # Same as the generate endpoints: the config parsed but cannot be used.
        L.info("Rejected unrunnable config: %s", e)
        raise invalid_config_error(str(e)) from e
    except Exception as e:
        L.exception("Failed to count grid scan coordinates")
        raise internal_error(str(e)) from e

    if n_grid_scan_coordinates > MAX_N_COORDINATES:
        msg = (
            f"Number of grid scan coordinates {n_grid_scan_coordinates} "
            f"exceeds maximum allowed {MAX_N_COORDINATES}."
        )
        raise invalid_config_error(msg)

    return max(1, n_grid_scan_coordinates)  # Ensure at least 1 coordinate
