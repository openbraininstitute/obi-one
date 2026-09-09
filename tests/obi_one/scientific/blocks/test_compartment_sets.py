from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

import obi_one as obi
from obi_one.core.exception import ConfigValidationError, OBIONEError
from obi_one.scientific.library import compartment_sets
from obi_one.scientific.library.compartment_sets import (
    CompartmentLocation,
    MaterializedCompartmentSet,
    build_compartment_set_for_neuron_set,
    build_compartment_set_from_locations_block,
)
from obi_one.scientific.library.constants import SIMULATION_TIMESTEP_MILLISECONDS
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
            morphology_items=[(1, MagicMock())],
        )


def test_build_compartment_set_accepts_offset_column():
    locations_block = MagicMock()
    locations_block.points_on.return_value = pd.DataFrame({"section_id": [3], "offset": [0.25]})

    result = build_compartment_set_from_locations_block(
        name="target",
        population="pop",
        locations_block=locations_block,
        morphology_items=[(7, MagicMock())],
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


def test_compartment_set_preflight_rejects_oversized_target_before_loading_morphologies():
    neuron_set = MagicMock()
    neuron_set.block.get_neuron_ids.return_value = {"pop": range(5_001)}
    circuit = MagicMock()

    with pytest.raises(
        ConfigValidationError,
        match="would contain 5,001 entries, which exceeds the maximum of 5,000",
    ):
        build_compartment_set_for_neuron_set(
            name="target",
            circuit=circuit,
            node_population="pop",
            population="pop",
            neuron_set=neuron_set,
            locations_block=obi.RandomMorphologyLocations(number_of_locations=1),
        )

    circuit.load_morphology.assert_not_called()


def test_compartment_set_preflight_allows_exact_limit(monkeypatch):
    monkeypatch.setattr(compartment_sets, "MAX_MATERIALIZED_COMPARTMENT_SET_ENTRIES", 2)
    neuron_set = MagicMock()
    neuron_set.block.get_neuron_ids.return_value = {"pop": [0, 1]}
    circuit = MagicMock()
    expected = MagicMock()

    with patch(
        "obi_one.scientific.library.compartment_sets.build_compartment_set_from_locations_block",
        return_value=expected,
    ) as build_compartment_set:
        result = build_compartment_set_for_neuron_set(
            name="target",
            circuit=circuit,
            node_population="pop",
            population="pop",
            neuron_set=neuron_set,
            locations_block=obi.RandomMorphologyLocations(number_of_locations=1),
        )

    assert result is expected
    build_compartment_set.assert_called_once()

    # Morphologies stream lazily, so nothing is read until the rows are consumed.
    circuit.load_morphology.assert_not_called()
    morphology_items = build_compartment_set.call_args.kwargs["morphology_items"]
    assert [node_id for node_id, _ in morphology_items] == [0, 1]
    assert circuit.load_morphology.call_args_list == [
        call(0, population="pop"),
        call(1, population="pop"),
    ]


def test_morphologies_are_loaded_one_at_a_time():
    """Only the morphology being read is held, so a large target does not accumulate them."""
    neuron_set = MagicMock()
    neuron_set.block.get_neuron_ids.return_value = {"pop": [0, 1, 2]}

    order: list[tuple[str, int]] = []

    def load_morphology(node_id, population):  # ruff: ignore[unused-function-argument]
        order.append(("load", node_id))
        return f"morphology-{node_id}"

    def points_on(morph):
        order.append(("read", int(str(morph).removeprefix("morphology-"))))
        return pd.DataFrame({"section_id": [1], "offset": [0.5]})

    circuit = MagicMock()
    circuit.load_morphology.side_effect = load_morphology
    locations_block = MagicMock()
    locations_block.output_location_count.return_value = 1
    locations_block.points_on.side_effect = points_on

    build_compartment_set_for_neuron_set(
        name="target",
        circuit=circuit,
        node_population="pop",
        population="pop",
        neuron_set=neuron_set,
        locations_block=locations_block,
    )

    assert order == [
        ("load", 0),
        ("read", 0),
        ("load", 1),
        ("read", 1),
        ("load", 2),
        ("read", 2),
    ]


class TestEmptyCompartmentSetsAreRejected:
    """A materialized set is only built when referenced, so empty means it targets nothing."""

    @staticmethod
    def _build(circuit, locations_block, node_ids):
        neuron_set = MagicMock()
        neuron_set.block.get_neuron_ids.return_value = {"pop": node_ids}
        return build_compartment_set_for_neuron_set(
            name="target",
            circuit=circuit,
            node_population="pop",
            population="pop",
            neuron_set=neuron_set,
            locations_block=locations_block,
        )

    def test_a_neuron_set_resolving_to_no_neurons_is_rejected(self):
        circuit = MagicMock()
        locations_block = MagicMock()

        with pytest.raises(
            ConfigValidationError, match="resolves to no neurons in population 'pop'"
        ):
            self._build(circuit, locations_block, [])

        circuit.load_morphology.assert_not_called()

    def test_unreadable_morphologies_are_reported_instead_of_yielding_an_empty_set(self):
        """The failure mode behind an empty compartment_sets.json: every load is skipped."""
        circuit = MagicMock()
        circuit.load_morphology.side_effect = FileNotFoundError
        locations_block = MagicMock()
        locations_block.output_location_count.return_value = 1

        with pytest.raises(
            ConfigValidationError,
            match="none of the 3 targeted neurons in population 'pop' had a readable morphology",
        ):
            self._build(circuit, locations_block, [0, 1, 2])

    def test_a_rule_producing_no_locations_is_rejected(self):
        circuit = MagicMock()
        locations_block = MagicMock()
        locations_block.output_location_count.return_value = None
        locations_block.points_on.return_value = pd.DataFrame({"section_id": [], "offset": []})

        with pytest.raises(
            ConfigValidationError, match="produced no locations on any of the 2 targeted neurons"
        ):
            self._build(circuit, locations_block, [0, 1])

    def test_a_partially_skipped_target_still_succeeds(self):
        """Some unreadable morphologies are tolerated as long as the result is non-empty."""
        morphology = MagicMock()
        circuit = MagicMock()
        circuit.load_morphology.side_effect = [FileNotFoundError, morphology]
        locations_block = MagicMock()
        locations_block.output_location_count.return_value = 1
        locations_block.points_on.return_value = pd.DataFrame({"section_id": [3], "offset": [0.75]})

        result = self._build(circuit, locations_block, [0, 1])

        assert result.compartment_entries == ((1, 3, 0.75),)


def test_compartment_set_row_limit_rejects_unestimated_output(monkeypatch):
    monkeypatch.setattr(compartment_sets, "MAX_MATERIALIZED_COMPARTMENT_SET_ENTRIES", 2)
    locations_block = MagicMock()
    locations_block.points_on.return_value = pd.DataFrame(
        {"section_id": [1, 2, 3], "offset": [0.25, 0.5, 0.75]}
    )

    with pytest.raises(
        ConfigValidationError,
        match="would contain 3 entries, which exceeds the maximum of 2",
    ):
        build_compartment_set_from_locations_block(
            name="target",
            population="pop",
            locations_block=locations_block,
            morphology_items=[(7, MagicMock())],
        )


def test_build_compartment_set_skips_unavailable_morphologies():
    neuron_set = MagicMock()
    neuron_set.block.get_neuron_ids.return_value = {
        "pop": [1, SimpleNamespace(id=2)],
    }
    locations_block = MagicMock()
    locations_block.output_location_count.return_value = None
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


def test_materialization_without_location_targets_returns_empty():
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


def test_materialization_uses_default_neuron_set_for_locations_without_target():
    locations = obi.RandomMorphologyLocations()
    locations.set_block_name("locations")
    locations_ref = MorphologyLocationsReference(
        block_dict_name="morphology_locations",
        block_name="locations",
    )
    locations_ref.block = locations
    stimulus = obi.ConstantCurrentClampSomaticStimulus(neuron_set=locations_ref)
    stimulus.set_block_name("stimulus")
    default_ref = MagicMock()

    with patch(
        "obi_one.scientific.tasks.generate_simulations.materialize_locations."
        "build_compartment_set_for_neuron_set"
    ) as build_compartment_set:
        build_compartment_set.return_value = MaterializedCompartmentSet(
            name="locations",
            population="pop",
        )

        materialize_locations_to_compartment_sets(
            single_config=SimpleNamespace(
                stimuli={"stimulus": stimulus},
                default_neuron_set_reference=default_ref,
            ),
            circuit=MagicMock(),
            node_population="pop",
            population="pop",
        )

    build_compartment_set.assert_called_once()
    assert build_compartment_set.call_args.kwargs["name"] == "locations"
    assert build_compartment_set.call_args.kwargs["neuron_set"] is default_ref


def test_materialization_handles_recording_location_targets():
    locations = obi.RandomMorphologyLocations()
    locations.set_block_name("locations")
    locations_ref = MorphologyLocationsReference(
        block_dict_name="morphology_locations",
        block_name="locations",
    )
    locations_ref.block = locations
    recording = obi.MorphologyLocationVoltageRecording(morphology_locations=locations_ref)
    recording.set_block_name("recording")
    default_ref = MagicMock()

    with patch(
        "obi_one.scientific.tasks.generate_simulations.materialize_locations."
        "build_compartment_set_for_neuron_set"
    ) as build_compartment_set:
        build_compartment_set.return_value = MaterializedCompartmentSet(
            name="locations",
            population="pop",
        )

        materialize_locations_to_compartment_sets(
            single_config=SimpleNamespace(
                recordings={"recording": recording},
                default_neuron_set_reference=default_ref,
            ),
            circuit=MagicMock(),
            node_population="pop",
            population="pop",
        )

    build_compartment_set.assert_called_once()
    config = recording.config(SIMULATION_TIMESTEP_MILLISECONDS, end_time=100.0)["recording"]

    assert config["compartment_set"] == "locations"
    assert config["type"] == "compartment_set"


def _morphology_location_recording():
    locations = obi.RandomMorphologyLocations()
    locations.set_block_name("locations")
    locations_ref = MorphologyLocationsReference(
        block_dict_name="morphology_locations",
        block_name="locations",
    )
    locations_ref.block = locations
    recording = obi.MorphologyLocationVoltageRecording(morphology_locations=locations_ref)
    recording.set_block_name("recording")
    return recording


def test_morphology_location_recording_rejects_none_locations():
    with pytest.raises(ValueError, match="require morphology locations"):
        obi.MorphologyLocationVoltageRecording(morphology_locations=None)


def test_morphology_location_recording_requires_end_time():
    recording = _morphology_location_recording()

    with pytest.raises(OBIONEError, match="End time must be specified"):
        recording.config(SIMULATION_TIMESTEP_MILLISECONDS)


def test_morphology_location_recording_requires_materialized_compartment_set():
    recording = _morphology_location_recording()

    with pytest.raises(OBIONEError, match="no compartment set was materialized"):
        recording.config(SIMULATION_TIMESTEP_MILLISECONDS, end_time=100.0)


def test_morphology_location_recording_requires_end_time_after_start():
    recording = _morphology_location_recording()
    recording.set_materialized_compartment_set_target("locations")

    with pytest.raises(OBIONEError, match="End time must be later"):
        recording.config(SIMULATION_TIMESTEP_MILLISECONDS, end_time=0.0)


def test_continuous_stimulus_without_target_uses_default_node_set():
    stimulus = obi.ConstantCurrentClampSomaticStimulus()
    stimulus.set_block_name("stimulus")

    config = stimulus.config(default_node_set="default-target")

    assert config["stimulus_0"]["node_set"] == "default-target"


def test_continuous_stimulus_uses_materialized_compartment_set_target():
    stimulus = obi.ConstantCurrentClampSomaticStimulus()
    stimulus.set_block_name("stimulus")
    stimulus.set_materialized_compartment_set_target("LocationCurrentClamp__locations")

    config = stimulus.config(default_node_set="default-target")

    assert config["stimulus_0"]["compartment_set"] == "LocationCurrentClamp__locations"
    assert "node_set" not in config["stimulus_0"]


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
