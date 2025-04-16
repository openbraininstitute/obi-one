from fastapi import FastAPI, HTTPException
from typing import Type, Dict, Any, List
import obi_one as obi
from fastapi.responses import JSONResponse


def activate_fastapi_app(app: FastAPI):

    for subclass in obi.Form.__subclasses__():
        generate_routes(subclass, app)
    return


# Auto-generate API routes
def generate_routes(model: Type[obi.Form], app: FastAPI):

    # model is the OBI.Form subclass 
    # i.e. <class 'obi.modeling.simulation.simulations.SimulationsForm'>

    # model_name is the name of the model (i.e. OBI.Form subclass) 
    # in lowercase (i.e. 'simulationsform')
    model_name = model.__name__.lower()

    @app.post(f"/{model_name}/")
    async def generate_grid_scan(form: model):
        
        print("\ngenerate_grid_scan")

        try:
            grid_scan = obi.GridScan(form=form, output_root=f"../obi_output/fastapi_test/{model_name}/grid_scan")
            grid_scan.generate()
        except Exception as e:
            print(e)

        return {}