from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import obi_one
from app.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION or "0.0.0",
    debug=settings.APP_DEBUG,
    root_path=settings.ROOT_PATH,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "message": (
            f"Welcome to {settings.APP_NAME} {settings.APP_VERSION}. "
            f"See {settings.ROOT_PATH}/docs for OpenAPI documentation."
        )
    }


@app.get("/health")
async def health() -> dict:
    """Health endpoint."""
    return {
        "status": "OK",
    }


@app.get("/version")
async def version() -> dict:
    """Version endpoint."""
    return {
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "commit_sha": settings.COMMIT_SHA,
    }


obi_one.activate_fastapi_app(app)
