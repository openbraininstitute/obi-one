import json
import re
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

import obi_one as obi

from tests.utils import CIRCUIT_DIR, MATRIX_DIR


def test_add_and_write_node_sets(tmp_path):
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name, path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json")
    )
    c = circuit.sonata_circuit

    # Add a new node sets to the SONATA circuit
    obi.add_node_set_to_circuit(c, {"Layer23": {"layer": ["2", "3"]}})

    with pytest.raises(ValueError, match="Node set 'Layer23' already exists!"):
        # Add a node set with an exising name --> Must raise an error
        obi.add_node_set_to_circuit(c, {"Layer23": {"layer": ["2", "3"]}})

    # Update/overwrite an existing node set
    obi.add_node_set_to_circuit(c, {"Layer23": ["Layer2", "Layer3"]}, overwrite_if_exists=True)

    # Add multiple node sets
    obi.add_node_set_to_circuit(
        c, {"Layer45": ["Layer4", "Layer5"], "Layer56": ["Layer5", "Layer6"]}
    )

    # Add a node set from NeuronSet object, resolved in the circuit's default node population
    neuron_set = obi.CombinedNeuronSet(node_sets=("Layer1", "Layer2", "Layer3"))
    obi.add_node_set_to_circuit(
        c,
        {"Layer123": neuron_set.get_node_set_definition(circuit, circuit.default_population_name)},
    )

    # Add a node sets based on previously added node sets
    obi.add_node_set_to_circuit(c, {"AllLayers": ["Layer123", "Layer4", "Layer56"]})

    # Write new circuit's node set file
    obi.write_circuit_node_set_file(
        c, output_path=tmp_path, file_name="new_node_sets.json", overwrite_if_exists=False
    )

    with pytest.raises(
        ValueError,
        match=(
            f"Output file '{tmp_path / 'new_node_sets.json'}' already exists!"
            " Delete or choose to overwrite."
        ),
    ):
        # Write again using the same filename (w/o overwrite) --> Must raise an error
        obi.write_circuit_node_set_file(
            c, output_path=tmp_path, file_name="new_node_sets.json", overwrite_if_exists=False
        )

    # Write again, this time with overwrite
    obi.write_circuit_node_set_file(
        c, output_path=tmp_path, file_name="new_node_sets.json", overwrite_if_exists=True
    )

    # Check if new node sets exist in the .json file
    with Path(tmp_path / "new_node_sets.json").open(encoding="utf-8") as f:
        node_sets = json.load(f)

    assert "Layer23" in node_sets
    assert "Layer45" in node_sets
    assert "Layer56" in node_sets
    assert "Layer123" in node_sets
    assert "AllLayers" in node_sets

    assert node_sets["Layer23"] == ["Layer2", "Layer3"]
    assert node_sets["Layer45"] == ["Layer4", "Layer5"]
    assert node_sets["Layer56"] == ["Layer5", "Layer6"]
    assert node_sets["Layer123"] == ["Layer1", "Layer2", "Layer3"]
    assert node_sets["AllLayers"] == ["Layer123", "Layer4", "Layer56"]

    # Reload circuit and check that original node sets are unchanged
    circuit = obi.Circuit(
        name=circuit_name, path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json")
    )
    c = circuit.sonata_circuit
    orig_node_sets = c.node_sets.content
    for k, v in orig_node_sets.items():
        assert k in node_sets
        assert node_sets[k] == v


def test_predefined_neuron_set():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) Non-existing node set --> Error
    neuron_set = obi.PredefinedNeuronSet(node_set="Layer678", sample_percentage=100)
    with pytest.raises(
        ValueError, match=f"Node set 'Layer678' not found in circuit '{circuit_name}'!"
    ):
        neuron_set_ids = neuron_set.get_neuron_ids(
            circuit, population=circuit.default_population_name
        )

    # (b) Existing node set
    neuron_set = obi.PredefinedNeuronSet(node_set="Layer6")
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, population=circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(neuron_set_ids, range(1, 10))
    assert neuron_set_def == ["Layer6"]

    # (c) Existing node set with sub-sampling (11% corresponding to 1 neuron)
    neuron_set = obi.PredefinedNeuronSet(node_set="Layer6", sample_percentage=11)
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, population=circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    assert len(neuron_set_ids) == 1
    assert isinstance(neuron_set_def, dict)
    assert neuron_set_def["population"] == circuit.default_population_name
    assert len(neuron_set_def["node_id"]) == 1

    # (d) Existing node set with invalid sub-sampling --> Error
    with pytest.raises(ValidationError):
        neuron_set = obi.PredefinedNeuronSet(node_set="Layer6", sample_percentage=-1)
    with pytest.raises(ValidationError):
        neuron_set = obi.PredefinedNeuronSet(node_set="Layer6", sample_percentage=101)


def test_combined_neuron_set():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) Non-existing node set --> Error
    neuron_set = obi.CombinedNeuronSet(node_sets=("L6_BPC", "L6_TPC:AA"))
    with pytest.raises(
        ValueError, match=f"Node set 'L6_TPC:AA' not found in circuit '{circuit_name}'!"
    ):
        neuron_set_ids = neuron_set.get_neuron_ids(
            circuit, population=circuit.default_population_name
        )

    # (b) Combined neuron set
    neuron_set = obi.CombinedNeuronSet(node_sets=("L6_BPC", "L6_TPC:A"))
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, population=circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(neuron_set_ids, [1, 2, 6, 7, 8, 9])
    assert neuron_set_def == ["L6_BPC", "L6_TPC:A"]

    # (c) Combined neuron set with sub-sampling (50% corresponding to 3 neuron)
    neuron_set = obi.CombinedNeuronSet(node_sets=("L6_BPC", "L6_TPC:A"), sample_percentage=50)
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, population=circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    assert len(neuron_set_ids) == 3
    assert isinstance(neuron_set_def, dict)
    assert neuron_set_def["population"] == circuit.default_population_name
    assert len(neuron_set_def["node_id"]) == 3


def test_id_neuron_set():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) Invalid IDs --> Error
    neuron_set = obi.IDNeuronSet(
        neuron_ids=obi.NamedTuple(name="IDNeuronSet", elements=(0, 2, 8, 10))
    )
    with pytest.raises(
        ValueError,
        match=re.escape(
            f"Neuron ID(s) not found in population '{circuit.default_population_name}'"
            f" of circuit '{circuit_name}'!"
        ),
    ):
        neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)

    # (b) Selected IDs
    neuron_set = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="IDNeuronSet", elements=range(10)))
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(neuron_set_ids, range(10))
    assert neuron_set_def["population"] == circuit.default_population_name
    np.testing.assert_array_equal(neuron_set_def["node_id"], range(10))

    # (c) Selected IDs with sub-sampling (50% corresponding to 5 neuron)
    neuron_set = obi.IDNeuronSet(
        neuron_ids=obi.NamedTuple(name="IDNeuronSet", elements=range(10)), sample_percentage=50
    )
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    assert len(neuron_set_ids) == 5
    assert neuron_set_def["population"] == circuit.default_population_name
    assert len(neuron_set_def["node_id"]) == 5


def test_property_neuron_set():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) Invalid neuron property --> Error
    neuron_set = obi.PropertyNeuronSet(
        property_filter=obi.NeuronPropertyFilter(
            filter_dict={"INVALID": ["x"], "layer": ["5", "6"], "synapse_class": ["EXC"]}
        ),
    )
    with pytest.raises(ValueError, match="Invalid neuron properties!"):
        neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)

    # (b) Invalid property value --> Empty neuron set
    neuron_set = obi.PropertyNeuronSet(
        property_filter=obi.NeuronPropertyFilter(
            filter_dict={"layer": ["5", "6"], "synapse_class": ["INVALID"]}
        ),
    )
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    assert len(neuron_set_ids) == 0

    # (c) Valid property neuron set
    neuron_set = obi.PropertyNeuronSet(
        property_filter=obi.NeuronPropertyFilter(
            filter_dict={"layer": ["3", "6"], "synapse_class": ["EXC"]}
        ),
    )
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(neuron_set_ids, range(1, 10))
    assert neuron_set_def == {"layer": ["3", "6"], "synapse_class": "EXC"}

    # (d) Valid property neuron set combined with existing node sets --> Enforces resolving node IDs
    neuron_set = obi.PropertyNeuronSet(
        property_filter=obi.NeuronPropertyFilter(filter_dict={"synapse_class": ["EXC"]}),
        node_sets=("Layer3", "Layer6"),
    )
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(neuron_set_ids, range(1, 10))
    assert neuron_set_def["population"] == circuit.default_population_name
    np.testing.assert_array_equal(neuron_set_def["node_id"], range(1, 10))


def _get_distance(circuit, neuron_set, neuron_ids):
    """Get neuron distance relative to the centroid of (filtered) neuron population."""
    base_neuron_ids = obi.PropertyNeuronSet(
        property_filter=neuron_set.property_filter
    ).get_neuron_ids(circuit, circuit.default_population_name)
    all_pos = circuit.sonata_circuit.nodes[circuit.default_population_name].positions(
        base_neuron_ids
    )
    center_pos = all_pos.mean() + np.array([neuron_set.ox, neuron_set.oy, neuron_set.oz])
    sel_pos = circuit.sonata_circuit.nodes[circuit.default_population_name].get(
        neuron_ids, properties=["x", "y", "z"]
    )
    sel_dist = np.sqrt(np.sum((sel_pos - center_pos) ** 2, 1))
    return sel_dist.to_numpy()


def test_volumetric_neuron_sets():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) Volumetric count neuron set with different numbers
    counts = [0, 3, 5, 7, 100]
    expected = [[], [6, 7, 9], [3, 5, 6, 7, 9], [1, 3, 4, 5, 6, 7, 9], range(1, 10)]
    for n, exp in zip(counts, expected, strict=False):
        neuron_set = obi.VolumetricCountNeuronSet(
            ox=10.0,
            oy=25.0,
            oz=100.0,
            n=n,
            property_filter=obi.NeuronPropertyFilter(filter_dict={"synapse_class": ["EXC"]}),
        )
        neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
        neuron_set_def = neuron_set.get_node_set_definition(
            circuit, circuit.default_population_name
        )
        np.testing.assert_array_equal(sorted(neuron_set_ids), exp)
        assert neuron_set_def["population"] == circuit.default_population_name
        np.testing.assert_array_equal(sorted(neuron_set_def["node_id"]), exp)

        # Check distances (no other neurons must be closer)
        cutoff_dist = (
            0.0
            if len(neuron_set_ids) == 0
            else np.max(_get_distance(circuit, neuron_set, neuron_set_ids))
        )
        diff_ids = np.setdiff1d(
            circuit.sonata_circuit.nodes[circuit.default_population_name].ids(), neuron_set_ids
        )
        other_dist = _get_distance(circuit, neuron_set, diff_ids)
        assert np.all(other_dist >= cutoff_dist)

    # (b) Volumetric radius neuron set with different radii
    radii = [0, 50.0, 100.0, 150.0, 200.0, 1000.0]
    expected = [[], [9], [6, 9], [1, 3, 4, 5, 6, 7, 9], range(1, 10), range(1, 10)]
    for r, exp in zip(radii, expected, strict=False):
        neuron_set = obi.VolumetricRadiusNeuronSet(
            ox=10.0,
            oy=25.0,
            oz=100.0,
            radius=r,
            property_filter=obi.NeuronPropertyFilter(
                filter_dict={"layer": ["5", "6"], "synapse_class": ["EXC"]}
            ),
        )
        neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
        neuron_set_def = neuron_set.get_node_set_definition(
            circuit, circuit.default_population_name
        )
        np.testing.assert_array_equal(sorted(neuron_set_ids), exp)
        assert neuron_set_def["population"] == circuit.default_population_name
        np.testing.assert_array_equal(sorted(neuron_set_def["node_id"]), exp)

        # Check distances (all neurons must be within radius)
        dist = _get_distance(circuit, neuron_set, neuron_set_ids)
        assert np.all(dist < r)


def test_simplex_neuron_sets():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # Simplex membership based neuron set
    dim_pos = [
        (2, "source"),
        (2, "target"),
        (3, "source"),
        (3, "target"),
        (4, "source"),
        (4, "target"),
    ]
    expected = [[4, 6, 7, 8, 9], [4, 9], [4, 7, 8, 9], [4, 9], [4, 7, 8, 9], [4, 9]]
    for (dim, pos), exp in zip(dim_pos, expected, strict=False):
        neuron_set = obi.SimplexMembershipBasedNeuronSet(
            central_neuron_id=9,
            dim=dim,
            central_neuron_simplex_position=pos,
            subsample=False,
            property_filter=obi.NeuronPropertyFilter(),
        )
        neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
        neuron_set_def = neuron_set.get_node_set_definition(
            circuit, circuit.default_population_name
        )
        assert neuron_set.central_neuron_id in neuron_set_ids
        np.testing.assert_array_equal(sorted(neuron_set_ids), exp)
        assert neuron_set_def["population"] == circuit.default_population_name
        np.testing.assert_array_equal(sorted(neuron_set_def["node_id"]), exp)

    # Simplex neuron set
    dim_pos = [
        (2, "source"),
        (2, "target"),
        (3, "source"),
        (3, "target"),
        (4, "source"),
        (4, "target"),
    ]
    expected = [[4, 6, 7, 8, 9], [4, 9], [4, 7, 8, 9], [4, 9], [4, 7, 8, 9], [4, 9]]
    for (dim, pos), exp in zip(dim_pos, expected, strict=False):
        neuron_set = obi.SimplexNeuronSet(
            central_neuron_id=9,
            dim=dim,
            central_neuron_simplex_position=pos,
            subsample=False,
            property_filter=obi.NeuronPropertyFilter(),
        )
        neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
        neuron_set_def = neuron_set.get_node_set_definition(
            circuit, circuit.default_population_name
        )
        assert neuron_set.central_neuron_id in neuron_set_ids
        np.testing.assert_array_equal(sorted(neuron_set_ids), exp)
        assert neuron_set_def["population"] == circuit.default_population_name
        np.testing.assert_array_equal(sorted(neuron_set_def["node_id"]), exp)


def test_write_to_node_set_file(tmp_path):
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name, path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json")
    )

    # Write new file
    neuron_set = obi.CombinedNeuronSet(node_sets=("Layer1", "Layer2", "Layer3"))
    nset_file = neuron_set.to_node_set_file(
        circuit,
        circuit.default_population_name,
        output_path=tmp_path,
        overwrite_if_exists=False,
        optional_node_set_name="L123",
    )
    assert Path(nset_file).exists()

    # Write again w/o overwriting --> Must raise an error
    with pytest.raises(
        ValueError,
        match=(
            f"Output file '{tmp_path / 'node_sets.json'}' already exists!"
            " Delete file or choose to append or overwrite."
        ),
    ):
        nset_file = neuron_set.to_node_set_file(
            circuit,
            circuit.default_population_name,
            output_path=tmp_path,
            overwrite_if_exists=False,
            optional_node_set_name="L123",
        )

    # Write again with overwriting --> No error
    nset_file = neuron_set.to_node_set_file(
        circuit,
        circuit.default_population_name,
        output_path=tmp_path,
        overwrite_if_exists=True,
        optional_node_set_name="L123",
    )
    assert Path(nset_file).exists()

    # Append to existing file, but name already exists --> Must raise an error
    with pytest.raises(ValueError, match="Appending not possible, node set 'L123' already exists!"):
        nset_file = neuron_set.to_node_set_file(
            circuit,
            circuit.default_population_name,
            output_path=tmp_path,
            append_if_exists=True,
            optional_node_set_name="L123",
        )

    # Append to existing file
    neuron_set = obi.CombinedNeuronSet(node_sets=("Layer4", "Layer5", "Layer6"))
    nset_file = neuron_set.to_node_set_file(
        circuit,
        circuit.default_population_name,
        output_path=tmp_path,
        append_if_exists=True,
        optional_node_set_name="L456",
    )
    assert Path(nset_file).exists()

    # Check if new node sets exist in the .json file
    with Path(nset_file).open(encoding="utf-8") as f:
        node_sets = json.load(f)

    assert "L123" in node_sets
    assert "L456" in node_sets

    assert node_sets["L123"] == ["Layer1", "Layer2", "Layer3"]
    assert node_sets["L456"] == ["Layer4", "Layer5", "Layer6"]

    # Check that original node sets are preserved in new node sets file
    orig_node_sets = circuit.sonata_circuit.node_sets.content
    for k, v in orig_node_sets.items():
        assert k in node_sets
        assert node_sets[k] == v

    # Check that original node sets are unchanged
    assert "L123" not in orig_node_sets
    assert "L456" not in orig_node_sets


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


def test_hard_coded_neuron_sets():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) All neurons
    neuron_set = obi.AllNeurons()
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(
        neuron_set_ids, circuit.sonata_circuit.nodes[circuit.default_population_name].ids()
    )
    assert neuron_set_def == ["All"]

    # (b) Excitatory neurons
    neuron_set = obi.ExcitatoryNeurons()
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(
        neuron_set_ids,
        circuit.sonata_circuit.nodes[circuit.default_population_name].ids({"synapse_class": "EXC"}),
    )
    assert neuron_set_def == ["Excitatory"]

    # (c) Inhibitory neurons
    neuron_set = obi.InhibitoryNeurons()
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(
        neuron_set_ids,
        circuit.sonata_circuit.nodes[circuit.default_population_name].ids({"synapse_class": "INH"}),
    )
    assert neuron_set_def == ["Inhibitory"]

    # (d) nbS1 VPM population
    neuron_set = obi.nbS1VPMInputs()
    neuron_set_ids = neuron_set.get_neuron_ids(circuit)
    neuron_set_def = neuron_set.get_node_set_definition(circuit)
    np.testing.assert_array_equal(neuron_set_ids, circuit.sonata_circuit.nodes["VPM"].ids())
    assert neuron_set_def == {"population": "VPM"}

    # (e) nbS1 POm population
    neuron_set = obi.nbS1POmInputs()
    neuron_set_ids = neuron_set.get_neuron_ids(circuit)
    neuron_set_def = neuron_set.get_node_set_definition(circuit)
    np.testing.assert_array_equal(neuron_set_ids, circuit.sonata_circuit.nodes["POm"].ids())
    assert neuron_set_def == {"population": "POm"}

    # (f) CA1-CA3 inputs --> Not availbale in nbS1 example circuit, error should be raised
    neuron_set = obi.rCA1CA3Inputs()
    with pytest.raises(
        ValueError,
        match=f"Node population 'CA3_projections' not found in circuit '{circuit_name}'!",
    ):
        neuron_set_ids = neuron_set.get_neuron_ids(circuit)
    with pytest.raises(
        ValueError,
        match=f"Node population 'CA3_projections' not found in circuit '{circuit_name}'!",
    ):
        neuron_set_def = neuron_set.get_node_set_definition(circuit)
