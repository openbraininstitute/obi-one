"""Tests for the circuit rewiring task and its structural connectivity models.

The task stages a SONATA circuit, draws a new connectivity-only edge population from
user-specified source/target neuron sets and a per-pathway structural connectivity model, and
registers the new edge population in ``circuit_config.json``. These tests exercise the full
local (no database) execution path against a tiny biophysical circuit, plus unit tests for the
connectivity models themselves.
"""

import importlib.util
from pathlib import Path
from typing import get_args

import libsonata
import numpy as np
import pydantic
import pytest
from bluepysnap import Circuit

from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.blocks.distributions.constant import IntConstantDistribution
from obi_one.scientific.blocks.morphology_locations.clustered import (
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.explicit import (
    ExplicitMorphologyLocations,
    MorphologyLocationPoint,
)
from obi_one.scientific.blocks.morphology_locations.path_distance import (
    PathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.random import (
    RandomGroupedMorphologyLocations,
    RandomMorphologyLocations,
)
from obi_one.scientific.blocks.neuron_sets.population import (
    BiophysicalPopulationNeuronSet,
    PointPopulationNeuronSet,
    VirtualPopulationNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.specific import AllBiophysicalNeurons
from obi_one.scientific.blocks.structural_conn_models.base import PathwayConnContext
from obi_one.scientific.blocks.structural_conn_models.distance_dependent import (
    DistanceDependentConnModel,
)
from obi_one.scientific.blocks.structural_conn_models.erdos_renyi import ErdosRenyiConnModel
from obi_one.scientific.blocks.structural_conn_models.sgsg import SgsgConnModel
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.block import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.library.circuit import Circuit as OBICircuit
from obi_one.scientific.tasks.circuit_rewiring import CircuitRewiringScanConfig
from obi_one.scientific.tasks.circuit_rewiring.config import CircuitConnectivityPathway
from obi_one.scientific.tasks.circuit_rewiring.task import CircuitRewiringTask
from obi_one.scientific.unions_and_references.morphology_locations import (
    NonGroupedMorphologyLocationsReference,
    NonGroupedMorphologyLocationUnion,
)

from tests.utils import CIRCUIT_DIR

CIRCUIT_PATH = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"
BIOPHYSICAL_POPULATION = "S1nonbarrel_neurons"

# Edge properties written for the postsynaptic location of each connection (same columns as
# Build Synaptome writes for its afferent locations).
AFFERENT_COLUMNS = {
    "afferent_section_id",
    "afferent_segment_id",
    "afferent_segment_offset",
    "afferent_section_pos",
    "afferent_section_type",
    "afferent_center_x",
    "afferent_center_y",
    "afferent_center_z",
}
# Edge properties written by the (Tsodyks-Markram) synaptic model of a pathway.
SYNAPSE_PARAMETER_COLUMNS = set(ExcitatoryTsodyksMarkramSynapticModel.parameter_names())
ALL_EDGE_COLUMNS = AFFERENT_COLUMNS | SYNAPSE_PARAMETER_COLUMNS
POINT_CIRCUIT_PATH = (
    Path(__file__).parents[2] / "library" / "simulation" / "data" / "circuit_config.json"
)


def _user_edge_properties(edges) -> set[str]:
    """Edge property names excluding SONATA's implicit '@...' ones."""
    return {p for p in edges.property_names if not p.startswith("@")}


_HAS_CONNALYSIS = importlib.util.find_spec("connalysis") is not None
requires_connalysis = pytest.mark.skipif(
    not _HAS_CONNALYSIS, reason="requires connectome-analysis (connalysis)"
)


# --------------------------------------------------------------------------------------------
# Connectivity model unit tests (no circuit staging).
# --------------------------------------------------------------------------------------------


def _context(n_source, n_target, *, same_population, positions=False):
    source_ids = np.arange(n_source, dtype=np.int64)
    target_ids = source_ids if same_population else np.arange(n_target, dtype=np.int64) + n_source
    rng = np.random.default_rng(0)
    src_pos = rng.random((n_source, 3)) * 1000 if positions else None
    tgt_pos = (
        src_pos
        if same_population and positions
        else (rng.random((target_ids.size, 3)) * 1000 if positions else None)
    )
    return PathwayConnContext(
        source_ids=source_ids,
        target_ids=target_ids,
        source_positions=src_pos,
        target_positions=tgt_pos,
        same_population=same_population,
    )


def test_erdos_renyi_probability_one_is_full_connectivity():
    model = ErdosRenyiConnModel(connection_probability=1.0, allow_self_connections=False)
    ctx = _context(5, 5, same_population=True)
    pre, post = model.draw_connections(ctx, np.random.default_rng(0))
    # Full connectivity minus self-connections.
    assert pre.size == 5 * 4
    assert (pre != post).all()


def test_erdos_renyi_probability_one_with_self_connections():
    model = ErdosRenyiConnModel(connection_probability=1.0, allow_self_connections=True)
    ctx = _context(5, 5, same_population=True)
    pre, _post = model.draw_connections(ctx, np.random.default_rng(0))
    assert pre.size == 5 * 5


def test_erdos_renyi_probability_zero_is_empty():
    model = ErdosRenyiConnModel(connection_probability=0.0)
    ctx = _context(10, 10, same_population=True)
    pre, post = model.draw_connections(ctx, np.random.default_rng(0))
    assert pre.size == 0
    assert post.size == 0


def test_erdos_renyi_matches_target_probability_statistically():
    model = ErdosRenyiConnModel(connection_probability=0.1)
    ctx = _context(200, 200, same_population=False)
    pre, _post = model.draw_connections(ctx, np.random.default_rng(7))
    empirical = pre.size / (200 * 200)
    assert 0.08 < empirical < 0.12


def test_distance_dependent_zero_distance_uses_scale_factor():
    # All neurons at the same position: distance 0, so P == scale_factor everywhere.
    model = DistanceDependentConnModel(scale_factor=1.0, length_scale=100.0)
    source_ids = np.arange(50, dtype=np.int64)
    target_ids = np.arange(50, dtype=np.int64) + 50
    positions_src = np.zeros((50, 3))
    positions_tgt = np.zeros((50, 3))
    ctx = PathwayConnContext(
        source_ids=source_ids,
        target_ids=target_ids,
        source_positions=positions_src,
        target_positions=positions_tgt,
        same_population=False,
    )
    pre, _post = model.draw_connections(ctx, np.random.default_rng(0))
    # scale_factor == 1.0 at zero distance => fully connected.
    assert pre.size == 50 * 50


def test_distance_dependent_decays_with_distance():
    """Nearby targets receive more connections than distant ones."""
    model = DistanceDependentConnModel(scale_factor=1.0, length_scale=50.0)
    # One source at origin; targets placed at increasing distances along x.
    source_ids = np.array([0], dtype=np.int64)
    target_ids = np.arange(200, dtype=np.int64) + 1
    source_positions = np.zeros((1, 3))
    # Half the targets near the source, half far away.
    near = np.zeros((100, 3))
    near[:, 0] = 5.0
    far = np.zeros((100, 3))
    far[:, 0] = 500.0
    target_positions = np.vstack([near, far])
    ctx = PathwayConnContext(
        source_ids=source_ids,
        target_ids=target_ids,
        source_positions=source_positions,
        target_positions=target_positions,
        same_population=False,
    )
    _pre, post = model.draw_connections(ctx, np.random.default_rng(3))
    near_ids = set(target_ids[:100].tolist())
    far_ids = set(target_ids[100:].tolist())
    n_near = sum(1 for t in post if int(t) in near_ids)
    n_far = sum(1 for t in post if int(t) in far_ids)
    assert n_near > n_far
    assert n_far == 0  # exp(-10) is effectively zero


def test_distance_dependent_requires_positions():
    model = DistanceDependentConnModel(scale_factor=1.0, length_scale=100.0)
    ctx = _context(5, 5, same_population=False, positions=False)
    with pytest.raises(OBIONEError, match="requires x/y/z positions"):
        model.draw_connections(ctx, np.random.default_rng(0))


# --------------------------------------------------------------------------------------------
# Synapses-per-connection expansion unit tests.
# --------------------------------------------------------------------------------------------


def test_expand_by_synapse_count_constant():
    """A constant distribution of value k turns every connection into k identical edges."""
    pre = np.array([0, 1, 2], dtype=np.int64)
    post = np.array([10, 11, 12], dtype=np.int64)
    dist = IntConstantDistribution(value=3)
    exp_pre, exp_post = CircuitRewiringTask._expand_by_synapse_count(
        pre, post, dist, np.random.default_rng(0)
    )
    assert exp_pre.size == 3 * 3
    # Each original pair appears exactly 3 times.
    pairs = list(zip(exp_pre.tolist(), exp_post.tolist(), strict=True))
    for src, tgt in zip(pre.tolist(), post.tolist(), strict=True):
        assert pairs.count((src, tgt)) == 3


def test_expand_by_synapse_count_clamps_to_one():
    """Non-positive samples are clamped to 1, so every drawn connection survives."""
    pre = np.array([5, 6], dtype=np.int64)
    post = np.array([7, 8], dtype=np.int64)
    dist = IntConstantDistribution(value=0)
    exp_pre, exp_post = CircuitRewiringTask._expand_by_synapse_count(
        pre, post, dist, np.random.default_rng(0)
    )
    assert exp_pre.size == 2
    assert sorted(zip(exp_pre.tolist(), exp_post.tolist(), strict=True)) == [(5, 7), (6, 8)]


def test_expand_by_synapse_count_empty():
    empty = np.empty(0, dtype=np.int64)
    dist = IntConstantDistribution(value=5)
    exp_pre, exp_post = CircuitRewiringTask._expand_by_synapse_count(
        empty, empty, dist, np.random.default_rng(0)
    )
    assert exp_pre.size == 0
    assert exp_post.size == 0


# --------------------------------------------------------------------------------------------
# Full-task integration tests.
# --------------------------------------------------------------------------------------------


def _build_scan_config(
    *,
    conn_model,
    edge_population_name: str,
    seed: int,
    synapses_per_connection: int = 1,
    source_set=None,
    target_set=None,
    locations_block=None,
    synaptic_model=None,
    circuit_path=CIRCUIT_PATH,
    set_block_neuron_set: bool = True,
) -> CircuitRewiringScanConfig:
    circuit = OBICircuit(name="tiny", path=str(circuit_path))

    config = CircuitRewiringScanConfig.empty_config()
    config.set(Info(campaign_name="Rewire", campaign_description="Rewire campaign"), name="info")

    source_set = source_set if source_set is not None else AllBiophysicalNeurons()
    target_set = target_set if target_set is not None else AllBiophysicalNeurons()
    locations_block = (
        locations_block
        if locations_block is not None
        else RandomMorphologyLocations(section_types=(3, 4))
    )
    config.add(source_set, name="Sources")
    config.add(target_set, name="Targets")
    config.add(conn_model, name="Model")
    if set_block_neuron_set:
        # The target neurons of a pathway are the neuron set of its morphology locations block.
        locations_block = locations_block.model_copy(update={"neuron_set": target_set.ref})
    config.add(locations_block, name="Locations")
    synaptic_model = (
        synaptic_model if synaptic_model is not None else ExcitatoryTsodyksMarkramSynapticModel()
    )
    config.add(synaptic_model, name="SynapticModel")

    synapse_count = IntConstantDistribution(value=synapses_per_connection)
    config.add(synapse_count, name="SynapsesPerConnection")

    pathway = CircuitConnectivityPathway(
        source_neuron_set=source_set.ref,
        conn_model=conn_model.ref,
        synapses_per_connection=synapse_count.ref,
        synaptic_model=synaptic_model.ref,
        morphology_locations=locations_block.ref,
    )
    config.pathways["MainPathway"] = pathway

    init = CircuitRewiringScanConfig.Initialize(
        circuit=circuit,
        edge_population_name=edge_population_name,
        seed=seed,
    )
    config.set(init, name="initialize")
    return config.validated_config()


def _run(config: CircuitRewiringScanConfig, scan_path) -> list:
    grid_scan = GridScanGenerationTask(
        form=config,
        output_root=scan_path,
        coordinate_directory_option="ZERO_INDEX",
    )
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)
    return grid_scan.single_configs


def test_rewiring_erdos_renyi_full_probability_no_self_connections(tmp_path):
    """Probability 1.0 connects every ordered source/target pair except self-connections."""
    config = _build_scan_config(
        conn_model=ErdosRenyiConnModel(connection_probability=1.0, allow_self_connections=False),
        edge_population_name="rewired",
        seed=0,
    )
    (instance,) = _run(config, tmp_path / "scan")

    circuit_path = tmp_path / "scan" / str(instance.idx) / "SONATA" / "circuit_config.json"
    c = Circuit(circuit_path)

    assert "rewired" in c.edges.population_names
    edges = c.edges["rewired"]
    n = c.nodes[BIOPHYSICAL_POPULATION].size
    assert edges.size == n * (n - 1)
    assert edges.source.name == BIOPHYSICAL_POPULATION
    assert edges.target.name == BIOPHYSICAL_POPULATION

    conns = edges.get(edges.ids(), properties=["@source_node", "@target_node"])
    assert (conns["@source_node"] != conns["@target_node"]).all()

    # The only edge properties are the location columns and the synaptic parameters.
    assert _user_edge_properties(edges) == ALL_EDGE_COLUMNS


def test_rewiring_multiple_synapses_per_connection(tmp_path):
    """synapses_per_connection = k places k identical edges for every drawn connection."""
    k = 4
    config = _build_scan_config(
        conn_model=ErdosRenyiConnModel(connection_probability=1.0, allow_self_connections=False),
        edge_population_name="rewired",
        seed=0,
        synapses_per_connection=k,
    )
    (instance,) = _run(config, tmp_path / "scan")

    circuit_path = tmp_path / "scan" / str(instance.idx) / "SONATA" / "circuit_config.json"
    c = Circuit(circuit_path)
    edges = c.edges["rewired"]
    n = c.nodes[BIOPHYSICAL_POPULATION].size
    # Full connectivity without self-connections, each connection replicated k times.
    assert edges.size == k * n * (n - 1)

    # Every connected pair is present exactly k times.
    conns = edges.get(edges.ids(), properties=["@source_node", "@target_node"])
    pair_counts = conns.groupby(["@source_node", "@target_node"]).size()
    assert (pair_counts == k).all()
    assert pair_counts.shape[0] == n * (n - 1)


def test_rewiring_erdos_renyi_full_probability_with_self_connections(tmp_path):
    """Allowing self-connections yields the full n * n ordered pairs."""
    config = _build_scan_config(
        conn_model=ErdosRenyiConnModel(connection_probability=1.0, allow_self_connections=True),
        edge_population_name="rewired",
        seed=0,
    )
    (instance,) = _run(config, tmp_path / "scan")

    circuit_path = tmp_path / "scan" / str(instance.idx) / "SONATA" / "circuit_config.json"
    c = Circuit(circuit_path)
    edges = c.edges["rewired"]
    n = c.nodes[BIOPHYSICAL_POPULATION].size
    assert edges.size == n * n


def test_rewiring_distance_dependent(tmp_path):
    """A distance-dependent model wires the biophysical population using its x/y/z positions."""
    config = _build_scan_config(
        conn_model=DistanceDependentConnModel(scale_factor=1.0, length_scale=1.0e9),
        edge_population_name="rewired",
        seed=0,
    )
    (instance,) = _run(config, tmp_path / "scan")

    circuit_path = tmp_path / "scan" / str(instance.idx) / "SONATA" / "circuit_config.json"
    c = Circuit(circuit_path)
    edges = c.edges["rewired"]
    n = c.nodes[BIOPHYSICAL_POPULATION].size
    # With a length scale far larger than any pairwise distance, P ~ 1 everywhere, so the
    # result is (essentially) full connectivity without self-connections.
    assert edges.size == n * (n - 1)


def test_rewiring_preserves_existing_edge_populations(tmp_path):
    """The original edge populations are left intact alongside the new one."""
    config = _build_scan_config(
        conn_model=ErdosRenyiConnModel(connection_probability=1.0),
        edge_population_name="rewired",
        seed=0,
    )
    (instance,) = _run(config, tmp_path / "scan")

    original = Circuit(str(CIRCUIT_PATH))
    result = Circuit(tmp_path / "scan" / str(instance.idx) / "SONATA" / "circuit_config.json")
    for edge_population in original.edges.population_names:
        assert edge_population in result.edges.population_names
    assert "rewired" in result.edges.population_names


def test_rewiring_zero_probability_raises(tmp_path):
    """A zero connection probability generates no edges and raises rather than registering."""
    config = _build_scan_config(
        conn_model=ErdosRenyiConnModel(connection_probability=0.0),
        edge_population_name="rewired",
        seed=0,
    )
    with pytest.raises(OBIONEError, match="No connections were generated"):
        _run(config, tmp_path / "scan")


def test_rewiring_duplicate_population_name_raises(tmp_path):
    """Reusing an existing edge population name is rejected."""
    config = _build_scan_config(
        conn_model=ErdosRenyiConnModel(connection_probability=1.0),
        edge_population_name="S1nonbarrel_neurons__S1nonbarrel_neurons__chemical",
        seed=0,
    )
    with pytest.raises(OBIONEError, match="already exists in the circuit"):
        _run(config, tmp_path / "scan")


VIRTUAL_POPULATION = "VPM"


def test_rewiring_virtual_source_to_biophysical_target(tmp_path):
    """A virtual neuron set is allowed as the source (e.g. a feedforward input projection)."""
    config = _build_scan_config(
        conn_model=ErdosRenyiConnModel(connection_probability=1.0),
        edge_population_name="rewired",
        seed=0,
        source_set=VirtualPopulationNeuronSet(population=VIRTUAL_POPULATION),
        target_set=AllBiophysicalNeurons(),
    )
    (instance,) = _run(config, tmp_path / "scan")

    circuit_path = tmp_path / "scan" / str(instance.idx) / "SONATA" / "circuit_config.json"
    c = Circuit(circuit_path)
    edges = c.edges["rewired"]
    assert edges.source.name == VIRTUAL_POPULATION
    assert edges.source.type == "virtual"
    assert edges.target.name == BIOPHYSICAL_POPULATION
    # Full connectivity between distinct populations: n_source * n_target (no self-connections).
    n_source = c.nodes[VIRTUAL_POPULATION].size
    n_target = c.nodes[BIOPHYSICAL_POPULATION].size
    assert edges.size == n_source * n_target


def test_rewiring_rejects_virtual_target():
    """A virtual neuron set is rejected as the target at config validation time."""
    with pytest.raises(pydantic.ValidationError):
        _build_scan_config(
            conn_model=ErdosRenyiConnModel(connection_probability=1.0),
            edge_population_name="rewired",
            seed=0,
            source_set=AllBiophysicalNeurons(),
            target_set=VirtualPopulationNeuronSet(population=VIRTUAL_POPULATION),
        )


# --------------------------------------------------------------------------------------------
# SGSG connectivity model (requires connalysis).
# --------------------------------------------------------------------------------------------


@requires_connalysis
def test_sgsg_same_population_produces_valid_connections():
    rng = np.random.default_rng(0)
    ids = np.arange(40, dtype=np.int64)
    positions = rng.random((40, 3)) * 100.0
    ctx = PathwayConnContext(
        source_ids=ids,
        target_ids=ids,
        source_positions=positions,
        target_positions=positions,
        same_population=True,
    )
    model = SgsgConnModel(n_neighbors=10, n_pick=5, n_protected=1, q=5.0, decay=0.9)
    pre, post = model.draw_connections(ctx, np.random.default_rng(1))
    assert pre.size == post.size
    assert pre.size > 0
    assert (pre != post).all()  # allow_self_connections defaults to False
    assert set(pre.tolist()) <= set(ids.tolist())
    assert set(post.tolist()) <= set(ids.tolist())


@requires_connalysis
def test_sgsg_is_reproducible_for_a_given_seed():
    rng = np.random.default_rng(0)
    ids = np.arange(40, dtype=np.int64)
    positions = rng.random((40, 3)) * 100.0
    ctx = PathwayConnContext(
        source_ids=ids,
        target_ids=ids,
        source_positions=positions,
        target_positions=positions,
        same_population=True,
    )
    model = SgsgConnModel(n_neighbors=10, n_pick=5, n_protected=1, q=5.0, decay=0.9)
    pre_a, post_a = model.draw_connections(ctx, np.random.default_rng(42))
    pre_b, post_b = model.draw_connections(ctx, np.random.default_rng(42))
    assert np.array_equal(pre_a, pre_b)
    assert np.array_equal(post_a, post_b)


@requires_connalysis
def test_sgsg_cross_population_keeps_source_and_target_ids_separate():
    rng = np.random.default_rng(0)
    src_ids = np.arange(25, dtype=np.int64)
    tgt_ids = np.arange(15, dtype=np.int64) + 100
    ctx = PathwayConnContext(
        source_ids=src_ids,
        target_ids=tgt_ids,
        source_positions=rng.random((25, 3)) * 100.0,
        target_positions=rng.random((15, 3)) * 100.0,
        same_population=False,
    )
    model = SgsgConnModel(n_neighbors=8, n_pick=4, n_protected=1, q=4.0, decay=0.9)
    pre, post = model.draw_connections(ctx, np.random.default_rng(3))
    assert set(pre.tolist()) <= set(src_ids.tolist())
    assert set(post.tolist()) <= set(tgt_ids.tolist())


@requires_connalysis
def test_sgsg_requires_positions():
    ids = np.arange(5, dtype=np.int64)
    ctx = PathwayConnContext(
        source_ids=ids,
        target_ids=ids,
        source_positions=None,
        target_positions=None,
        same_population=True,
    )
    model = SgsgConnModel(n_neighbors=3, n_pick=2)
    with pytest.raises(OBIONEError, match="requires x/y/z positions"):
        model.draw_connections(ctx, np.random.default_rng(0))


@requires_connalysis
def test_rewiring_sgsg_end_to_end(tmp_path):
    """SgsgConnModel wires the biophysical population through the full task."""
    config = _build_scan_config(
        conn_model=SgsgConnModel(n_neighbors=5, n_pick=3, n_protected=1, q=3.0, decay=0.9),
        edge_population_name="rewired",
        seed=0,
    )
    (instance,) = _run(config, tmp_path / "scan")

    circuit_path = tmp_path / "scan" / str(instance.idx) / "SONATA" / "circuit_config.json"
    c = Circuit(circuit_path)
    assert "rewired" in c.edges.population_names
    edges = c.edges["rewired"]
    assert edges.source.name == BIOPHYSICAL_POPULATION
    assert edges.target.name == BIOPHYSICAL_POPULATION
    # The only edge properties are the location columns and the synaptic parameters.
    assert _user_edge_properties(edges) == ALL_EDGE_COLUMNS


# --------------------------------------------------------------------------------------------
# Postsynaptic morphology locations reference.
# --------------------------------------------------------------------------------------------


def _union_member_names(union) -> set[str]:
    return {t.__name__ for t in get_args(get_args(union)[0])}


def test_morphology_locations_union_excludes_explicit_and_grouped():
    names = _union_member_names(NonGroupedMorphologyLocationUnion)
    assert names == {
        "ClusteredMorphologyLocations",
        "ClusteredPathDistanceMorphologyLocations",
        "PathDistanceMorphologyLocations",
        "RandomMorphologyLocations",
    }
    allowed = set(NonGroupedMorphologyLocationsReference.model_json_schema()["allowed_block_types"])
    assert allowed == names


def _config_with_locations(locations_block) -> CircuitRewiringScanConfig:
    config = CircuitRewiringScanConfig.empty_config()
    config.set(Info(campaign_name="Rewire", campaign_description="Rewire campaign"), name="info")
    config.set(
        CircuitRewiringScanConfig.Initialize(
            circuit=OBICircuit(name="tiny", path=str(CIRCUIT_PATH))
        ),
        name="initialize",
    )
    source_set = AllBiophysicalNeurons()
    target_set = AllBiophysicalNeurons()
    config.add(source_set, name="Sources")
    config.add(target_set, name="Targets")
    model = ErdosRenyiConnModel(connection_probability=0.5)
    config.add(model, name="Model")
    synapse_count = IntConstantDistribution(value=1)
    config.add(synapse_count, name="SynapsesPerConnection")
    locations_block = locations_block.model_copy(update={"neuron_set": target_set.ref})
    config.add(locations_block, name="Locations")
    synaptic_model = ExcitatoryTsodyksMarkramSynapticModel()
    config.add(synaptic_model, name="SynapticModel")
    config.pathways["P"] = CircuitConnectivityPathway(
        source_neuron_set=source_set.ref,
        conn_model=model.ref,
        synapses_per_connection=synapse_count.ref,
        synaptic_model=synaptic_model.ref,
        morphology_locations=locations_block.ref,
    )
    return config.validated_config()


@pytest.mark.parametrize(
    "locations_block",
    [
        RandomMorphologyLocations(section_types=(3, 4), number_of_locations=5),
        PathDistanceMorphologyLocations(section_types=(3, 4), number_of_locations=4),
        ClusteredMorphologyLocations(section_types=(3, 4), number_of_locations=6),
        ClusteredPathDistanceMorphologyLocations(section_types=(3, 4), number_of_locations=6),
    ],
    ids=lambda b: type(b).__name__,
)
def test_pathway_accepts_allowed_morphology_locations_and_round_trips(locations_block):
    config = _config_with_locations(locations_block)
    reloaded = CircuitRewiringScanConfig.model_validate_json(config.model_dump_json())
    resolved = reloaded.pathways["P"].morphology_locations.block
    assert type(resolved) is type(locations_block)


def test_pathway_morphology_locations_is_required():
    assert CircuitConnectivityPathway.model_fields["morphology_locations"].is_required()


@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings:UserWarning")
@pytest.mark.parametrize(
    "locations_block",
    [
        ExplicitMorphologyLocations(locations=(MorphologyLocationPoint(section_id=1, offset=0.5),)),
        RandomGroupedMorphologyLocations(section_types=(3, 4), number_of_locations=6, n_groups=2),
        ClusteredGroupedMorphologyLocations(
            section_types=(3, 4), number_of_locations=6, n_groups=2
        ),
    ],
    ids=lambda b: type(b).__name__,
)
def test_config_rejects_explicit_and_grouped_morphology_locations(locations_block):
    config = CircuitRewiringScanConfig.empty_config()
    config.morphology_locations["Locations"] = locations_block
    with pytest.raises(pydantic.ValidationError):
        config.validated_config()


# --------------------------------------------------------------------------------------------
# Postsynaptic locations written to the edge population.
# --------------------------------------------------------------------------------------------


def _location_table(circuit_path):
    """Read the new edge population's target ids and location columns."""
    c = Circuit(circuit_path)
    edges = c.edges["rewired"]
    return edges.get(
        edges.ids(), properties=["@target_node", "@source_node", *sorted(AFFERENT_COLUMNS)]
    )


def _run_er_with_locations(tmp_path, locations_block, *, name="scan", synapses=1):
    config = _build_scan_config(
        conn_model=ErdosRenyiConnModel(connection_probability=1.0),
        edge_population_name="rewired",
        seed=0,
        synapses_per_connection=synapses,
        locations_block=locations_block,
    )
    (instance,) = _run(config, tmp_path / name)
    return tmp_path / name / str(instance.idx) / "SONATA" / "circuit_config.json"


def test_rewiring_writes_valid_postsynaptic_locations(tmp_path):
    circuit_path = _run_er_with_locations(
        tmp_path, RandomMorphologyLocations(section_types=(3, 4), random_seed=3)
    )
    table = _location_table(circuit_path)
    assert not table[sorted(AFFERENT_COLUMNS)].isna().any().any()
    assert (table["afferent_section_id"] >= 1).all()  # soma locations are not generated
    assert table["afferent_section_type"].isin([3, 4]).all()
    assert (table["afferent_segment_offset"] >= 0).all()
    assert table["afferent_section_pos"].between(0.0, 1.0).all()
    # Every target neuron receives several edges, and they sit at different locations.
    distinct = table.groupby("@target_node")[
        ["afferent_section_id", "afferent_segment_id", "afferent_segment_offset"]
    ].apply(lambda g: len(g.drop_duplicates()))
    assert (distinct > 1).all()


def test_rewiring_locations_are_reproducible_and_seed_dependent(tmp_path):
    first = _location_table(
        _run_er_with_locations(
            tmp_path, RandomMorphologyLocations(section_types=(3, 4), random_seed=1), name="a"
        )
    )
    again = _location_table(
        _run_er_with_locations(
            tmp_path, RandomMorphologyLocations(section_types=(3, 4), random_seed=1), name="b"
        )
    )
    other = _location_table(
        _run_er_with_locations(
            tmp_path, RandomMorphologyLocations(section_types=(3, 4), random_seed=2), name="c"
        )
    )
    columns = sorted(AFFERENT_COLUMNS)
    assert first[columns].equals(again[columns])
    assert not first[columns].equals(other[columns])


@pytest.mark.parametrize(
    "locations_block",
    [
        PathDistanceMorphologyLocations(section_types=(3, 4)),
        ClusteredMorphologyLocations(section_types=(3, 4)),
        ClusteredPathDistanceMorphologyLocations(section_types=(3, 4)),
    ],
    ids=lambda b: type(b).__name__,
)
def test_rewiring_supports_other_location_blocks(tmp_path, locations_block):
    table = _location_table(_run_er_with_locations(tmp_path, locations_block))
    assert len(table) == 10 * 9
    assert not table[sorted(AFFERENT_COLUMNS)].isna().any().any()


def test_rewiring_locations_cover_every_synapse(tmp_path):
    """Multiple synapses per connection each get their own location."""
    table = _location_table(
        _run_er_with_locations(
            tmp_path, RandomMorphologyLocations(section_types=(3, 4)), synapses=3
        )
    )
    assert len(table) == 3 * 10 * 9
    assert not table[sorted(AFFERENT_COLUMNS)].isna().any().any()


def test_rewiring_rejects_non_biophysical_target():
    """Point-neuron targets have no morphology, so they are rejected as targets."""
    with pytest.raises(pydantic.ValidationError):
        _build_scan_config(
            conn_model=ErdosRenyiConnModel(connection_probability=1.0),
            edge_population_name="rewired",
            seed=0,
            source_set=PointPopulationNeuronSet(population="drosophila"),
            target_set=PointPopulationNeuronSet(population="drosophila"),
            circuit_path=POINT_CIRCUIT_PATH,
        )


def test_rewiring_requires_neuron_set_in_morphology_locations():
    """The morphology locations block defines the target, so its neuron set is required."""
    with pytest.raises(pydantic.ValidationError, match="must specify a neuron set"):
        _build_scan_config(
            conn_model=ErdosRenyiConnModel(connection_probability=1.0),
            edge_population_name="rewired",
            seed=0,
            set_block_neuron_set=False,
        )


def test_rewiring_targets_are_the_morphology_locations_neuron_set(tmp_path):
    """Only neurons of the block's neuron set receive connections."""
    target_set = BiophysicalPopulationNeuronSet(
        population=BIOPHYSICAL_POPULATION, sample_percentage=50.0, sample_seed=1
    )
    expected_targets = set(
        target_set.get_neuron_ids(OBICircuit(name="tiny", path=str(CIRCUIT_PATH)))[
            BIOPHYSICAL_POPULATION
        ]
    )
    assert 0 < len(expected_targets) < 10

    config = _build_scan_config(
        conn_model=ErdosRenyiConnModel(connection_probability=1.0),
        edge_population_name="rewired",
        seed=0,
        target_set=target_set,
    )
    (instance,) = _run(config, tmp_path / "scan")
    circuit_path = tmp_path / "scan" / str(instance.idx) / "SONATA" / "circuit_config.json"
    table = _location_table(circuit_path)
    assert set(table["@target_node"]) == expected_targets
    # Every source except the target itself connects to each target (p=1, no self-connections).
    assert len(table) == len(expected_targets) * (10 - 1)


# --------------------------------------------------------------------------------------------
# Synaptic model: physiological parameters of the new edge population.
# --------------------------------------------------------------------------------------------


def _edge_table(circuit_path, columns):
    c = Circuit(circuit_path)
    edges = c.edges["rewired"]
    return edges.get(edges.ids(), properties=["@source_node", "@target_node", *sorted(columns)])


def _run_er(tmp_path, *, name="scan", seed=0, synaptic_model=None, synapses=1):
    config = _build_scan_config(
        conn_model=ErdosRenyiConnModel(connection_probability=1.0),
        edge_population_name="rewired",
        seed=seed,
        synapses_per_connection=synapses,
        synaptic_model=synaptic_model,
    )
    (instance,) = _run(config, tmp_path / name)
    return tmp_path / name / str(instance.idx) / "SONATA" / "circuit_config.json"


def test_pathway_synaptic_model_is_required():
    assert CircuitConnectivityPathway.model_fields["synaptic_model"].is_required()


def test_rewiring_writes_synaptic_parameters(tmp_path):
    table = _edge_table(_run_er(tmp_path), SYNAPSE_PARAMETER_COLUMNS)
    columns = sorted(SYNAPSE_PARAMETER_COLUMNS)
    assert len(table) == 10 * 9
    assert not table[columns].isna().any().any()
    excitatory = ExcitatoryTsodyksMarkramSynapticModel()
    assert (table["syn_type_id"] == excitatory.syn_type_id).all()
    # Parameters are drawn from distributions, so they differ between synapses.
    varying = [c for c in columns if c != "syn_type_id" and table[c].nunique() > 1]
    assert varying


def test_rewiring_uses_the_pathways_synaptic_model(tmp_path):
    table = _edge_table(
        _run_er(tmp_path, synaptic_model=InhibitoryTsodyksMarkramSynapticModel()),
        SYNAPSE_PARAMETER_COLUMNS,
    )
    inhibitory = InhibitoryTsodyksMarkramSynapticModel()
    assert inhibitory.syn_type_id != ExcitatoryTsodyksMarkramSynapticModel().syn_type_id
    assert (table["syn_type_id"] == inhibitory.syn_type_id).all()


def test_rewiring_synaptic_parameters_are_reproducible_and_seed_dependent(tmp_path):
    columns = sorted(SYNAPSE_PARAMETER_COLUMNS)
    first = _edge_table(_run_er(tmp_path, name="a", seed=1), columns)[columns]
    again = _edge_table(_run_er(tmp_path, name="b", seed=1), columns)[columns]
    other = _edge_table(_run_er(tmp_path, name="c", seed=2), columns)[columns]
    assert first.equals(again)
    assert not first.equals(other)


def test_rewiring_samples_each_synapse_of_a_connection_separately(tmp_path):
    table = _edge_table(_run_er(tmp_path, synapses=3), SYNAPSE_PARAMETER_COLUMNS)
    assert len(table) == 3 * 10 * 9
    columns = [c for c in sorted(SYNAPSE_PARAMETER_COLUMNS) if c != "syn_type_id"]
    per_connection = table.groupby(["@source_node", "@target_node"])[columns].nunique()
    # The three synapses of a connection do not all share their parameter values.
    assert (per_connection.max(axis=1) > 1).all()


@pytest.mark.parametrize(
    ("synaptic_model", "mod_file"),
    [
        (ExcitatoryTsodyksMarkramSynapticModel(), "ProbAMPANMDA_EMS.mod"),
        (InhibitoryTsodyksMarkramSynapticModel(), "ProbGABAAB_EMS.mod"),
    ],
    ids=["excitatory", "inhibitory"],
)
def test_rewiring_copies_the_mechanism_files_of_the_synaptic_model(
    tmp_path, synaptic_model, mod_file
):
    circuit_path = _run_er(tmp_path, synaptic_model=synaptic_model)
    properties = libsonata.CircuitConfig.from_file(str(circuit_path)).edge_population_properties(
        "rewired"
    )
    assert (Path(properties.mechanisms_dir) / mod_file).exists()


def test_rewiring_two_pathways_with_different_synaptic_models_share_a_population(tmp_path):
    config = CircuitRewiringScanConfig.empty_config()
    config.set(Info(campaign_name="Rewire", campaign_description="Rewire campaign"), name="info")
    config.set(
        CircuitRewiringScanConfig.Initialize(
            circuit=OBICircuit(name="tiny", path=str(CIRCUIT_PATH)),
            edge_population_name="rewired",
        ),
        name="initialize",
    )
    sources = AllBiophysicalNeurons()
    targets = AllBiophysicalNeurons()
    config.add(sources, name="Sources")
    config.add(targets, name="Targets")
    synapse_count = IntConstantDistribution(value=1)
    config.add(synapse_count, name="Count")
    for name, model in (
        ("Exc", ExcitatoryTsodyksMarkramSynapticModel()),
        ("Inh", InhibitoryTsodyksMarkramSynapticModel()),
    ):
        conn_model = ErdosRenyiConnModel(connection_probability=0.5)
        locations = RandomMorphologyLocations(section_types=(3, 4)).model_copy(
            update={"neuron_set": targets.ref}
        )
        config.add(conn_model, name=f"Conn{name}")
        config.add(model, name=f"Syn{name}")
        config.add(locations, name=f"Loc{name}")
        config.pathways[name] = CircuitConnectivityPathway(
            source_neuron_set=sources.ref,
            conn_model=conn_model.ref,
            synapses_per_connection=synapse_count.ref,
            synaptic_model=model.ref,
            morphology_locations=locations.ref,
        )
    (instance,) = _run(config.validated_config(), tmp_path / "scan")
    circuit_path = tmp_path / "scan" / str(instance.idx) / "SONATA" / "circuit_config.json"

    table = _edge_table(circuit_path, SYNAPSE_PARAMETER_COLUMNS)
    assert not table[sorted(SYNAPSE_PARAMETER_COLUMNS)].isna().any().any()
    assert set(table["syn_type_id"]) == {
        ExcitatoryTsodyksMarkramSynapticModel().syn_type_id,
        InhibitoryTsodyksMarkramSynapticModel().syn_type_id,
    }
    properties = libsonata.CircuitConfig.from_file(str(circuit_path)).edge_population_properties(
        "rewired"
    )
    for mod_file in ("ProbAMPANMDA_EMS.mod", "ProbGABAAB_EMS.mod"):
        assert (Path(properties.mechanisms_dir) / mod_file).exists()


def test_rewiring_rejects_synaptic_models_for_other_edge_population_types(monkeypatch):
    monkeypatch.setattr(
        ExcitatoryTsodyksMarkramSynapticModel,
        "_compatible_edge_population_types",
        ("Exp2Syn_synapse",),
    )
    with pytest.raises(OBIONEError, match="can only be assigned to edge populations"):
        CircuitRewiringTask._check_synaptic_model("P", ExcitatoryTsodyksMarkramSynapticModel())


def test_rewiring_rejects_incompatible_synaptic_models_in_one_population(monkeypatch):
    monkeypatch.setattr(InhibitoryTsodyksMarkramSynapticModel, "_synapse_model_family", "Other")
    with pytest.raises(OBIONEError, match="incompatible synaptic models"):
        CircuitRewiringTask._check_consistent_synaptic_models(
            "P",
            ("pop", "pop"),
            [ExcitatoryTsodyksMarkramSynapticModel()],
            InhibitoryTsodyksMarkramSynapticModel(),
        )
