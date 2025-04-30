
from fastapi import FastAPI
from fastapi.responses import JSONResponse

import obi_one as obi
from app.dependencies.auth import UserContextDep
from app.logger import L


def activate_fastapi_app(app: FastAPI) -> None:

    # For each obi.Form subclass, create a FastAPI route for generating grid scans.
    for subclass in obi.Form.__subclasses__():
        create_form_generate_route(subclass, app)

    # Create a single endpoint that returns all available Form endpoints
    @app.get("")
    async def get_forms() -> JSONResponse:
        forms = [subclass.__name__.lower() for subclass in obi.Form.__subclasses__()]
        return JSONResponse(content={"forms": forms})


# # This function creates a FastAPI route for generating grid scans based on the provided OBI Form model.
# It takes a model class (subclass of obi.Form) and a FastAPI app instance as arguments.
def create_form_generate_route(model: type[obi.Form], app: FastAPI) -> None:

    # model is the OBI.Form subclass
    # i.e. <class 'obi.modeling.simulation.simulations.SimulationsForm'>

    # model_name is the name of the model (i.e. OBI.Form subclass)
    # in lowercase (i.e. 'simulationsform')
    model_name = model.__name__.lower()

    @app.post(f"/{model_name}")
    async def generate_grid_scan(user_context: UserContextDep, form: model) -> dict:

        L.info("generate_grid_scan")
        L.info("user_context: %s", user_context.model_dump())

        try:
            grid_scan = obi.GridScan(form=form, output_root=f"../obi_output/fastapi_test/{model_name}/grid_scan")
            grid_scan.generate()
        except Exception:
            L.exception("Generic exception")

        return {}
