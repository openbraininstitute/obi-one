from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import obi_one as obi
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.compartment_sets import (
    CompartmentLocation,
    CompartmentSet,
    build_compartment_set_for_neuron_set,
    build_compartment_set_from_locations_block,
)
from obi_one.scientific.library.entity_property_types import (
    CircuitMappedProperties,
    MappedPropertiesGroup,
)
from obi_one.scientific.library.sonata_circuit_helpers import (
    write_circuit_compartment_set_file,
)
from obi_one.scientific.tasks.generate_simulations.materialize_locations import (
    materialize_locations_to_compartment_sets,
)
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask
from obi_one.scientific.unions.unions_compartment_sets import (
    CompartmentSetReference,
    resolve_compartment_set_ref_to_name,
)
from obi_one.scientific.unions.unions_morphology_locations import MorphologyLocationsReference


def test_compartment_set_sorts_deduplicates_and_builds_from_locations():
    compartment_set = CompartmentSet.from_locations(
        population="pop",
        locations=[
            CompartmentLocation(node_id=2, section_id=3, offset=0.5),
            CompartmentLocation(node_id=1, section_id=4, offset=0.2),
            CompartmentLocation(node_id=2, section_id=3, offset=0.5),
        ],
    )
    compartment_set.set_block_name("target")

    assert compartment_set.to_sonata_dict() == {
        "target": {
            "population": "pop",
            "compartment_set": [[1, 4, 0.2], [2, 3, 0.5]],
        }
    }


def test_compartment_set_population_uses_biophysical_population_dropdown():
    assert CompartmentSet.model_fields["population"].json_schema_extra == {
        SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
        SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
        SchemaKey.PROPERTY: CircuitMappedProperties.BIOPHYSICAL_NEURONAL_POPULATION,
    }


@pytest.mark.parametrize(
    ("columns", "match"),
    [
        ({"offset": [0.5]}, "section_id"),
        ({"section_id": [1]}, "normalized_section_offset.*or.*offset"),
    ],
)
def test_build_compartment_set_rejects_missing_location_columns(columns, match):
    locations_block = MagicMock()
    locations_block.points_on.return_value = pd.DataFrame(columns)

    with pytest.raises(KeyError, match=match):
        build_compartment_set_from_locations_block(
            population="pop",
            locations_block=locations_block,
            morphologies={1: MagicMock()},
        )


def test_build_compartment_set_accepts_offset_column():
    locations_block = MagicMock()
    locations_block.points_on.return_value = pd.DataFrame({"section_id": [3], "offset": [0.25]})

    result = build_compartment_set_from_locations_block(
        population="pop",
        locations_block=locations_block,
        morphologies={7: MagicMock()},
    )

    assert result.compartment_entries == ((7, 3, 0.25),)


def test_build_compartment_set_rejects_neuron_set_without_selected_population():
    neuron_set = MagicMock()
    neuron_set.block.get_neuron_ids.return_value = {"other": [1]}

    with pytest.raises(ValueError, match="does not contain population 'selected'"):
        build_compartment_set_for_neuron_set(
            circuit=MagicMock(),
            node_population="selected",
            population="selected",
            neuron_set=neuron_set,
            locations_block=MagicMock(),
            morphology_loader=MagicMock(),
        )


def test_build_compartment_set_skips_unavailable_morphologies():
    neuron_set = MagicMock()
    neuron_set.block.get_neuron_ids.return_value = {
        "pop": [1, SimpleNamespace(id=2)],
    }
    locations_block = MagicMock()
    locations_block.points_on.return_value = pd.DataFrame(
        {"section_id": [3], "normalized_section_offset": [0.75]}
    )
    morphology = MagicMock()

    result = build_compartment_set_for_neuron_set(
        circuit=MagicMock(),
        node_population="pop",
        population="pop",
        neuron_set=neuron_set,
        locations_block=locations_block,
        morphology_loader=lambda node_id, _population: None if node_id == 1 else morphology,
    )

    assert result.compartment_entries == ((2, 3, 0.75),)
    locations_block.points_on.assert_called_once_with(morphology)


def test_materialization_without_stimuli_returns_empty():
    assert (
        materialize_locations_to_compartment_sets(
            single_config=SimpleNamespace(),
            circuit=MagicMock(),
            node_population="pop",
            population="pop",
            morphology_loader=MagicMock(),
        )
        == {}
    )


def test_compartment_set_reference_name_resolution():
    ref = CompartmentSetReference(block_dict_name="", block_name="target")

    assert resolve_compartment_set_ref_to_name(None, default="default") == "default"
    assert resolve_compartment_set_ref_to_name("raw-name") == "raw-name"
    assert resolve_compartment_set_ref_to_name(ref) == "target"


def test_write_compartment_sets_uses_circuit_default_file(tmp_path):
    circuit = MagicMock()
    circuit.config = {"compartment_sets_file": "inputs/default-compartment-sets.json"}

    output = write_circuit_compartment_set_file(
        circuit,
        str(tmp_path),
        compartment_sets={"target": {"population": "pop", "compartment_set": []}},
    )

    assert output == tmp_path / "default-compartment-sets.json"
    assert output.read_text()


@pytest.mark.parametrize("file_name", ["", "targets.txt", ".json"])
def test_write_compartment_sets_rejects_invalid_file_name(tmp_path, file_name):
    circuit = MagicMock()
    circuit.config = {}

    with pytest.raises(ValueError, match="File name"):
        write_circuit_compartment_set_file(
            circuit,
            str(tmp_path),
            compartment_sets={},
            file_name=file_name,
        )


def test_materialization_requires_locations_neuron_set():
    locations = obi.RandomMorphologyLocations()
    locations.set_block_name("locations")
    locations_ref = MorphologyLocationsReference(
        block_dict_name="morphology_locations",
        block_name="locations",
    )
    locations_ref.block = locations
    stimulus = obi.ConstantCurrentClampSomaticStimulus(neuron_set=locations_ref)
    stimulus.set_block_name("stimulus")

    with pytest.raises(ValueError, match="has no neuron_set"):
        materialize_locations_to_compartment_sets(
            single_config=SimpleNamespace(stimuli={"stimulus": stimulus}),
            circuit=MagicMock(),
            node_population="pop",
            population="pop",
            morphology_loader=MagicMock(),
        )


def test_continuous_stimulus_without_target_uses_default_node_set():
    stimulus = obi.ConstantCurrentClampSomaticStimulus()
    stimulus.set_block_name("stimulus")

    config = stimulus.config(default_node_set="default-target")

    assert config["stimulus_0"]["node_set"] == "default-target"


def test_task_injects_default_into_optional_unified_target():
    default_ref = MagicMock()
    task = GenerateSimulationTask.model_construct(config=SimpleNamespace(neuron_sets={}))
    stimulus = obi.ConstantCurrentClampSomaticStimulus()

    with patch.object(GenerateSimulationTask, "_default_neuron_set_ref", return_value=default_ref):
        task._ensure_block_has_neuron_set_reference_if_neuron_sets_dictionary_exists(stimulus)

    assert stimulus.neuron_set is default_ref


def test_task_assigns_implicit_default_to_morphology_locations():
    default_ref = MagicMock()
    locations = obi.RandomMorphologyLocations()
    task = GenerateSimulationTask.model_construct(
        config=SimpleNamespace(
            morphology_locations={"locations": locations},
            default_neuron_set_reference=default_ref,
        )
    )

    task._ensure_morphology_locations_have_neuron_set_reference()

    assert locations.neuron_set is default_ref


def test_task_requires_circuit_before_materialization():
    task = GenerateSimulationTask.model_construct(config=MagicMock())

    with pytest.raises(obi.OBIONEError, match="Circuit must be resolved"):
        task._materialize_location_targets()
