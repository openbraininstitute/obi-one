import re
from typing import Annotated

import entitysdk.client
import entitysdk.common
from fastapi import APIRouter, Depends

from app.config import settings
from app.dependencies.entitysdk import get_client
from app.logger import L
from obi_one.core.form import Form
from obi_one.core.scan import GridScan
from obi_one.scientific.unions.unions_form import (
    check_implmentations_of_single_coordinate_class_and_methods_and_return_types,
)


def create_endpoints_for_form(model: type[Form], router: APIRouter):
    """Create a FastAPI endpoint for generating grid scans
    based on an OBI Form model.
    - model is the OBI.Form subclass
    """
    # model_name: model in lowercase with underscores between words and "Forms" removed (i.e. 'morphology_metrics_example')
    model_base_name = model.__name__.removesuffix("Form")
    model_name = "-".join([word.lower() for word in re.findall(r"[A-Z][^A-Z]*", model_base_name)])

    # methods and data_handling types to iterate over
    processing_methods = ["run", "generate"]
    data_postprocessing_methods = [""]  # , "save", "data"

    # Iterate over methods and data_handling types
    for processing_method in processing_methods:
        for data_postprocessing_method in data_postprocessing_methods:
            # Check which of single coordinate class, method, data_handling_method and return type are implemented
            return_class = (
                check_implmentations_of_single_coordinate_class_and_methods_and_return_types(
                    model, processing_method, data_postprocessing_method
                )
            )

            if not isinstance(return_class, str):
                if return_class is None:
                    return_type = None
                else:
                    return_type = dict[str, return_class]

                # Create endpoint name
                endpoint_name_with_slash = "/" + model_name + "-" + processing_method + "-grid"
                if data_postprocessing_method != "":
                    endpoint_name_with_slash = (
                        endpoint_name_with_slash + "-" + data_postprocessing_method
                    )

                # Create POST endpoint (advised that it is standard to use POST even for "GET-Like" requests, when the request body is non-trivial)
                @router.post(
                    endpoint_name_with_slash, summary=model.name, description=model.description
                )
                def endpoint(
                    entity_client: Annotated[entitysdk.client.Client, Depends(get_client)],
                    form: model,
                ) -> return_type:
                    L.info("generate_grid_scan")
                    # L.debug("user_context: %s", user_context.model_dump())

                    try:
                        grid_scan = GridScan(
                            form=form,
                            output_root=settings.OUTPUT_DIR
                            / "fastapi_test"
                            / model_name
                            / "grid_scan",
                            coordinate_directory_option="ZERO_INDEX",
                        )
                        result = grid_scan.execute(
                            processing_method=processing_method,
                            data_postprocessing_method=data_postprocessing_method,
                        )
                        return result
                    except Exception:  # noqa: BLE001
                        L.exception("Generic exception")


def activate_generated_endpoints(router: APIRouter) -> APIRouter:
    # # 1. Create endpoints for each OBI Form subclass.
    for form in Form.__subclasses__():
        create_endpoints_for_form(form, router)

    return router
