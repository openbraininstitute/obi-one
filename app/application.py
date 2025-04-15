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

obi_one.activate_fastapi_app(app)
