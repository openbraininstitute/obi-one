from typing import Annotated

import entitysdk.client
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from obi_one.core.exception import ProtocolNotFoundError
from obi_one.scientific.library.ephys_extraction import (
    CALCULATED_FEATURES,
    STIMULI_TYPES,
    AmplitudeInput,
    ElectrophysiologyMetricsOutput,
    get_electrophysiology_metrics,
)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.get(
    "/electrophysiologyrecording-metrics/{trace_id}",
    summary="Electrophysiology recording metrics",
    description="This calculates electrophysiology traces metrics for a particular recording",
)
def electrophysiologyrecording_metrics_endpoint(
    trace_id: str,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    requested_metrics: Annotated[CALCULATED_FEATURES | None, Query()] = None,
    amplitude: Annotated[AmplitudeInput, Depends()] = None,
    protocols: Annotated[STIMULI_TYPES | None, Query()] = None,
) -> ElectrophysiologyMetricsOutput:
    try:
        ephys_metrics = get_electrophysiology_metrics(
            trace_id=trace_id,
            entity_client=db_client,
            calculated_feature=requested_metrics,
            amplitude=amplitude,
            stimuli_types=protocols,
        )
    except ProtocolNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e!s}") from e
    return ephys_metrics
