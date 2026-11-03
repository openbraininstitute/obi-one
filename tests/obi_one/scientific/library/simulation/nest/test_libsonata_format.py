"""Tests that libsonata reads the SONATA-extension NEST format."""

import libsonata
import pytest

from tests.obi_one.scientific.library.simulation.nest._circuits import write_nest_circuit


@pytest.fixture
def circuit(tmp_path):
    return write_nest_circuit(tmp_path)


def test_libsonata_loads_with_template_dirs(circuit):
    cc = libsonata.CircuitConfig.from_file(str(circuit.circuit_config))
    assert cc.target_simulator == libsonata.SimulatorType.NEST
    props = cc.node_population_properties("exc")
    assert props.type == "point_process"
    assert props.model_template_dir.endswith("model_templates/exc")
    assert cc.edge_population_properties("exc__exc").model_template_dir.endswith(
        "model_templates/exc__exc"
    )


def test_node_model_templates(circuit):
    cc = libsonata.CircuitConfig.from_file(str(circuit.circuit_config))
    pop = cc.node_population("exc")
    names = list(pop.get_attribute("model_template", pop.select_all()))
    assert names == [
        "iaf_psc_alpha_type1",
        "iaf_psc_alpha_type1",
        "iaf_psc_alpha_type2",
        "iaf_psc_alpha_type2",
    ]


def test_edge_dynamics_attributes(circuit):
    cc = libsonata.CircuitConfig.from_file(str(circuit.circuit_config))
    pop = cc.edge_population("exc__exc")
    sel = pop.select_all()
    assert pop.dynamics_attribute_names == {"U", "u", "tau_rec", "tau_fac"}
    assert list(pop.get_dynamics_attribute("u", sel)) == pytest.approx([0.1, 0.2, 0.3])
    assert {"syn_weight", "delay", "model_template"} <= pop.attribute_names
    assert "U" not in pop.attribute_names


def test_simulation_config_with_synapse_replay(circuit):
    sim = libsonata.SimulationConfig.from_file(str(circuit.simulation_config))
    assert sim.target_simulator == libsonata.SimulatorType.NEST
    assert sim.run.dt == pytest.approx(0.1)
    assert sim.run.tstop == pytest.approx(20.0)
    replay = sim.input("input_spikes")
    assert replay.module == libsonata.SimulationConfig.InputBase.Module.synapse_replay
    assert replay.node_set == "input"
    assert replay.spike_file.endswith("inputs/input_spikes.h5")
