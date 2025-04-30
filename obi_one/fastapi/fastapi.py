from fastapi import FastAPI
import obi_one as obi
from typing import Type

from fastapi.responses import JSONResponse
def activate_fastapi_app(app: FastAPI):
    """
    Create endpoints for each OBI Form subclass 
    and endpoint that lists Form endpoints.
    """

    all_endpoint_names = []

    # 1. Create endpoints for each OBI Form subclass.
    for subclass in obi.Form.__subclasses__():
        form_endpoints = create_form_endpoints(subclass, app)
        all_endpoint_names.extend(form_endpoints)

    print(f"All endpoint names: {all_endpoint_names}")

    # 2. Create an endpoint that returns all available Form endpoints.
    @app.get("/forms")
    async def get_forms():
        return JSONResponse(content={"forms": all_endpoint_names})


from typing import get_type_hints
def check_implmentations_of_single_coordinate_class_methods_and_return_types(model: Type[obi.Form], method: str, data_handling_method: str):
    """
    Method to return the class of the return type of a method of the single coordinate class.
    Returns None if return type not specified
    Returns message strings if the method or data_handling_method are not implementd
    """

    return_class = None

    # Check that the single_coord_class_name is set
    if model.single_coord_class_name == "":
        return f"single_coord_class_name is not set in the form: {model.__name__}"
    else:
        single_coordinate_cls = getattr(obi, model.single_coord_class_name)

        # Check that the method is a method of the single coordinate class
        if not (hasattr(single_coordinate_cls, method) and callable(getattr(single_coordinate_cls, method))):
            return f"{method} is not a method of {single_coordinate_cls.__name__}"
        else:

            # Check that the data_handling_method is a method of the single coordinate class
            if not (hasattr(single_coordinate_cls, data_handling_method) and callable(getattr(single_coordinate_cls, data_handling_method))):
                return f"{data_handling_method} is not a method of {single_coordinate_cls.__name__}"
            else:
                return_class = get_type_hints(getattr(single_coordinate_cls, data_handling_method)).get('return')

    return return_class


    

def create_form_endpoints(model: Type[obi.Form], app: FastAPI):
    """
    Create a FastAPI endpoint for generating grid scans 
    based on an OBI Form model.
    - model is the OBI.Form subclass
    """

    # model_name: model in lowercase (i.e. 'simulationsform')
    model_name = model.__name__.lower()

    methods = ["run", "generate"]
    data_handlings = ["POST", "GET"]

    endpoint_names = []

    for method in methods:
        for data_handling in data_handlings:

            if data_handling == "POST":
                data_handling_method = "save"
            elif data_handling == "GET":
                data_handling_method = "data"

            # Check which of single coordinate class, method, data_handling_method and return type are implemented
            return_class = check_implmentations_of_single_coordinate_class_methods_and_return_types(model, method, data_handling_method)
            if not isinstance(return_class, str):
                if return_class is None:
                    return_type = None
                else:                
                    return_type = dict[str, return_class]


                endpoint_name = model_name + "_" + method + "_" + data_handling_method
                endpoint_name_with_slash = "/" + endpoint_name

                if data_handling == "POST":
                    # Create a post endpoint
                    
                    endpoint_names.append(endpoint_name)
                    @app.post(endpoint_name_with_slash)
                    async def grid_scan_endpoint(form: model):

                        try:
                            grid_scan = obi.GridScan(form=form, output_root=f"../obi_output/fastapi_test/{model_name}/grid_scan", data_handling=data_handling)
                            result = getattr(grid_scan, method)()
                            return {}
                        except Exception as e:
                            print(e)
                            return JSONResponse(content={"error": "An internal error has occurred."}, status_code=500)

                elif data_handling == "GET":
                    # Create a get endpoint

                    endpoint_names.append(endpoint_name)
                    @app.get(endpoint_name_with_slash, summary=model.name, description=model.description)
                    async def grid_scan_endpoint(form: model) -> return_type:

                        try:
                            grid_scan = obi.GridScan(form=form, output_root=f"../obi_output/fastapi_test/{model_name}/grid_scan", data_handling=data_handling)
                            result = getattr(grid_scan, method)()
                            return result
                        except Exception as e:
                            print(e)
                            return JSONResponse(content={"error": "An internal error has occurred."}, status_code=500)

    return endpoint_names