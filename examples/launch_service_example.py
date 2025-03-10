# Launch server
# uvicorn examples.launch_service_example:app --reload

import obi
from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.cors import CORSMiddleware

app = FastAPI()

# Define allowed origins
origins = [
    "http://localhost:3000",  # Allow frontend running on React/Vue/Next.js
    # "http://127.0.0.1:8000",
    "https://yourdomain.com",  # Allow specific production domain
    # "*"  # Allow all domains (not recommended for production)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


obi.activate_fastapi_app(app)