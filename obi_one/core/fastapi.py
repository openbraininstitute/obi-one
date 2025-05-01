
from fastapi import APIRouter
from fastapi.responses import JSONResponse

import obi_one as obi
from app.config import settings
from app.dependencies.auth import UserContextDep
from app.logger import L


def activate_router(router: APIRouter) -> APIRouter:

    # For each obi.Form subclass, create a FastAPI route for generating grid scans.
    for subclass in obi.Form.__subclasses__():
        create_form_generate_route(subclass, router)

    # Create a single endpoint that returns all available Form endpoints
    @router.get("")
    async def get_forms() -> JSONResponse:
        forms = [subclass.__name__.lower() for subclass in obi.Form.__subclasses__()]
        return JSONResponse(content={"forms": forms})

    return router


def create_form_generate_route(model: type[obi.Form], router: APIRouter) -> None:
    """Create a FastAPI route for generating grid scans based on the provided OBI Form model.

    Args:
        model: OBI Form model.
        router: FastAPI router.
    """
    # model is the OBI.Form subclass
    # i.e. <class 'obi.modeling.simulation.simulations.SimulationsForm'>

    # model_name is the name of the model (i.e. OBI.Form subclass)
    # in lowercase (i.e. 'simulationsform')
    model_name = model.__name__.lower()

    @router.post(f"/{model_name}", summary=f"Generate a grid scan for {model.__name__}")
    async def generate_grid_scan(user_context: UserContextDep, form: model) -> dict:

        L.info("generate_grid_scan")
        L.debug("user_context: %s", user_context.model_dump())

        try:
            output_root = settings.OUTPUT_DIR / "fastapi_test" / model_name / "grid_scan"
            grid_scan = obi.GridScan(form=form, output_root=str(output_root))
            grid_scan.generate()
        except Exception:  # noqa: BLE001
            L.exception("Generic exception")

        return {}
