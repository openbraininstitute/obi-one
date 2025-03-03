# Launch server
# uvicorn examples.launch_service_example:app --reload

import obi
from fastapi import FastAPI

app = FastAPI()
obi.activate_fastapi_app(app)