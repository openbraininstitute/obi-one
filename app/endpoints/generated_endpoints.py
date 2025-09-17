import re
import tempfile
from typing import Annotated, get_type_hints

import entitysdk.client
import entitysdk.common
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.entitysdk import get_client
from obi_one.core.form import Form
from obi_one.core.scan import GridScan
from obi_one.scientific.contribute.contribute import (
    ContributeMorphology,
    ContributeMorphologyForm,
    ContributeSubject,
    ContributeSubjectForm,    
)
from obi_one.scientific.morphology_metrics.morphology_metrics import (
    MorphologyMetrics,
    MorphologyMetricsForm,
)
from obi_one.scientific.simulation.simulations import (
    Simulation,
    SimulationsForm,
)

def check_implementations_of_single_coordinate_class(
    single_coordinate_cls: type[Form], processing_method: str, data_postprocessing_method: str
) -> str | type | None:
    return_class = None
    if not (
        hasattr(single_coordinate_cls, processing_method)
        and callable(getattr(single_coordinate_cls, processing_method))
    ):
        return f"{processing_method} is not a method of {single_coordinate_cls.__name__}"
    if not data_postprocessing_method:
        return None
    if not (
        hasattr(single_coordinate_cls, data_postprocessing_method)
        and callable(getattr(single_coordinate_cls, data_postprocessing_method))
    ):
        return f"{data_postprocessing_method} is not a method of {single_coordinate_cls.__name__}"
    return_class = get_type_hints(getattr(single_coordinate_cls, data_postprocessing_method)).get("return")

    return return_class

def create_endpoint_for_form(
    model: type[Form],
    single_coordinate_cls: type[Form],
    router: APIRouter,
    processing_method: str,
    data_postprocessing_method: str,
) -> None:
    model_base_name = model.__name__.removesuffix("Form")
    model_name = "-".join([word.lower() for word in re.findall(r"[A-Z][^A-Z]*", model_base_name)])   
    return_class = check_implementations_of_single_coordinate_class(
        single_coordinate_cls, processing_method, data_postprocessing_method
    )
    if isinstance(return_class, str):     
        return
    endpoint_name_with_slash = "/" + model_name + "-" + processing_method + "-grid"
    if data_postprocessing_method:
        endpoint_name_with_slash = endpoint_name_with_slash + "-" + data_postprocessing_method  

    @router.post(endpoint_name_with_slash, summary=model.name, description=model.description)
    def endpoint(
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        form: model,
    ) -> str:     
        campaign = None
        try:
            with tempfile.TemporaryDirectory() as tdir:
                grid_scan = GridScan(
                    form=form,
                    output_root=tdir,
                    coordinate_directory_option="ZERO_INDEX",
                )
                campaign = grid_scan.execute(
                    processing_method=processing_method,
                    data_postprocessing_method=data_postprocessing_method,
                    db_client=db_client,
                )
        except Exception as e:
            error_msg = str(e)
            if len(e.args) == 1:
                error_msg = str(e.args[0])
            elif len(e.args) > 1:
                error_msg = str(e.args)           
            raise HTTPException(status_code=500, detail=error_msg) from e
        else:
         
            if campaign is not None:
                return str(campaign.id)        
            return ""

def activate_generated_endpoints(router: APIRouter) -> APIRouter:
    for form, processing_method, data_postprocessing_method, single_coordinate_cls in [
        (SimulationsForm, "generate", "", Simulation),
        (SimulationsForm, "generate", "save", Simulation),
        (MorphologyMetricsForm, "run", "", MorphologyMetrics),
        (ContributeMorphologyForm, "generate", "", ContributeMorphology),
        (ContributeSubjectForm, "generate", "", ContributeSubject),
    ]:
 
        create_endpoint_for_form(
            form,
            single_coordinate_cls,
            router,
            processing_method=processing_method,
            data_postprocessing_method=data_postprocessing_method,
        )
    return router
