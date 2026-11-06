"""Integration tests for CellMorphologyFromID against staging EntityCore.

Default auth uses obi-auth PKCE against staging (cached locally after first login).

    pytest tests/integration/test_cell_morphology_from_id_staging.py -m integration --no-cov -v

Optional launch-system style auth:

    export PERSISTENT_TOKEN_ID=<token-id>
    export DEPLOYMENT=staging

Optional project override (defaults to ``obi_one`` staging test lab and project IDs):

    TEST_VIRTUAL_LAB_ID=...
    TEST_PROJECT_ID=...

Optional explicit morphology IDs (skip discovery):

    TEST_CELL_MORPHOLOGY_ID_ASC=...
    TEST_CELL_MORPHOLOGY_ID_SWC=...
    TEST_CELL_MORPHOLOGY_ID_H5=...
"""

import os
from functools import partial
from typing import TYPE_CHECKING

import pytest
from entitysdk import Client, ProjectContext
from entitysdk.models import CellMorphology
from entitysdk.token_manager import TokenFromFunction
from entitysdk.types import AssetLabel, ContentType
from obi_auth import get_token
from obi_auth.typedef import AuthMode, DeploymentEnvironment

from obi_one import LAB_ID_STAGING_TEST, PROJECT_ID_STAGING_TEST
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID

if TYPE_CHECKING:
    from entitysdk.client import Client as DBClient

pytestmark = pytest.mark.integration

_MORPHOLOGY_FORMATS = (
    ContentType.application_asc,
    ContentType.application_swc,
    ContentType.application_x_hdf5,
)

_ENV_ID_KEYS = {
    ContentType.application_asc: "TEST_CELL_MORPHOLOGY_ID_ASC",
    ContentType.application_swc: "TEST_CELL_MORPHOLOGY_ID_SWC",
    ContentType.application_x_hdf5: "TEST_CELL_MORPHOLOGY_ID_H5",
}


def _staging_token_manager(deployment: DeploymentEnvironment, persistent_token_id: str):
    if persistent_token_id:
        return TokenFromFunction(
            partial(
                get_token,
                environment=deployment,
                auth_mode=AuthMode.persistent_token,
                persistent_token_id=persistent_token_id,
            ),
        )
    return TokenFromFunction(partial(get_token, environment=deployment))


@pytest.fixture(scope="module")
def staging_db_client() -> "DBClient":
    deployment_name = os.environ.get("DEPLOYMENT", DeploymentEnvironment.staging.value)
    deployment = DeploymentEnvironment(deployment_name)
    persistent_token_id = os.environ.get("PERSISTENT_TOKEN_ID", "").strip()
    virtual_lab_id = os.environ.get("TEST_VIRTUAL_LAB_ID", LAB_ID_STAGING_TEST)
    project_id = os.environ.get("TEST_PROJECT_ID", PROJECT_ID_STAGING_TEST)

    return Client(
        environment=deployment_name,
        project_context=ProjectContext(virtual_lab_id=virtual_lab_id, project_id=project_id),
        token_manager=_staging_token_manager(deployment, persistent_token_id),
    )


def _morphology_has_format(
    db_client: "DBClient", entity: CellMorphology, content_type: ContentType
) -> bool:
    assets = db_client.select_assets(
        entity=entity,
        selection={"label": AssetLabel.morphology, "content_type": content_type},
    ).all()
    return bool(assets)


def _discover_morphology_ids_by_format(db_client: "DBClient") -> dict[ContentType, str]:
    discovered: dict[ContentType, str] = {}
    for content_type in _MORPHOLOGY_FORMATS:
        env_key = _ENV_ID_KEYS[content_type]
        if env_id := os.environ.get(env_key, "").strip():
            discovered[content_type] = env_id
            continue

    if len(discovered) == len(_MORPHOLOGY_FORMATS):
        return discovered

    morphologies = db_client.search_entity(entity_type=CellMorphology, query={}, limit=200).all()
    for entity in morphologies:
        for content_type in _MORPHOLOGY_FORMATS:
            if content_type in discovered:
                continue
            if _morphology_has_format(db_client, entity, content_type):
                discovered[content_type] = str(entity.id)

    return discovered


@pytest.fixture(scope="module")
def morphology_ids_by_format(staging_db_client: "DBClient") -> dict[ContentType, str]:
    discovered = _discover_morphology_ids_by_format(staging_db_client)
    if not discovered:
        pytest.skip(
            "No CellMorphology assets found on staging (set TEST_CELL_MORPHOLOGY_ID_* env vars)"
        )
    return discovered


@pytest.mark.parametrize("content_type", _MORPHOLOGY_FORMATS)
def test_morphio_morphology_downloads_staging_asset(
    staging_db_client: "DBClient",
    morphology_ids_by_format: dict[ContentType, str],
    content_type: ContentType,
) -> None:
    morphology_id = morphology_ids_by_format.get(content_type)
    if morphology_id is None:
        pytest.skip(f"No staging CellMorphology with {content_type} morphology asset")

    reference = CellMorphologyFromID(id_str=morphology_id)
    loaded = reference.morphio_morphology(staging_db_client)

    assert loaded is not None
    assert loaded.root_sections is not None


def test_neurom_morphology_downloads_swc_when_available(
    staging_db_client: "DBClient",
    morphology_ids_by_format: dict[ContentType, str],
) -> None:
    morphology_id = morphology_ids_by_format.get(ContentType.application_swc)
    if morphology_id is None:
        pytest.skip("No staging CellMorphology with SWC morphology asset")

    reference = CellMorphologyFromID(id_str=morphology_id)
    loaded = reference.neurom_morphology(staging_db_client)

    assert loaded is not None
