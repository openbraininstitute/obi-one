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


def resolve_ref(openapi_schema: dict, ref: str) -> dict:
    """Resolves a JSON Reference (e.g., '#/components/schemas/Item')
    within the openapi_schema.
    """
    if not ref.startswith("#/"):
        msg = f"Only local references (starting with #/) are supported. Got: {ref}"
        raise ValueError(msg)

    # Split the path, skipping the first element which is '#'
    path_parts = ref.split("/")[1:]

    current_node = openapi_schema

    for part in path_parts:
        current_node = current_node.get(part)
        if current_node is None:
            msg = f"Reference '{ref}' could not be resolved. Part '{part}' missing."
            raise KeyError(msg)

    return current_node


def extract_and_print_schema() -> None:
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )

    for path, value in openapi_schema["paths"].items():
        if not path.startswith("/generated"):
            continue

        schema_ref = value["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]

        if schema_ref != "#/components/schemas/CircuitSimulationScanConfig":
            continue

        ## schema = resolve_ref(openapi_schema, schema_ref)

        with Path.open(current_dir / "example_simulations_form.json") as f:
            schema = json.load(f)

        with Path.open(current_dir / "meta_schema.json") as f:
            meta_schema = json.load(f)

        validate(instance=schema, schema=meta_schema)


if __name__ == "__main__":
    extract_and_print_schema()
