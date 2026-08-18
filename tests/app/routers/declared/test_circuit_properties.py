from types import SimpleNamespace

import entitysdk
import pytest

from app.endpoints import circuit_properties
from obi_one.scientific.library.entity_property_types import CircuitUsability


def _circuit_metrics():
    return SimpleNamespace(
        names_of_nodesets=["All"],
        names_of_biophys_node_populations=["biophysical"],
        names_of_point_node_populations=[],
        names_of_virtual_node_populations=[],
        biophysical_node_populations=[
            SimpleNamespace(
                name="biophysical",
                property_unique_values={},
                dynamics_param_names=[],
            )
        ],
        point_node_populations=[],
        virtual_node_populations=[],
    )


def _db_client(scale: entitysdk.types.CircuitScale):
    return SimpleNamespace(
        get_entity=lambda **_: SimpleNamespace(scale=scale, has_morphologies=True),
    )


def test_circuit_metrics_endpoint_returns_metrics(monkeypatch):
    metrics = _circuit_metrics()
    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", lambda **_: metrics)

    response = circuit_properties.circuit_metrics_endpoint(
        circuit_id="circuit-id",
        db_client=SimpleNamespace(),
    )

    assert response is metrics


def test_circuit_metrics_endpoint_maps_sdk_error_to_500(monkeypatch):
    def raise_entity_sdk_error(**_kwargs):
        raise entitysdk.exception.EntitySDKError

    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", raise_entity_sdk_error)

    with pytest.raises(circuit_properties.HTTPException) as exc_info:
        circuit_properties.circuit_metrics_endpoint(
            circuit_id="circuit-id",
            db_client=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 500


def test_circuit_populations_endpoint_returns_biophysical_populations(monkeypatch):
    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", lambda **_: _circuit_metrics())

    response = circuit_properties.circuit_populations_endpoint(
        circuit_id="circuit-id",
        db_client=SimpleNamespace(),
    )

    assert response.populations == ["biophysical"]


def test_circuit_populations_endpoint_maps_sdk_error_to_500(monkeypatch):
    def raise_entity_sdk_error(**_kwargs):
        raise entitysdk.exception.EntitySDKError

    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", raise_entity_sdk_error)

    with pytest.raises(circuit_properties.HTTPException) as exc_info:
        circuit_properties.circuit_populations_endpoint(
            circuit_id="circuit-id",
            db_client=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 500


def test_circuit_nodesets_endpoint_returns_nodesets(monkeypatch):
    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", lambda **_: _circuit_metrics())

    response = circuit_properties.circuit_nodesets_endpoint(
        circuit_id="circuit-id",
        db_client=SimpleNamespace(),
    )

    assert response.nodesets == ["All"]


def test_circuit_nodesets_endpoint_maps_sdk_error_to_500(monkeypatch):
    def raise_entity_sdk_error(**_kwargs):
        raise entitysdk.exception.EntitySDKError

    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", raise_entity_sdk_error)

    with pytest.raises(circuit_properties.HTTPException) as exc_info:
        circuit_properties.circuit_nodesets_endpoint(
            circuit_id="circuit-id",
            db_client=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 500


@pytest.mark.parametrize(
    "scale",
    [
        entitysdk.types.CircuitScale.single,
        entitysdk.types.CircuitScale.pair,
        entitysdk.types.CircuitScale.small,
        entitysdk.types.CircuitScale.microcircuit,
    ],
)
def test_morphology_locations_are_enabled_through_microcircuit(scale, monkeypatch):
    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", lambda **_: _circuit_metrics())

    response = circuit_properties.mapped_circuit_properties_endpoint(
        circuit_id="circuit-id",
        db_client=_db_client(scale),
    )

    assert response["usability"][CircuitUsability.SHOW_MORPHOLOGY_LOCATIONS] is True


@pytest.mark.parametrize(
    "scale",
    [
        entitysdk.types.CircuitScale.region,
        entitysdk.types.CircuitScale.system,
        entitysdk.types.CircuitScale.whole_brain,
    ],
)
def test_morphology_locations_are_disabled_above_microcircuit(scale, monkeypatch):
    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", lambda **_: _circuit_metrics())

    response = circuit_properties.mapped_circuit_properties_endpoint(
        circuit_id="circuit-id",
        db_client=_db_client(scale),
    )

    assert response["usability"][CircuitUsability.SHOW_MORPHOLOGY_LOCATIONS] is False


@pytest.mark.parametrize(
    ("scale", "expected"),
    [
        (entitysdk.types.CircuitScale.single, True),
        (entitysdk.types.CircuitScale.pair, False),
        (entitysdk.types.CircuitScale.small, False),
        (entitysdk.types.CircuitScale.microcircuit, False),
    ],
)
def test_explicit_morphology_locations_are_single_neuron_only(scale, expected, monkeypatch):
    """Narrower than the general morphology-locations gate, and deliberately so.

    An explicit location names a section id with no cell attached, so on a circuit holding
    several neurons the same id is applied to every morphology — where it refers to a
    different branch on each.
    """
    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", lambda **_: _circuit_metrics())

    response = circuit_properties.mapped_circuit_properties_endpoint(
        circuit_id="circuit-id",
        db_client=_db_client(scale),
    )

    assert response["usability"][CircuitUsability.SHOW_EXPLICIT_MORPHOLOGY_LOCATIONS] is expected


def test_explicit_morphology_locations_are_enabled_for_memodels(monkeypatch):
    """An MEModel is one neuron, so a section id names exactly one branch.

    MEModels are not stored as Circuit, so they fall through to the default usability
    branch which enables explicit morphology locations.
    """

    def _no_circuit_metrics(**_):
        msg = "not a circuit"
        raise entitysdk.exception.EntitySDKError(msg)

    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", _no_circuit_metrics)

    response = circuit_properties.mapped_circuit_properties_endpoint(
        circuit_id="memodel-id",
        db_client=SimpleNamespace(get_entity=lambda **_: None),
    )

    assert response["usability"][CircuitUsability.SHOW_EXPLICIT_MORPHOLOGY_LOCATIONS] is True


def test_memodel_without_circuit_metrics_gets_default_usability(monkeypatch):
    def raise_entity_sdk_error(**_kwargs):
        raise entitysdk.exception.EntitySDKError

    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", raise_entity_sdk_error)
    db_client = _db_client(entitysdk.types.CircuitScale.single)

    response = circuit_properties.mapped_circuit_properties_endpoint(
        circuit_id="memodel-id",
        db_client=db_client,
    )

    assert "MechanismVariablesByIonChannel" not in response
    assert response["usability"][CircuitUsability.SHOW_MORPHOLOGY_LOCATIONS] is True
    assert response["usability"][CircuitUsability.SHOW_NEURON_SETS] is False


def test_unknown_entity_without_circuit_metrics_returns_500(monkeypatch):
    def raise_entity_sdk_error(**_kwargs):
        raise entitysdk.exception.EntitySDKError

    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", raise_entity_sdk_error)
    db_client = type(
        "DBClient",
        (),
        {"get_entity": staticmethod(raise_entity_sdk_error)},
    )()

    with pytest.raises(circuit_properties.HTTPException) as exc_info:
        circuit_properties.mapped_circuit_properties_endpoint(
            circuit_id="unknown-id",
            db_client=db_client,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["detail"] == "No properties found for entity unknown-id."


def test_circuit_entity_lookup_failure_uses_default_usability(monkeypatch):
    monkeypatch.setattr(circuit_properties, "get_circuit_metrics", lambda **_: _circuit_metrics())

    def raise_entity_sdk_error(**_kwargs):
        raise entitysdk.exception.EntitySDKError

    db_client = type(
        "DBClient",
        (),
        {"get_entity": staticmethod(raise_entity_sdk_error)},
    )()

    response = circuit_properties.mapped_circuit_properties_endpoint(
        circuit_id="circuit-id",
        db_client=db_client,
    )

    assert response["usability"][CircuitUsability.SHOW_ELECTRIC_FIELD_STIMULI] is False
    assert response["usability"][CircuitUsability.SHOW_NEURON_SETS] is False
