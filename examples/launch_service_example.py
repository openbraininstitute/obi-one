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
    # "http://127.0.0.1:3000"
    # "*"  # Allow all domains (not recommended for production)
]

# Trying to fix CORS issue (currently not solved)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Access-Control-Allow-Origin"]
)

# Possibly useful to solving issue
# app.headers["Access-Control-Allow-Origin"] = True


obi.activate_fastapi_app(app)