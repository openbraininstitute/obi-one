from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

import obi_one as obi
from obi_one.core.exception import OBIONEError
from obi_one.core.fill_none_references import fill_none_references_in_config
from obi_one.scientific.library.compartment_sets import (
    CompartmentLocation,
    MaterializedCompartmentSet,
    build_compartment_set_for_neuron_set,
    build_compartment_set_from_locations_block,
)
from obi_one.scientific.library.sonata_circuit_helpers import (
    write_circuit_compartment_set_file,
)
from obi_one.scientific.tasks.generate_simulations.materialize_locations import (
    materialize_locations_to_compartment_sets,
)
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationsReference,
)
from obi_one.scientific.unions_and_references.neuron_sets import BiophysicalNeuronSetReference
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag
from obi_one.scientific.unions_and_references.timestamps import TimestampsReference


def test_compartment_set_sorts_deduplicates_and_builds_from_locations():
    compartment_set = MaterializedCompartmentSet.from_locations(
        name="target",
        population="pop",
        locations=[
            CompartmentLocation(node_id=2, section_id=3, offset=0.5),
            CompartmentLocation(node_id=1, section_id=4, offset=0.2),
            CompartmentLocation(node_id=2, section_id=3, offset=0.5),
        ],
    )

    assert compartment_set.to_sonata_dict() == {
        "target": {
            "population": "pop",
            "compartment_set": [[1, 4, 0.2], [2, 3, 0.5]],
        }
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
            name="target",
            population="pop",
            locations_block=locations_block,
            morphologies={1: MagicMock()},
        )


def test_build_compartment_set_accepts_offset_column():
    locations_block = MagicMock()
    locations_block.points_on.return_value = pd.DataFrame({"section_id": [3], "offset": [0.25]})

    result = build_compartment_set_from_locations_block(
        name="target",
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
            name="target",
            circuit=MagicMock(),
            node_population="selected",
            population="selected",
            neuron_set=neuron_set,
            locations_block=MagicMock(),
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
    circuit = MagicMock()
    circuit.load_morphology.side_effect = [FileNotFoundError, morphology]

    result = build_compartment_set_for_neuron_set(
        name="target",
        circuit=circuit,
        node_population="pop",
        population="pop",
        neuron_set=neuron_set,
        locations_block=locations_block,
    )

    assert result.compartment_entries == ((2, 3, 0.75),)
    locations_block.points_on.assert_called_once_with(morphology)
    assert circuit.load_morphology.call_args_list == [
        call(1, population="pop"),
        call(2, population="pop"),
    ]


def test_materialization_without_stimuli_returns_empty():
    assert (
        materialize_locations_to_compartment_sets(
            single_config=SimpleNamespace(),
            circuit=MagicMock(),
            node_population="pop",
            population="pop",
        )
        == {}
    )


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


def _neuron_set_reference(name: str) -> BiophysicalNeuronSetReference:
    """A resolved neuron set reference, as ``_fill_none_references`` would produce."""
    block = obi.AllBiophysicalNeurons()
    block.set_block_name(name)
    reference = BiophysicalNeuronSetReference(block_dict_name="neuron_sets", block_name=name)
    reference.block = block
    return reference


def _timestamps_reference() -> TimestampsReference:
    block = obi.SingleTimestamp(start_time=0.0)
    block.set_block_name("start")
    reference = TimestampsReference(block_dict_name="timestamps", block_name="start")
    reference.block = block
    return reference


def _fill(config: SimpleNamespace, target_node_set: str = "default-target") -> list:
    return fill_none_references_in_config(
        config,
        {
            ReferenceTag.STIMULUS_TARGET: _neuron_set_reference(target_node_set),
            ReferenceTag.MORPHOLOGY_LOCATIONS_TARGET: _neuron_set_reference(target_node_set),
            ReferenceTag.TIMESTAMPS: _timestamps_reference(),
        },
    )


def test_materialization_uses_the_neuron_set_already_on_the_locations_block():
    """The fallback lives in ``_fill_none_references``; materialisation just reads what it set."""
    locations = obi.RandomMorphologyLocations()
    locations.set_block_name("locations")
    locations_ref = MorphologyLocationsReference(
        block_dict_name="morphology_locations",
        block_name="locations",
    )
    locations_ref.block = locations
    stimulus = obi.ConstantCurrentClampSomaticStimulus(neuron_set=locations_ref)
    stimulus.set_block_name("stimulus")

    config = SimpleNamespace(
        stimuli={"stimulus": stimulus},
        morphology_locations={"locations": locations},
    )
    _fill(config)

    with patch(
        "obi_one.scientific.tasks.generate_simulations.materialize_locations."
        "build_compartment_set_for_neuron_set"
    ) as build_compartment_set:
        build_compartment_set.return_value = MaterializedCompartmentSet(
            name="locations",
            population="pop",
        )

        materialize_locations_to_compartment_sets(
            single_config=config,
            circuit=MagicMock(),
            node_population="pop",
            population="pop",
        )

    build_compartment_set.assert_called_once()
    assert build_compartment_set.call_args.kwargs["name"] == "locations"
    assert build_compartment_set.call_args.kwargs["neuron_set"] is locations.neuron_set


def test_continuous_stimulus_names_the_node_set_it_was_filled_with():
    stimulus = obi.ConstantCurrentClampSomaticStimulus()
    stimulus.set_block_name("stimulus")
    _fill(SimpleNamespace(stimuli={"stimulus": stimulus}))

    config = stimulus.config()

    assert config["stimulus_0"]["node_set"] == "default-target"


def test_continuous_stimulus_with_an_unfilled_target_is_refused():
    """Resolution happens after the fill, so an unset reference here is a programming error."""
    stimulus = obi.ConstantCurrentClampSomaticStimulus()
    stimulus.set_block_name("stimulus")

    with pytest.raises(OBIONEError, match="still unset at resolution time"):
        stimulus.config()


def test_continuous_stimulus_uses_materialized_compartment_set_target():
    stimulus = obi.ConstantCurrentClampSomaticStimulus()
    stimulus.set_block_name("stimulus")
    stimulus.set_materialized_compartment_set_target("LocationCurrentClamp__locations")
    _fill(SimpleNamespace(stimuli={"stimulus": stimulus}))

    config = stimulus.config()

    assert config["stimulus_0"]["compartment_set"] == "LocationCurrentClamp__locations"
    assert "node_set" not in config["stimulus_0"]


def test_fill_gives_a_stimulus_the_default_for_its_role():
    stimulus = obi.ConstantCurrentClampSomaticStimulus()
    target = _neuron_set_reference("chosen")

    used = fill_none_references_in_config(
        SimpleNamespace(stimuli={"stimulus": stimulus}),
        {ReferenceTag.STIMULUS_TARGET: target},
    )

    assert stimulus.neuron_set is target
    assert used == [target]


def test_fill_gives_morphology_locations_the_default_for_their_role():
    locations = obi.RandomMorphologyLocations()
    target = _neuron_set_reference("chosen")

    fill_none_references_in_config(
        SimpleNamespace(morphology_locations={"locations": locations}),
        {ReferenceTag.MORPHOLOGY_LOCATIONS_TARGET: target},
    )

    assert locations.neuron_set is target


def test_fill_leaves_a_reference_that_was_set_explicitly():
    chosen = _neuron_set_reference("chosen")
    stimulus = obi.ConstantCurrentClampSomaticStimulus(neuron_set=chosen)

    used = fill_none_references_in_config(
        SimpleNamespace(stimuli={"stimulus": stimulus}),
        {ReferenceTag.STIMULUS_TARGET: _neuron_set_reference("default-target")},
    )

    assert stimulus.neuron_set is chosen
    assert used == []


def test_fill_reports_each_default_once_however_many_blocks_needed_it():
    target = _neuron_set_reference("chosen")

    used = fill_none_references_in_config(
        SimpleNamespace(
            stimuli={
                "a": obi.ConstantCurrentClampSomaticStimulus(),
                "b": obi.ConstantCurrentClampSomaticStimulus(),
            }
        ),
        {ReferenceTag.STIMULUS_TARGET: target},
    )

    assert used == [target]


def test_fill_is_idempotent():
    stimulus = obi.ConstantCurrentClampSomaticStimulus()
    config = SimpleNamespace(stimuli={"stimulus": stimulus})
    target = _neuron_set_reference("chosen")

    fill_none_references_in_config(config, {ReferenceTag.STIMULUS_TARGET: target})
    used = fill_none_references_in_config(
        config, {ReferenceTag.STIMULUS_TARGET: _neuron_set_reference("other")}
    )

    assert stimulus.neuron_set is target
    assert used == []


def test_task_requires_circuit_before_materialization():
    task = GenerateSimulationTask.model_construct(config=MagicMock())

    with pytest.raises(obi.OBIONEError, match="Circuit must be resolved"):
        task._materialize_location_targets()


def test_task_uploads_materialized_compartment_sets_asset(tmp_path):
    simulation_id = "simulation-id"
    for file_name in (
        GenerateSimulationTask.NODE_SETS_FILE_NAME,
        GenerateSimulationTask.COMPARTMENT_SETS_FILE_NAME,
        GenerateSimulationTask.CONFIG_FILE_NAME,
    ):
        (tmp_path / file_name).write_text("{}")

    task = GenerateSimulationTask.model_construct(
        config=SimpleNamespace(
            coordinate_output_root=tmp_path,
            single_entity=SimpleNamespace(id=simulation_id),
        )
    )
    task._sonata_config = {"inputs": {}}
    db_client = MagicMock()

    task._save_generated_simulation_assets_to_entity(db_client)

    upload_labels_by_path = {
        call_.kwargs["file_path"].name: call_.kwargs["asset_label"]
        for call_ in db_client.upload_file.call_args_list
    }
    assert upload_labels_by_path == {
        GenerateSimulationTask.NODE_SETS_FILE_NAME: "custom_node_sets",
        GenerateSimulationTask.COMPARTMENT_SETS_FILE_NAME: "compartment_sets",
        GenerateSimulationTask.CONFIG_FILE_NAME: "sonata_simulation_config",
    }
    compartment_sets_upload = next(
        call_
        for call_ in db_client.upload_file.call_args_list
        if call_.kwargs["file_path"].name == GenerateSimulationTask.COMPARTMENT_SETS_FILE_NAME
    )
    assert compartment_sets_upload.kwargs["file_name"] == (
        GenerateSimulationTask.COMPARTMENT_SETS_FILE_NAME
    )
