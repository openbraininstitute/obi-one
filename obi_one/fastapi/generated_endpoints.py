from typing import Type
from fastapi.responses import JSONResponse
from obi_one.core.form import Form
from obi_one.core.scan import GridScan
from fastapi import FastAPI
from fastapi import APIRouter

from obi_one.modeling.unions.unions_form import check_implmentations_of_single_coordinate_class_and_methods_and_return_types
    
import re
def create_form_endpoints(model: Type[Form], router: APIRouter):
    """
    Create a FastAPI endpoint for generating grid scans 
    based on an OBI Form model.
    - model is the OBI.Form subclass
    """

    # model_name: model in lowercase with underscores between words and "Forms" removed (i.e. 'morphology_metrics_example')
    model_base_name = model.__name__.removesuffix("Form")
    model_name = '_'.join([word.lower() for word in re.findall(r'[A-Z][^A-Z]*', model_base_name)])

    # methods and data_handling types to iterate over
    processing_methods = ["run", "generate"]
    data_postprocessing_methods = ["save", "data"]

    # List of names of created endpoints
    endpoint_names = []

    # Iterate over methods and data_handling types
    for processing_method in processing_methods:
        for data_postprocessing_method in data_postprocessing_methods:

            # Check which of single coordinate class, method, data_handling_method and return type are implemented
            return_class = check_implmentations_of_single_coordinate_class_and_methods_and_return_types(model, processing_method, data_postprocessing_method)
            if not isinstance(return_class, str):
                if return_class is None:
                    return_type = None
                else:                
                    return_type = dict[str, return_class]

                # Create endpoint names
                endpoint_name = model_name + "_" + processing_method + "_grid" # + "_" + data_postprocessing_method
                endpoint_name_with_slash = "/" + endpoint_name
                endpoint_names.append(endpoint_name)

                # Create POST endpoint (advised that it is standard to use POST even for "GET-Like" requests, when the request body is non-trivial)
                @router.post(endpoint_name_with_slash, summary=model.name, description=model.description)
                async def endpoint(form: model) -> return_type:

                    try:
                        grid_scan = GridScan(form=form, output_root=f"../obi_output/fastapi_test/{model_name}/grid_scan", coordinate_directory_option="ZERO_INDEX")
                        result = grid_scan.execute(processing_method=processing_method, data_postprocessing_method=data_postprocessing_method)
                        return result
                    except Exception as e:
                        print(e)
                        return JSONResponse(content={"error": "An internal error has occurred."}, status_code=500)

    return endpoint_names




prefix = ""
# prefix = "/generated"

router = APIRouter(prefix=prefix, tags=["OBI-ONE - Generated Endpoints"])


all_endpoint_names = []

# # 1. Create endpoints for each OBI Form subclass.
for subclass in Form.__subclasses__():
    form_endpoints = create_form_endpoints(subclass, router)
    all_endpoint_names.extend(form_endpoints)


# 2. Create an endpoint that returns all available Form endpoints.
@router.get("/forms")
async def get_forms():
    return JSONResponse(content={"forms": all_endpoint_names})