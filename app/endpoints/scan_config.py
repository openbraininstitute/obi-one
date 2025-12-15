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
    MEModelWithSynapsesCircuitSimulationScanConfig,
)
from obi_one.scientific.tasks.ion_channel_modeling import IonChannelFittingScanConfig
from obi_one.scientific.tasks.morphology_metrics import (
    MorphologyMetricsScanConfig,
)
from obi_one.scientific.unions.aliases import SimulationsForm

router = APIRouter(prefix="/generated", tags=["generated"], dependencies=[Depends(user_verified)])


def create_endpoint_for_scan_config(
    model: type[ScanConfig],
    *,
    processing_method: str,
    data_postprocessing_method: str,
    execute_single_config_task: bool = True,
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
        grid_scan = None
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
                if execute_single_config_task:
                    run_tasks_for_generated_scan(grid_scan, db_client=db_client, entity_cache=True)

                

        except Exception as e:
            error_msg = str(e)

            if len(e.args) == 1:
                error_msg = str(e.args[0])
            elif len(e.args) > 1:
                error_msg = str(e.args)

            L.info("Grid scan generation failed")
            L.error(error_msg)

            if isinstance(grid_scan.form, (CircuitSimulationScanConfig, 
                                 MEModelSimulationScanConfig, 
                                 MEModelWithSynapsesCircuitSimulationScanConfig, 
                                 SimulationsForm)):
                if (grid_scan is not None) and (grid_scan.form.campaign is not None):
                    L.info(
                        f"Grid scan generation failed, but campaign {grid_scan.form.campaign.id} \
                            of type {type(grid_scan.form.campaign)} was created. Let's delete it and associated entities / assets."
                    )   
                    L.info("\n\n\nStarting cleanup of created entities...\n\n\n")

                    # DELETE THE CAMPAIGN (SAME AS GENERATION ACTIIVTY - USED)
                    # db_client.delete_entity(entity_id=grid_scan.form.campaign.id, entity_type=type(grid_scan.form.campaign))

                    campaign_entity = db_client.get_entity(entity_id=grid_scan.form.campaign.id, entity_type=type(grid_scan.form.campaign))

                    L.info(campaign_entity.assets)

                    for idx, asset in enumerate(campaign_entity.assets):
                        L.info(f"Deleting asset {idx}.")
                        
                        db_client.delete_asset(
                            entity_id=grid_scan.form.campaign.id, 
                            entity_type=type(grid_scan.form.campaign), 
                            asset_id=asset.id)
                        
                        L.info(f"Deleted asset {idx}.")

                    # db_client.delete_entity(entity_id=grid_scan.form.campaign.id, entity_type=type(grid_scan.form.campaign))

                    # db_client.delete_entity(entity_id=grid_scan.form.campaign.id, 
                    #                         entity_type=entitysdk.models.SimulationCampaign)

                    if grid_scan.form.generation_activity is not None:

                        # L.info(grid_scan.form.generation_activity.used)
                        # L.info(grid_scan.form.generation_activity.generated)

                        # DELETE EACH SIMULATION
                        for simulation in grid_scan.form.generation_activity.generated:
                            
                            simulation = db_client.get_entity(entity_id=simulation.id, entity_type=entitysdk.models.Simulation)

                            for idx, asset in enumerate(simulation.assets):
                                L.info(f"Deleting asset {idx}.")
                                
                                db_client.delete_asset(
                                    entity_id=simulation.id, 
                                    entity_type=entitysdk.models.Simulation, 
                                    asset_id=asset.id,
                                    hard=True,
                                    admin=True)
                                
                            simulation = db_client.get_entity(entity_id=simulation.id, entity_type=entitysdk.models.Simulation)
                            L.info(simulation.assets)

                            L.info(f"Deleting simulation {simulation.id} of type {type(simulation)}")
                            db_client.delete_entity(entity_id=simulation.id, entity_type=entitysdk.models.Simulation)

                        
                        # # DELETE THE GENERATION ACTIVITY
                        # db_client.delete_entity(entity_id=grid_scan.form.campaign.id, entity_type=type(grid_scan.form.generation_activity))

                raise HTTPException(status_code=500, detail=error_msg) from e

        else:
            L.info("Grid scan generated successfully")
            if campaign is not None:
                return str(campaign.id)

            L.info("No campaign generated")
            return ""


def activate_scan_config_endpoints() -> None:
    # Create endpoints for each OBI ScanConfig subclass.
    for form, processing_method, data_postprocessing_method, execute_single_config_task in [
        (CircuitSimulationScanConfig, "generate", "", True),
        (MEModelSimulationScanConfig, "generate", "", True),
        (MEModelWithSynapsesCircuitSimulationScanConfig, "generate", "", True),
        (SimulationsForm, "generate", "save", True),
        (MorphologyMetricsScanConfig, "run", "", True),
        (ContributeMorphologyScanConfig, "generate", "", True),
        (ContributeSubjectScanConfig, "generate", "", True),
        (IonChannelFittingScanConfig, "generate", "", False),
    ]:
        create_endpoint_for_scan_config(
            form,
            processing_method=processing_method,
            data_postprocessing_method=data_postprocessing_method,
            execute_single_config_task=execute_single_config_task,
        )

    return router
