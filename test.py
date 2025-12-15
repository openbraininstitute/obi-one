from pathlib import Path
import json
import sys
import os
from fastapi.openapi.utils import get_openapi
from jsonschema import validate


current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from app.application import app


import json
import jsonref
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


# --- 1. The Extraction Function ---
def get_dereferenced_schema(app: FastAPI, schema_name: str) -> dict:
    """
    Generates the OpenAPI spec from a FastAPI app, resolves all $ref pointers,
    and returns the specific schema requested as a clean dict.
    """
    # Generate the raw OpenAPI dictionary from the app
    # This contains the $ref pointers (e.g., "#/components/schemas/SubModel")
    raw_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )

    # Use jsonref to resolve all references recursively
    # We use proxies=False to get standard dicts back immediately
    dereferenced_spec = jsonref.replace_refs(raw_schema, proxies=False)

    try:
        # Extract the specific schema
        target_schema = dereferenced_spec["components"]["schemas"][schema_name]
        return target_schema
    except KeyError:
        raise ValueError(
            f"Schema '{schema_name}' not found. Ensure the Pydantic model is used in a route."
        )


# B. actually running the extraction
if __name__ == "__main__":
    try:
        # Pass your actual 'app' object here
        full_schema = get_dereferenced_schema(app, "CircuitSimulationScanConfig")

        print("--- Fully Dereferenced Schema ---")
        print(json.dumps(full_schema, indent=2))

    except Exception as e:
        print(f"Error: {e}")
