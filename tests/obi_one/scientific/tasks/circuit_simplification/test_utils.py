"""Tests for making sonata-simplify NEST exports loadable and registrable."""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import bluepysnap
import libsonata
import pytest
from entitysdk import types

from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.circuit_simplification import utils as test_module
from obi_one.scientific.tasks.circuit_validation.task import run_circuit_validation
from obi_one.utils.circuit import get_circuit_properties, get_circuit_size

from tests.obi_one.scientific.tasks.circuit_simplification._nest_export import (
    N_NEURONS,
    N_VPM,
    write_nest_export,
)


@pytest.fixture
def nest_export(tmp_path):
    config_path = write_nest_export(tmp_path / "export")
    test_module.make_nest_export_loadable(config_path.parent)
    return config_path


def test_export_as_written_is_not_loadable(tmp_path):
    config_path = write_nest_export(tmp_path / "export")

    with pytest.raises(libsonata.SonataError, match="target_simulator"):
        bluepysnap.Circuit(str(config_path))


def test_loadable_export_opens_with_bluepysnap(nest_export):
    circuit = bluepysnap.Circuit(str(nest_export))

    assert {name: circuit.nodes[name].type for name in circuit.nodes.population_names} == {
        "neurons": "point_neuron",
        "VPM": "virtual",
    }
    assert circuit.nodes["VPM"].size == N_VPM
    # Afferent queries need the edge indices the exporter does not write.
    assert sorted(circuit.edges["VPM__neurons__chemical"].afferent_nodes(2)) == [1]
    assert sorted(circuit.edges["neurons__neurons__chemical"].efferent_nodes(0)) == [1]


def test_nest_settings_move_to_a_simulation_config(nest_export):
    circuit_config = json.loads(nest_export.read_text(encoding="utf-8"))
    simulation_config = json.loads(
        (nest_export.parent / test_module.NEST_SIMULATION_CONFIG_NAME).read_text(encoding="utf-8")
    )

    assert "target_simulator" not in circuit_config
    assert "run" not in circuit_config
    assert simulation_config == {
        "manifest": {"$BASE_DIR": "."},
        "target_simulator": "NEST",
        "network": "circuit_config.json",
        "run": {"dt": 0.1},
    }
    # NEST's loader still finds its node and edge types files.
    assert all("node_types_file" in entry for entry in circuit_config["networks"]["nodes"])
    assert all("edge_types_file" in entry for entry in circuit_config["networks"]["edges"])


def test_registration_metadata_of_a_loadable_export(nest_export):
    circuit = Circuit(name="nest", path=str(nest_export))

    scale, n_neurons, n_synapses, n_connections = get_circuit_size(circuit)

    assert scale == types.CircuitScale.small
    assert (n_neurons, n_synapses, n_connections) == (N_NEURONS, 3, 3)
    # (has_morphologies, has_point_neurons, has_electrical_cell_models, has_spines)
    assert get_circuit_properties(circuit) == (False, True, False, False)


def test_validation_job_accepts_a_loadable_export(nest_export):
    """The registration endpoint's validation job opens the export and skips the SONATA schemas,
    which have none for NEST point neurons.
    """
    db_client = MagicMock()
    db_client.get_entity.return_value = MagicMock(target_simulator=types.TargetSimulator.NEST)

    with (
        patch(
            "obi_one.scientific.tasks.circuit_validation.task.stage_circuit",
            return_value=nest_export,
        ),
        patch(
            "obi_one.scientific.tasks.circuit_validation.task._update_lifecycle_status"
        ) as status,
        patch("obi_one.scientific.tasks.circuit_validation.task.run_validation") as validation,
    ):
        result = run_circuit_validation(db_client=db_client, circuit_id=uuid4())

    assert result["valid"] is True
    assert any("validation skipped" in warning for warning in result["warnings"])
    validation.assert_not_called()
    assert status.call_args.args[2] == "active"


def test_rejects_a_circuit_that_is_not_a_nest_export(tmp_path):
    config_path = write_nest_export(tmp_path / "export")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config.pop("target_simulator")
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="not a NEST export"):
        test_module.make_nest_export_loadable(config_path.parent)


def test_rejects_an_export_that_already_has_a_simulation_config(tmp_path):
    config_path = write_nest_export(tmp_path / "export")
    (config_path.parent / test_module.NEST_SIMULATION_CONFIG_NAME).write_text("{}")

    with pytest.raises(FileExistsError):
        test_module.make_nest_export_loadable(config_path.parent)


def test_rejects_a_node_types_file_with_several_model_types(tmp_path):
    config_path = write_nest_export(tmp_path / "export")
    types_path = config_path.parent / "neurons/nodes_types.csv"
    types_path.write_text(
        types_path.read_text(encoding="utf-8") + "-2 virtual nest:spike_generator x.json\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="2 model types"):
        test_module.make_nest_export_loadable(config_path.parent)
