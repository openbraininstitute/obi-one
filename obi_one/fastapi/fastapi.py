from fastapi import FastAPI
import obi_one as obi


from fastapi.responses import JSONResponse
def activate_fastapi_app(app: FastAPI):
    """
    1. Create endpoints for each OBI Form subclass.
    2. Create an endpoint that returns all available Form endpoints.
    """

    all_form_endpoints = []

    # 1.
    for subclass in obi.Form.__subclasses__():
        form_endpoints = create_form_endpoints(subclass, app)
        all_form_endpoints.extend(form_endpoints)

    print(f"All form endpoints: {all_form_endpoints}")

    # 2.
    @app.get("/forms")
    async def get_forms():
        # forms = [subclass.__name__.lower() for subclass in obi.Form.__subclasses__()]
        return JSONResponse(content={"forms": all_form_endpoints})

    
from typing import Type, get_type_hints
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

    endpoints = []

    for method in methods:
        for data_handling in data_handlings:

            if data_handling == "POST":
                data_handling_method = "save"
            elif data_handling == "GET":
                data_handling_method = "data"

            # Get return signature of the run method if specified
            return_type = None
            if hasattr(model, "single_coord_class_name") and model.single_coord_class_name != "":
                cls = getattr(obi, model.single_coord_class_name)

                if hasattr(cls, method) and callable(getattr(cls, method)):
                    
                    if hasattr(cls, data_handling_method) and callable(getattr(cls, data_handling_method)):

                        print(cls, method, data_handling_method)

                        return_class = get_type_hints(getattr(cls, data_handling_method)).get('return')
                        return_type = dict[str, return_class]

                        if data_handling == "POST":
                            # Create a post endpoint
                            endpoint = f"/{model_name}" + "_" + method + "_" + data_handling_method
                            endpoints.append(endpoint)
                            @app.post(endpoint, summary=model.name, description=model.description)
                            async def grid_scan_endpoint(form: model):

                                try:
                                    grid_scan = obi.GridScan(form=form, output_root=f"../obi_output/fastapi_test/{model_name}/grid_scan", data_handling=data_handling)
                                    result = getattr(grid_scan, method)()
                                    return result
                                except Exception as e:
                                    print(e)
                                    return JSONResponse(content={"error": "An internal error has occurred."}, status_code=500)

                        elif data_handling == "GET":
                            # Create a get endpoint
                            endpoint = f"/{model_name}" + "_" + method + "_" + data_handling_method
                            endpoints.append(endpoint)
                            @app.get(endpoint, summary=model.name, description=model.description)
                            async def grid_scan_endpoint(form: model):

                                try:
                                    grid_scan = obi.GridScan(form=form, output_root=f"../obi_output/fastapi_test/{model_name}/grid_scan", data_handling=data_handling)
                                    result = getattr(grid_scan, method)()
                                    return result
                                except Exception as e:
                                    print(e)
                                    return JSONResponse(content={"error": "An internal error has occurred."}, status_code=500)

    return endpoints