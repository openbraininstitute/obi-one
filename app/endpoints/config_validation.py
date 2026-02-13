from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ValidationError

from app.dependencies.auth import user_verified
from app.logger import L
from obi_one.scientific.tasks.circuit_extraction import CircuitExtractionScanConfig
from obi_one.scientific.tasks.contribute import (
    ContributeMorphologyScanConfig,
    ContributeSubjectScanConfig,
)
from obi_one.scientific.tasks.generate_simulation_configs import (
    CircuitSimulationScanConfig,
    MEModelSimulationScanConfig,
    MEModelWithSynapsesCircuitSimulationScanConfig,
)
from obi_one.scientific.tasks.ion_channel_modeling import IonChannelFittingScanConfig
from obi_one.scientific.tasks.morphology_metrics import (
    MorphologyMetricsScanConfig,
)
from obi_one.scientific.tasks.schema_example import SchemaExampleScanConfig
from obi_one.scientific.tasks.skeletonization import SkeletonizationScanConfig
from obi_one.scientific.unions.aliases import SimulationsForm

router = APIRouter(
    prefix="/config-validation",
    tags=["config-validation"],
    dependencies=[Depends(user_verified)],
)

CLASS_NAME_MAP: dict[str, type] = {
    "CircuitExtractionScanConfig": CircuitExtractionScanConfig,
    "ContributeMorphologyScanConfig": ContributeMorphologyScanConfig,
    "ContributeSubjectScanConfig": ContributeSubjectScanConfig,
    "CircuitSimulationScanConfig": CircuitSimulationScanConfig,
    "MEModelSimulationScanConfig": MEModelSimulationScanConfig,
    "MEModelWithSynapsesCircuitSimulationScanConfig": MEModelWithSynapsesCircuitSimulationScanConfig,  # noqa: E501
    "IonChannelFittingScanConfig": IonChannelFittingScanConfig,
    "MorphologyMetricsScanConfig": MorphologyMetricsScanConfig,
    "SchemaExampleScanConfig": SchemaExampleScanConfig,
    "SkeletonizationScanConfig": SkeletonizationScanConfig,
    "SimulationsForm": SimulationsForm,
}

ScanConfigClassName = Literal[
    "CircuitExtractionScanConfig",
    "ContributeMorphologyScanConfig",
    "ContributeSubjectScanConfig",
    "CircuitSimulationScanConfig",
    "MEModelSimulationScanConfig",
    "MEModelWithSynapsesCircuitSimulationScanConfig",
    "IonChannelFittingScanConfig",
    "MorphologyMetricsScanConfig",
    "SchemaExampleScanConfig",
    "SkeletonizationScanConfig",
    "SimulationsForm",
]


class ConfigValidationRequest(BaseModel):
    """Request body for config validation."""

    class_name: ScanConfigClassName
    data: dict[str, Any]


class ConfigValidationResponse(BaseModel):
    """Response body for config validation."""

    valid: bool
    message: str


@router.post(
    "/validate",
    summary="Validate scan config data",
    description="Instantiate a scan config class and return validation results.",
)
def validate_config(request: ConfigValidationRequest) -> ConfigValidationResponse:
    """Validate arbitrary data against a scan config class."""
    cls = CLASS_NAME_MAP[request.class_name]
    L.info("Validating data against %s", request.class_name)

    try:
        cls(**request.data)
    except (ValidationError, Exception) as e:
        L.info("Validation failed for %s: %s", request.class_name, e)
        return ConfigValidationResponse(valid=False, message=f"{type(e).__name__}: {e}")

    L.info("Validation succeeded for %s", request.class_name)
    return ConfigValidationResponse(valid=True, message="ok")
