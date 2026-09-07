import pytest

from app.endpoints import scan_config
from app.errors import ApiError
from obi_one.scientific.tasks.schema_example import SchemaExampleScanConfig

_SCHEMA_EXAMPLE_PATH = "/generated/schema-example-scan-config-generate-grid"
_BUILD_SYNAPTOME_PATH = "/generated/me-model-synaptic-model-placement-scan-config-generate-grid"


def _route(path):
    return next(route for route in scan_config.router.routes if route.path == path)


def test_schema_example_endpoint_reports_its_model_name():
    route = _route(_SCHEMA_EXAMPLE_PATH)

    with pytest.raises(ApiError) as exc_info:
        route.endpoint(db_client=object(), form=SchemaExampleScanConfig.model_construct())

    assert exc_info.value.message == "SchemaExampleScanConfig endpoint is non-functional."


def test_build_synaptome_scan_config_endpoint_is_registered():
    route = _route(_BUILD_SYNAPTOME_PATH)

    assert route.methods == {"POST"}
    assert (
        route.endpoint.__annotations__["form"]
        is scan_config.MEModelSynapticModelPlacementScanConfig
    )
