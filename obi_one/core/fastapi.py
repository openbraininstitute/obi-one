from fastapi import FastAPI, HTTPException
from typing import Type, Dict, Any, List
import obi_one as obi
from fastapi.responses import JSONResponse


def activate_fastapi_app(app: FastAPI):

    # For each obi.Form subclass, create a FastAPI route for generating grid scans.
    for subclass in obi.Form.__subclasses__():
        create_form_generate_route(subclass, app)

    # Create a single endpoint that returns all available Form endpoints
    @app.get("/forms")
    async def get_forms():
        forms = [subclass.__name__.lower() for subclass in obi.Form.__subclasses__()]
        return JSONResponse(content={"forms": forms})

    
    return

from pydantic import BaseModel
from obi_one.core.base import OBIBaseModel
class MorphologyFeatureToolOutput(BaseModel):
    """Output schema for the neurom tool."""
    hello: str


# # This function creates a FastAPI route for generating grid scans based on the provided OBI Form model.
# It takes a model class (subclass of obi.Form) and a FastAPI app instance as arguments.
def create_form_generate_route(model: Type[obi.Form], app: FastAPI):

    # model is the OBI.Form subclass 
    # i.e. <class 'obi.modeling.simulation.simulations.SimulationsForm'>

    # model_name is the name of the model (i.e. OBI.Form subclass) 
    # in lowercase (i.e. 'simulationsform')
    model_name = model.__name__.lower()

    model_return = None
    if hasattr(model, "Output") and isinstance(model.Output, type) and issubclass(model.Output, OBIBaseModel):
        model_return = model.Output


    @app.post(f"/{model_name}", summary="Hello world", description="Hello world description.")

    async def generate_grid_scan(form: model) -> model_return:

        try:
            grid_scan = obi.GridScan(form=form, output_root=f"../obi_output/fastapi_test/{model_name}/grid_scan")
            grid_scan.generate()
        except Exception as e:
            print(e)

        return MorphologyFeatureToolOutput(hello="Hello, world!")