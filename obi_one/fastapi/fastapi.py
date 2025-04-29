from fastapi import FastAPI
import obi_one as obi


from fastapi.responses import JSONResponse
def activate_fastapi_app(app: FastAPI):
    """
    1. Create endpoints for each OBI Form subclass.
    2. Create an endpoint that returns all available Form endpoints.
    """

    # 1.
    for subclass in obi.Form.__subclasses__():
        create_form_endpoints(subclass, app)

    # 2.
    @app.get("/forms")
    async def get_forms():
        forms = [subclass.__name__.lower() for subclass in obi.Form.__subclasses__()]
        return JSONResponse(content={"forms": forms})

    
from typing import Type, get_type_hints
def create_form_endpoints(model: Type[obi.Form], app: FastAPI):
    """
    Create a FastAPI endpoint for generating grid scans 
    based on an OBI Form model.
    - model is the OBI.Form subclass
    """

    # model_name: model in lowercase (i.e. 'simulationsform')
    model_name = model.__name__.lower()

    # Get return signature of the run method if specified
    return_class = None
    if hasattr(model, "single_coord_class_name") and model.single_coord_class_name != "":        
        cls = getattr(obi, model.single_coord_class_name)
        return_type = get_type_hints(cls.run).get('return')
        return_class = return_type


    # Create the get endpoint
    @app.get(f"/{model_name}", summary=model.name, description=model.description)
    async def grid_scan_endpoint(form: model) -> return_class:

        try:
            grid_scan = obi.GridScan(form=form, output_root=f"../obi_output/fastapi_test/{model_name}/grid_scan", data_handling="GET")
            grid_scan.generate()
        except Exception as e:
            print(e)

        # Still need to consider what exactly to return
        return 


    # Create the post endpoint
    @app.post(f"/{model_name}", summary=model.name, description=model.description)
    async def grid_scan_endpoint(form: model) -> return_class:

        try:
            grid_scan = obi.GridScan(form=form, output_root=f"../obi_output/fastapi_test/{model_name}/grid_scan", data_handling="POST")
            grid_scan.generate()
        except Exception as e:
            print(e)

        # Still need to consider what exactly to return
        return