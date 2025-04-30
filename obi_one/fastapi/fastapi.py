from obi_one.fastapi.neuroagent_endpoints import router as neuroagent_endpoints_router
from obi_one.fastapi.generated_endpoints import router as generated_endpoints_router

from fastapi import FastAPI

def activate_fastapi_app(app: FastAPI):

    app.include_router(generated_endpoints_router)
    app.include_router(neuroagent_endpoints_router)