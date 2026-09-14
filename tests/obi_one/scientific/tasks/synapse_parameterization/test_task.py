"""End-to-end tests for SynapseParameterizationTask.execute against a local circuit.

Mirrors the circuit-extraction task tests: run the task on a tiny local circuit with no
db_client, so the parameterization/output path is exercised while the entitycore
registration branch (which needs a db_client and a parent entity) is skipped.
"""

import bluepysnap as snap
import pytest

import obi_one as obi
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
)

from tests.utils import CIRCUIT_DIR

# Intrinsic biophysical -> biophysical edge population of the tiny test circuit.
EDGE_POPULATION_NAME = "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical"


def _local_circuit():
    return obi.Circuit(
        name="N_10__top_nodes_dim6",
        path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
    )


def _build_config(tmp_path):
    """A minimal single-config: one excitatory model applied to every synapse."""
    config = obi.SynapseParameterizationSingleConfig.empty_config()
    config.set(
        obi.Info(campaign_name="Test", campaign_description="Test parameterization"),
        name="info",
    )
    config.set(config.Initialize(circuit=_local_circuit()), name="initialize")

    conductance = obi.GammaDistribution(shape=4.0, scale=0.25)
    config.add(conductance, "Excitatory conductance distribution")
    model = obi.ExcitatoryTsodyksMarkramSynapticModel(conductance_distribution=conductance.ref)
    config.add(model, "Excitatory synaptic model")
    config.add(
        obi.AllPairsSynapticModelAssigner(
            edge_population_name=EDGE_POPULATION_NAME,
            synaptic_model=model.ref,
        ),
        name="all_pairs",
    )
    config.fill_block_references_and_names()

    config.scan_output_root = tmp_path / "scan"
    config.coordinate_output_root = tmp_path / "scan" / "parameterized"
    return config


@pytest.mark.filterwarnings("ignore::FutureWarning")
def test_execute_parameterizes_local_circuit(tmp_path):
    config = _build_config(tmp_path)

    result = obi.SynapseParameterizationTask(config=config).execute(db_client=None)

    # Local circuit has no parent entity, so nothing is registered and no id is returned.
    assert result is None

    # The parameterized circuit is written to the coordinate output directory.
    output_config = config.coordinate_output_root / "circuit_config.json"
    assert output_config.exists()

    result_circuit = snap.Circuit(str(output_config))

    # The output is a full copy of the circuit, not just the modified edge file: every
    # edge population of the source survives, including the ones no assigner touched.
    source = _local_circuit().sonata_circuit
    assert set(result_circuit.edges.population_names) == set(source.edges.population_names)

    edges = result_circuit.edges[EDGE_POPULATION_NAME]

    # Every Tsodyks-Markram parameter is present on the edge population.
    for parameter in ExcitatoryTsodyksMarkramSynapticModel.parameter_names():
        assert parameter in edges.property_names

    # Every synapse carries the excitatory model's syn_type_id (the all-pairs assigner).
    expected_syn_type_id = ExcitatoryTsodyksMarkramSynapticModel().syn_type_id
    syn_type_ids = set(edges.get(edges.ids(), properties=["syn_type_id"])["syn_type_id"])
    assert syn_type_ids == {expected_syn_type_id}


def test_execute_rejects_output_dir_that_already_exists(tmp_path):
    """Running twice into the same coordinate output must not silently overwrite."""
    config = _build_config(tmp_path)

    with pytest.warns(FutureWarning):
        obi.SynapseParameterizationTask(config=config).execute(db_client=None)

    # A second run against the same output directory fails rather than clobbering it.
    with pytest.raises(FileExistsError):
        obi.SynapseParameterizationTask(config=config).execute(db_client=None)
