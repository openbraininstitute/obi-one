import numpy as np

import obi_one as obi

from tests.utils import CIRCUIT_DIR, MATRIX_DIR


def test_pair_motif_neuron_set():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) Reciprocal pairs
    neuron1_filter = {"synapse_class": "EXC", "layer": "6"}  # First neuron A in pair
    neuron2_filter = {"synapse_class": "EXC", "layer": "6"}  # Second neuron B in pair

    conn_ff_filter = {"nsyn": {"gt": 0}}  # Feedforward connectivity from A->B
    conn_fb_filter = {"nsyn": {"gt": 0}}  # Feedback connectivity from B->A

    pair_selection = {}  # Select all pairs

    neuron_set = obi.PairMotifNeuronSet(
        neuron1_filter=neuron1_filter,
        neuron2_filter=neuron2_filter,
        conn_ff_filter=conn_ff_filter,
        conn_fb_filter=conn_fb_filter,
        pair_selection=pair_selection,
    )
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(neuron_set_ids, [1, 3, 4, 9])
    assert neuron_set_def["population"] == circuit.default_population_name
    np.testing.assert_array_equal(neuron_set_def["node_id"], [1, 3, 4, 9])

    # Check pair table
    df_pairs = neuron_set.get_pair_table(circuit, circuit.default_population_name)
    edges = circuit.sonata_circuit.edges[circuit.default_edge_population_name]
    for _, row in df_pairs.iterrows():
        nff = list(
            edges.iter_connections(source=row["nrn1"], target=row["nrn2"], return_edge_count=True)
        )
        nff = 0 if len(nff) == 0 else nff[0][-1]
        nfb = list(
            edges.iter_connections(source=row["nrn2"], target=row["nrn1"], return_edge_count=True)
        )
        nfb = 0 if len(nfb) == 0 else nfb[0][-1]
        assert row["nsyn_ff"] == nff
        assert row["nsyn_fb"] == nfb
        assert row["nsyn_all"] == nff + nfb
    assert np.all(np.isin(neuron_set_ids, df_pairs["nrn1"]))
    assert np.all(np.isin(neuron_set_ids, df_pairs["nrn2"]))
    assert np.all(df_pairs["is_rc"])

    # (b) Strongest non-reciprocal pair
    neuron1_filter = {"node_set": "Excitatory", "layer": "6"}
    neuron2_filter = {"node_set": "Excitatory", "layer": "6"}

    conn_ff_filter = {"nsyn": {"gt": 0}}
    conn_fb_filter = {"nsyn": 0}  # No feedback connection

    pair_selection = {
        "count": 1,
        "method": "max_nsyn_ff",
    }  # Selection based on max. number of synapses

    neuron_set = obi.PairMotifNeuronSet(
        neuron1_filter=neuron1_filter,
        neuron2_filter=neuron2_filter,
        conn_ff_filter=conn_ff_filter,
        conn_fb_filter=conn_fb_filter,
        pair_selection=pair_selection,
    )
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(neuron_set_ids, [6, 8])
    assert neuron_set_def["population"] == circuit.default_population_name
    np.testing.assert_array_equal(neuron_set_def["node_id"], [6, 8])

    # Check pair table
    df_pairs = neuron_set.get_pair_table(circuit, circuit.default_population_name)
    edges = circuit.sonata_circuit.edges[circuit.default_edge_population_name]
    assert df_pairs.shape[0] == 1  # Only one pair
    row = df_pairs.iloc[0]
    nff = list(
        edges.iter_connections(source=row["nrn1"], target=row["nrn2"], return_edge_count=True)
    )
    nff = 0 if len(nff) == 0 else nff[0][-1]
    nfb = list(
        edges.iter_connections(source=row["nrn2"], target=row["nrn1"], return_edge_count=True)
    )
    nfb = 0 if len(nfb) == 0 else nfb[0][-1]
    assert nfb == 0
    assert row["nsyn_ff"] == nff
    assert row["nsyn_fb"] == nfb
    assert row["nsyn_all"] == nff + nfb
    assert np.all(np.isin(neuron_set_ids, row[["nrn1", "nrn2"]]))
    assert not row["is_rc"]
