from app.config import settings
from app.dependencies.auth import UserContextDep
from app.logger import L

from fastapi import APIRouter

def activate_neuroagent_router(router: APIRouter) -> APIRouter:

    # Create POST endpoint
    @router.get("/hello_world", summary="Hello world summary", description="Hello workd description")
    async def hello_world(user_context: UserContextDep) -> dict:

        L.info("generate_grid_scan")
        L.debug("user_context: %s", user_context.model_dump())

        return {"message": "Hello world!"}

    return router
