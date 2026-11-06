"""Tests for the circuit rewiring task and its structural connectivity models.

The task stages a SONATA circuit, draws a new connectivity-only edge population from
user-specified source/target neuron sets and a per-pathway structural connectivity model, and
registers the new edge population in ``circuit_config.json``. These tests exercise the full
local (no database) execution path against a tiny biophysical circuit, plus unit tests for the
connectivity models themselves.
"""

import importlib.util

import numpy as np
import pydantic
import pytest
from bluepysnap import Circuit

from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.blocks.distributions.constant import IntConstantDistribution
from obi_one.scientific.blocks.neuron_sets.population import VirtualPopulationNeuronSet
from obi_one.scientific.blocks.neuron_sets.specific import AllBiophysicalNeurons
from obi_one.scientific.blocks.structural_conn_models.base import PathwayConnContext
from obi_one.scientific.blocks.structural_conn_models.distance_dependent import (
    DistanceDependentConnModel,
)
from obi_one.scientific.blocks.structural_conn_models.erdos_renyi import ErdosRenyiConnModel
from obi_one.scientific.blocks.structural_conn_models.sgsg import SgsgConnModel
from obi_one.scientific.library.circuit import Circuit as OBICircuit
from obi_one.scientific.tasks.circuit_rewiring import CircuitRewiringScanConfig
from obi_one.scientific.tasks.circuit_rewiring.config import CircuitConnectivityPathway
from obi_one.scientific.tasks.circuit_rewiring.task import CircuitRewiringTask

from tests.utils import CIRCUIT_DIR

CIRCUIT_PATH = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"
BIOPHYSICAL_POPULATION = "S1nonbarrel_neurons"

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
) -> CircuitRewiringScanConfig:
    circuit = OBICircuit(name="tiny", path=str(CIRCUIT_PATH))

    config = CircuitRewiringScanConfig.empty_config()
    config.set(Info(campaign_name="Rewire", campaign_description="Rewire campaign"), name="info")

    source_set = source_set if source_set is not None else AllBiophysicalNeurons()
    target_set = target_set if target_set is not None else AllBiophysicalNeurons()
    config.add(source_set, name="Sources")
    config.add(target_set, name="Targets")
    config.add(conn_model, name="Model")

    synapse_count = IntConstantDistribution(value=synapses_per_connection)
    config.add(synapse_count, name="SynapsesPerConnection")

    pathway = CircuitConnectivityPathway(
        source_neuron_set=source_set.ref,
        target_neuron_set=target_set.ref,
        conn_model=conn_model.ref,
        synapses_per_connection=synapse_count.ref,
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

    # Connectivity only: the new population carries no user-facing edge properties.
    assert [p for p in edges.property_names if not p.startswith("@")] == []


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
    # No per-edge properties: connectivity only.
    assert [p for p in edges.property_names if not p.startswith("@")] == []
