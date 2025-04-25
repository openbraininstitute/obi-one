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



import inspect
from typing import get_type_hints
# # This function creates a FastAPI route for generating grid scans based on the provided OBI Form model.
# It takes a model class (subclass of obi.Form) and a FastAPI app instance as arguments.
def create_form_generate_route(model: Type[obi.Form], app: FastAPI):

    # model is the OBI.Form subclass i.e. <class 'obi.modeling.simulation.simulations.SimulationsForm'>

    # model_name is the name of the model in lowercase (i.e. 'simulationsform')
    model_name = model.__name__.lower()

    model_return = None
    if hasattr(model, "single_coord_class_name") and model.single_coord_class_name:
        # Check if the class name exists in the obi module
        if not hasattr(obi, model.single_coord_class_name):
            raise ValueError(f"Class {model.single_coord_class_name} not found in obi module.")
        
        cls = getattr(obi, model.single_coord_class_name)
    
        method = cls.run
        return_type = get_type_hints(method).get('return')
        model_return = return_type



    @app.post(f"/{model_name}", summary=model.name, description=model.description)
    async def generate_grid_scan(form: model) -> model_return:

        try:
            grid_scan = obi.GridScan(form=form, output_root=f"../obi_output/fastapi_test/{model_name}/grid_scan")
            grid_scan.generate()
        except Exception as e:
            print(e)

        return MorphologyFeatureToolOutput(hello="Hello, world!")