import json

import bluepysnap
import numpy as np
import pandas as pd
import pytest

from obi_one.scientific.tasks.point_neuron_circuit_from_em.brian2_sonata import (
    POINT_POPULATION,
    VIRTUAL_POPULATION,
    W_SYN_MV,
    write_brian2_sonata_circuit,
)
from obi_one.scientific.tasks.point_neuron_circuit_from_em.connectivity import (
    EdgeSet,
    ResolvedConnectivity,
)
from obi_one.utils.circuit import run_validation


def _connectivity(*, with_virtual=True):
    point_pt_root_ids = [111, 222, 333]
    internal = EdgeSet(
        source_node_id=np.array([1, 0], dtype=np.uint32),
        target_node_id=np.array([0, 2], dtype=np.uint32),
        synapse_count=np.array([2, 1], dtype=np.int64),
    )
    if with_virtual:
        virtual_pt_root_ids = [888, 999]
        external = EdgeSet(
            source_node_id=np.array([0, 1], dtype=np.uint32),
            target_node_id=np.array([0, 1], dtype=np.uint32),
            synapse_count=np.array([3, 5], dtype=np.int64),
        )
    else:
        virtual_pt_root_ids = []
        external = EdgeSet(
            source_node_id=np.array([], dtype=np.uint32),
            target_node_id=np.array([], dtype=np.uint32),
            synapse_count=np.array([], dtype=np.int64),
        )
    matrix = pd.DataFrame(
        np.zeros((3, 3), dtype=np.int64),
        index=pd.Index(point_pt_root_ids, name="pre_pt_root_id"),
        columns=pd.Index(point_pt_root_ids, name="post_pt_root_id"),
    )
    summary = pd.DataFrame({"pt_root_id": point_pt_root_ids}).set_index("pt_root_id")
    return ResolvedConnectivity(
        point_pt_root_ids=point_pt_root_ids,
        virtual_pt_root_ids=virtual_pt_root_ids,
        internal_edges=internal,
        external_edges=external,
        internal_matrix=matrix,
        neuron_summary=summary,
    )


class TestWriteBrian2SonataCircuit:
    def test_writes_loadable_circuit_with_virtual_population(self, tmp_path):
        config_path = write_brian2_sonata_circuit(tmp_path, _connectivity(with_virtual=True))

        assert config_path.exists()
        assert (tmp_path / "nodes.h5").exists()
        assert (tmp_path / "edges.h5").exists()
        assert (tmp_path / "models" / "point_neuron.json").exists()
        assert (tmp_path / "models" / "virtual_neuron.json").exists()
        assert (tmp_path / "models" / "synapse.json").exists()
        assert (tmp_path / "node_sets.json").exists()

        circuit = bluepysnap.Circuit(str(config_path))
        assert set(circuit.nodes.population_names) == {POINT_POPULATION, VIRTUAL_POPULATION}
        assert circuit.nodes[POINT_POPULATION].size == 3
        assert circuit.nodes[VIRTUAL_POPULATION].size == 2
        assert circuit.nodes[VIRTUAL_POPULATION].type == "virtual"
        assert circuit.nodes[POINT_POPULATION].get(
            properties="model_template"
        ).unique().tolist() == ["json:point_neuron"]
        assert circuit.nodes[VIRTUAL_POPULATION].get(
            properties="model_template"
        ).unique().tolist() == ["json:virtual_neuron"]

        internal_name = f"{POINT_POPULATION}__{POINT_POPULATION}__brian2_synapse"
        external_name = f"{VIRTUAL_POPULATION}__{POINT_POPULATION}__brian2_synapse"
        assert set(circuit.edges.population_names) == {internal_name, external_name}

        external = circuit.edges[external_name].to_libsonata
        weights = sorted(external.get_attribute("w", external.select_all()).tolist())
        assert weights == pytest.approx(sorted([3 * W_SYN_MV, 5 * W_SYN_MV]))

        assert circuit.to_libsonata.node_population_properties(POINT_POPULATION).type == (
            "brian2_point"
        )

    def test_written_circuit_passes_sonata_validation(self, tmp_path):
        # Guards against e.g. the virtual population missing the required model_template property.
        config_path = write_brian2_sonata_circuit(tmp_path, _connectivity(with_virtual=True))
        try:
            run_validation(config_path)
        except FileNotFoundError as exc:  # bluepysnap build without brian2 SONATA schemas
            pytest.skip(f"bluepysnap lacks brian2 SONATA schemas: {exc}")

    def test_inhibitory_fraction_gives_negative_weights(self, tmp_path):
        n = 10
        pts = list(range(100, 100 + n))
        # One internal edge from each neuron i -> (i + 1) % n.
        internal = EdgeSet(
            source_node_id=np.arange(n, dtype=np.uint32),
            target_node_id=((np.arange(n) + 1) % n).astype(np.uint32),
            synapse_count=np.full(n, 2, dtype=np.int64),
        )
        empty = EdgeSet(
            np.array([], dtype=np.uint32),
            np.array([], dtype=np.uint32),
            np.array([], dtype=np.int64),
        )
        connectivity = ResolvedConnectivity(
            point_pt_root_ids=pts,
            virtual_pt_root_ids=[],
            internal_edges=internal,
            external_edges=empty,
            internal_matrix=pd.DataFrame(
                np.zeros((n, n), dtype=np.int64), index=pd.Index(pts), columns=pd.Index(pts)
            ),
            neuron_summary=pd.DataFrame({"pt_root_id": pts}).set_index("pt_root_id"),
        )

        circuit = bluepysnap.Circuit(str(write_brian2_sonata_circuit(tmp_path, connectivity)))

        # Exactly 20% of the neurons are inhibitory.
        synapse_class = circuit.nodes[POINT_POPULATION].get(properties="synapse_class")
        assert (synapse_class == "INH").sum() == round(0.2 * n)

        # A synapse is negative iff its presynaptic neuron is inhibitory.
        internal_name = f"{POINT_POPULATION}__{POINT_POPULATION}__brian2_synapse"
        edges = circuit.edges[internal_name].to_libsonata
        selection = edges.select_all()
        weights = edges.get_attribute("w", selection)
        sources = edges.source_nodes(selection)
        inhibitory = {i for i in range(n) if synapse_class.iloc[i] == "INH"}
        for weight, source in zip(weights, sources, strict=True):
            assert (weight < 0) == (source in inhibitory)

    def test_writes_circuit_without_virtual_population(self, tmp_path):
        config_path = write_brian2_sonata_circuit(tmp_path, _connectivity(with_virtual=False))

        config = json.loads(config_path.read_text())
        node_pops = config["networks"]["nodes"][0]["populations"]
        assert POINT_POPULATION in node_pops
        assert VIRTUAL_POPULATION not in node_pops

        edge_pops = config["networks"]["edges"][0]["populations"]
        assert list(edge_pops) == [f"{POINT_POPULATION}__{POINT_POPULATION}__brian2_synapse"]

        # The circuit still loads (only the modelled population and internal edges).
        circuit = bluepysnap.Circuit(str(config_path))
        assert circuit.nodes.population_names == [POINT_POPULATION]
