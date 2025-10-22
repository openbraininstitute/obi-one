import re
import tempfile
from typing import Annotated

import entitysdk.client
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.logger import L
from obi_one import run_tasks_for_generated_scan
from obi_one.core.scan_config import ScanConfig
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.tasks.contribute import (
    ContributeMorphologyScanConfig,
    ContributeSubjectScanConfig,
)
from obi_one.scientific.tasks.generate_simulation_configs import (
    CircuitSimulationScanConfig,
    MEModelSimulationScanConfig,
)
from obi_one.scientific.tasks.ion_channel_modeling import IonChannelFittingScanConfig
from obi_one.scientific.tasks.morphology_metrics import (
    MorphologyMetricsScanConfig,
)
from obi_one.scientific.unions.aliases import SimulationsForm

router = APIRouter(prefix="/generated", tags=["generated"], dependencies=[Depends(user_verified)])


def create_endpoint_for_scan_config(
    model: type[ScanConfig],
    processing_method: str,
    data_postprocessing_method: str,
) -> None:
    """Create a FastAPI endpoint for generating grid scans based on an OBI ScanConfig model."""
    # model_name: model in lowercase with underscores between words and "Forms" removed (i.e.
    # 'morphology_metrics_example')
    model_base_name = model.__name__.removesuffix("Form")
    pattern = r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[0-9]+"
    model_name = "-".join(word.lower() for word in re.findall(pattern, model_base_name))

    # Create endpoint name
    endpoint_name_with_slash = "/" + model_name + "-" + processing_method + "-grid"
    if data_postprocessing_method:
        endpoint_name_with_slash = endpoint_name_with_slash + "-" + data_postprocessing_method

    @router.post(endpoint_name_with_slash, summary=model.name, description=model.description)
    def endpoint(
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        form: model,
    ) -> str:
        L.info("generate_grid_scan")
        L.info(db_client)

        campaign = None
        try:
            with tempfile.TemporaryDirectory() as tdir:
                grid_scan = GridScanGenerationTask(
                    form=form,
                    # TODO: output_root=settings.OUTPUT_DIR / "fastapi_test" / model_name
                    #        / "grid_scan", => ERA001 Found commented-out code
                    output_root=tdir,
                    coordinate_directory_option="ZERO_INDEX",
                )
                grid_scan.execute(db_client=db_client)
                campaign = grid_scan.form.campaign
                run_tasks_for_generated_scan(grid_scan, db_client=db_client, entity_cache=True)

        except Exception as e:
            error_msg = str(e)

            if len(e.args) == 1:
                error_msg = str(e.args[0])
            elif len(e.args) > 1:
                error_msg = str(e.args)

            L.error(error_msg)

            raise HTTPException(status_code=500, detail=error_msg) from e

        else:
            L.info("Grid scan generated successfully")
            if campaign is not None:
                return str(campaign.id)

            L.info("No campaign generated")
            return ""


def activate_scan_config_endpoints() -> None:
    # Create endpoints for each OBI ScanConfig subclass.
    for form, processing_method, data_postprocessing_method in [
        (CircuitSimulationScanConfig, "generate", ""),
        (MEModelSimulationScanConfig, "generate", ""),
        (SimulationsForm, "generate", "save"),
        (MorphologyMetricsScanConfig, "run", ""),
        (ContributeMorphologyScanConfig, "generate", ""),
        (ContributeSubjectScanConfig, "generate", ""),
        (IonChannelFittingScanConfig, "generate", ""),
    ]:
        create_endpoint_for_scan_config(
            form,
            processing_method=processing_method,
            data_postprocessing_method=data_postprocessing_method,
        )

    return router
