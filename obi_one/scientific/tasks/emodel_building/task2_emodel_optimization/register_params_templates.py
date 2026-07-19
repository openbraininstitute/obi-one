"""Register SSCx params templates as TaskConfig entities in entitycore.

Usage::

    python -m obi_one.scientific.tasks.emodel_building.\
        task2_emodel_optimization.register_params_templates

This is a one-time script to upload the standard BluePyEModel params JSON
files (from SSCxEModelExamples) as TaskConfig entities so they can be
selected via a dropdown in the optimization UI.
"""

import logging
from pathlib import Path

import entitysdk
from entitysdk.models import TaskConfig
from entitysdk.types import AssetLabel, ContentType, TaskConfigType

L = logging.getLogger(__name__)

PARAMS_DIR = Path(__file__).parent / "params_templates"

TEMPLATES = [
    {
        "file": "pyr.json",
        "name": "Params: Pyramidal (SSCx)",
        "description": "Standard params for pyramidal cells (SSCxEModelExamples).",
    },
    {
        "file": "int.json",
        "name": "Params: Interneuron (SSCx)",
        "description": "Standard params for interneurons (SSCxEModelExamples).",
    },
    {
        "file": "int_delayed.json",
        "name": "Params: Interneuron delayed (SSCx)",
        "description": "Params for interneurons with delayed KdShu2007 (SSCxEModelExamples).",
    },
    {
        "file": "int_delayed_noise.json",
        "name": "Params: Interneuron delayed+noise (SSCx)",
        "description": (
            "Params for interneurons with delayed KdShu2007"
            " and StochKv3 noise (SSCxEModelExamples)."
        ),
    },
    {
        "file": "int_noise.json",
        "name": "Params: Interneuron noise (SSCx)",
        "description": "Params for interneurons with StochKv3 noise (SSCxEModelExamples).",
    },
]


def register_params_templates(db_client: entitysdk.client.Client) -> None:
    """Register all params templates as TaskConfig entities."""
    for template in TEMPLATES:
        params_path = PARAMS_DIR / template["file"]
        if not params_path.exists():
            msg = f"Params file not found: {params_path}"
            raise FileNotFoundError(msg)

        params_content = params_path.read_bytes()

        task_config = db_client.register_entity(
            TaskConfig(
                name=template["name"],
                description=template["description"],
                task_config_type=TaskConfigType.emodel_optimization__config,
                meta={},
                inputs=[],
            )
        )

        db_client.upload_content(
            entity_id=task_config.id,
            entity_type=TaskConfig,
            file_content=params_content,
            file_name="params.json",
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.task_config,
        )

        L.info("Registered: %s -> %s", template["name"], task_config.id)


if __name__ == "__main__":
    from entitysdk import Client, ProjectContext
    from obi_auth import get_token

    import obi_one as obi

    token = get_token(environment="staging")
    client = Client(
        api_url="https://staging.cell-a.openbraininstitute.org/api/entitycore",
        project_context=ProjectContext(
            virtual_lab_id=obi.LAB_ID_STAGING_TEST,
            project_id=obi.PROJECT_ID_STAGING_TEST,
        ),
        token_manager=token,
    )
    register_params_templates(client)
