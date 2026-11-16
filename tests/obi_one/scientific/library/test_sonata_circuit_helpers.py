import pytest

from obi_one.core.exception import OBIONEError
from obi_one.core.tuple import NamedTuple
from obi_one.scientific.blocks.neuron_sets.id import BiophysicalPopulationIDNeuronSet
from obi_one.scientific.blocks.neuron_sets.specific import AllBiophysicalNeurons
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.sonata_circuit_helpers import add_neuron_sets_to_sonata_circuit

from tests.utils import CIRCUIT_DIR

POPULATION = "S1nonbarrel_neurons"


@pytest.fixture
def circuit():
    return Circuit(
        name="N_10__top_nodes_dim6",
        path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
    )


def _neuron_set(name, ids):
    neuron_set = BiophysicalPopulationIDNeuronSet(
        population=POPULATION, neuron_ids=NamedTuple(name=name, elements=ids)
    )
    neuron_set.set_block_name(name)
    return neuron_set


def test_neuron_sets_are_added_under_their_names_to_the_returned_circuit(circuit):
    neuron_sets = {"First": _neuron_set("First", [0, 1]), "Second": _neuron_set("Second", [2])}

    sonata_circuit = add_neuron_sets_to_sonata_circuit(circuit, neuron_sets)

    content = sonata_circuit.node_sets.content
    assert content["First"] == {"population": POPULATION, "node_id": [0, 1]}
    assert content["Second"] == {"population": POPULATION, "node_id": [2]}
    # The circuit's node sets from before are still there.
    assert {"All", "Excitatory"} <= set(content)


def test_the_sets_are_only_on_the_returned_object_not_on_the_circuit_file(circuit):
    """`Circuit.sonata_circuit` loads a fresh object per access: only the returned one has them."""
    add_neuron_sets_to_sonata_circuit(circuit, {"First": _neuron_set("First", [0])})

    assert "First" not in circuit.sonata_circuit.node_sets.content


def test_no_neuron_sets_leave_the_node_sets_as_they_are(circuit):
    sonata_circuit = add_neuron_sets_to_sonata_circuit(circuit, {})

    assert sonata_circuit.node_sets.content == circuit.sonata_circuit.node_sets.content


def test_a_neuron_set_identical_to_an_existing_node_set_is_accepted(circuit):
    # The circuit's "AllBiophysical" has exactly the definition this neuron set generates, so
    # adding it under the same name is not a redefinition.
    neuron_set = AllBiophysicalNeurons()
    neuron_set.set_block_name("AllBiophysical")

    sonata_circuit = add_neuron_sets_to_sonata_circuit(circuit, {"AllBiophysical": neuron_set})

    assert sonata_circuit.node_sets.content["AllBiophysical"] == {"population": POPULATION}


def test_a_dictionary_key_that_differs_from_the_block_name_is_rejected(circuit):
    with pytest.raises(OBIONEError, match=r"name mismatch.*'Key'.*'Other'"):
        add_neuron_sets_to_sonata_circuit(circuit, {"Key": _neuron_set("Other", [0])})


def test_a_clash_with_an_existing_node_set_is_rejected(circuit):
    # "Excitatory" is a node set of the circuit already, with a different definition.
    with pytest.raises(ValueError, match="Node set 'Excitatory' already exists"):
        add_neuron_sets_to_sonata_circuit(circuit, {"Excitatory": _neuron_set("Excitatory", [0])})
