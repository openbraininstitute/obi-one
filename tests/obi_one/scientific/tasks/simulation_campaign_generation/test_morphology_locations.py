"""How morphology location blocks become SONATA compartment sets.

A stimulus can target a ``MorphologyLocations`` block instead of a neuron set. The task then
materialises the locations against the circuit's morphologies, writes them to
``compartment_sets.json``, and rewrites the stimulus input to reference the compartment set by
name instead of carrying a node set.
"""

import pytest

import obi_one as obi
from obi_one.core.exception import ConfigValidationError, OBIONEError
from obi_one.scientific.blocks.neuron_sets.id import BiophysicalPopulationIDNeuronSet
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask
from obi_one.scientific.unions_and_references.morphology_locations import (
    CircuitMorphologyLocationUnion,
    MorphologyLocationsReference,
    MorphologyLocationUnion,
)

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    DEFAULT_BIOPHYSICAL_NODE_SET,
    build_config,
    generate,
    union_member_names,
)

MORPHOLOGY_POPULATION = "S1nonbarrel_neurons"

MORPHOLOGY_LOCATIONS = {
    "RandomMorphologyLocations": obi.RandomMorphologyLocations(
        random_seed=0, number_of_locations=3
    ),
    "ClusteredMorphologyLocations": obi.ClusteredMorphologyLocations(
        random_seed=0, number_of_locations=4, n_clusters=2
    ),
    "PathDistanceMorphologyLocations": obi.PathDistanceMorphologyLocations(
        random_seed=0, number_of_locations=3
    ),
    "ClusteredPathDistanceMorphologyLocations": obi.ClusteredPathDistanceMorphologyLocations(
        random_seed=0, number_of_locations=4, n_clusters=2
    ),
    "PerNeuronExplicitMorphologyLocations": obi.PerNeuronExplicitMorphologyLocations(
        locations=(
            obi.NeuronMorphologyLocationPoint(node_id=0, section_id=0, offset=0.0),
            obi.NeuronMorphologyLocationPoint(node_id=1, section_id=1, offset=0.5),
        )
    ),
}

EXPLICIT_LOCATIONS = obi.ExplicitMorphologyLocations(
    locations=(
        obi.MorphologyLocationPoint(section_id=0, offset=0.0),
        obi.MorphologyLocationPoint(section_id=1, offset=0.5),
    )
)


def _me_model_locations_config(me_model_config, locations, *, name="Locations"):
    """Explicit locations are only offered for single-neuron configurations."""
    return me_model_config(
        blocks={
            name: locations,
            "Clamp": lambda: obi.ConstantCurrentClampSomaticStimulus(
                neuron_set=locations.ref, amplitude=0.2, duration=50.0
            ),
        }
    )


def _locations_config(circuit, locations, *, neuron_set=None, name="Locations"):
    blocks: dict = {}
    if neuron_set is not None:
        blocks["Cell"] = neuron_set
    blocks[name] = locations
    blocks["Clamp"] = lambda: obi.ConstantCurrentClampSomaticStimulus(
        neuron_set=locations.ref, amplitude=0.2, duration=50.0
    )
    return build_config(CircuitSimulationSingleConfig, circuit=circuit, blocks=blocks)


class TestUnionCoverage:
    def test_every_circuit_selectable_morphology_location_block_is_exercised(self):
        assert union_member_names(CircuitMorphologyLocationUnion) == set(MORPHOLOGY_LOCATIONS)

    def test_explicit_locations_are_not_offered_for_circuits(self):
        """A section id names a different branch on every morphology in a multi-neuron circuit."""
        assert "ExplicitMorphologyLocations" not in union_member_names(
            CircuitMorphologyLocationUnion
        )
        assert "ExplicitMorphologyLocations" in union_member_names(MorphologyLocationUnion)


class TestPerNeuronExplicitLocations:
    """Selected points name their own neuron, so they are written through unchanged."""

    def test_the_selected_rows_are_written_exactly(self, morphology_circuit, tmp_path):
        locations = obi.PerNeuronExplicitMorphologyLocations(
            locations=(
                obi.NeuronMorphologyLocationPoint(node_id=1, section_id=2, offset=0.75),
                obi.NeuronMorphologyLocationPoint(node_id=0, section_id=1, offset=0.25),
            )
        )
        config = _locations_config(morphology_circuit, locations)

        result = generate(config, tmp_path)

        assert result.compartment_sets["Locations"]["compartment_set"] == [
            [0, 1, 0.25],
            [1, 2, 0.75],
        ]
        assert result.compartment_sets["Locations"]["population"] == MORPHOLOGY_POPULATION

    def test_no_cross_product_with_a_neuron_set(self, morphology_circuit, tmp_path):
        """Two points on two neurons stay two rows, however many neurons the circuit holds."""
        locations = obi.PerNeuronExplicitMorphologyLocations(
            locations=(
                obi.NeuronMorphologyLocationPoint(node_id=0, section_id=1, offset=0.5),
                obi.NeuronMorphologyLocationPoint(node_id=1, section_id=1, offset=0.5),
            )
        )
        config = _locations_config(morphology_circuit, locations)

        result = generate(config, tmp_path)

        assert len(result.compartment_sets["Locations"]["compartment_set"]) == 2

    def test_it_does_not_take_a_neuron_set(self):
        """The target neurons are the ones named by the points."""
        assert "neuron_set" not in obi.PerNeuronExplicitMorphologyLocations.model_fields

    def test_an_empty_block_referenced_by_a_stimulus_is_rejected(
        self, morphology_circuit, tmp_path
    ):
        config = _locations_config(morphology_circuit, obi.PerNeuronExplicitMorphologyLocations())

        with pytest.raises(
            ConfigValidationError,
            match="must contain at least one point before they can be used",
        ):
            generate(config, tmp_path)


class TestCompartmentSetGeneration:
    @pytest.mark.parametrize("name", sorted(MORPHOLOGY_LOCATIONS))
    def test_each_location_block_materialises(self, name, morphology_circuit, tmp_path):
        locations = MORPHOLOGY_LOCATIONS[name].model_copy(deep=True)
        config = _locations_config(morphology_circuit, locations)

        result = generate(config, tmp_path)

        assert set(result.compartment_sets) == {"Locations"}
        assert result.compartment_sets["Locations"]["population"] == MORPHOLOGY_POPULATION
        assert len(result.compartment_sets["Locations"]["compartment_set"]) > 0

    def test_compartment_set_file_is_written_and_referenced(self, morphology_circuit, tmp_path):
        config = _locations_config(
            morphology_circuit,
            obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2),
        )

        result = generate(config, tmp_path)

        assert (result.directory / "compartment_sets.json").exists()
        assert result.sonata_config["compartment_sets_file"] == "compartment_sets.json"

    def test_rows_are_node_id_section_id_offset_triples(self, morphology_circuit, tmp_path):
        config = _locations_config(
            morphology_circuit,
            obi.RandomMorphologyLocations(random_seed=0, number_of_locations=5),
        )

        result = generate(config, tmp_path)

        for node_id, section_id, offset in result.compartment_sets["Locations"]["compartment_set"]:
            assert isinstance(node_id, int)
            assert isinstance(section_id, int)
            assert 0.0 <= offset <= 1.0

    def test_rows_are_sorted_and_deduplicated(self, morphology_circuit, tmp_path):
        """``to_sonata_dict`` emits canonical SONATA order, not generation order."""
        config = _locations_config(
            morphology_circuit,
            obi.RandomMorphologyLocations(random_seed=0, number_of_locations=8),
        )

        result = generate(config, tmp_path)

        rows = [tuple(row) for row in result.compartment_sets["Locations"]["compartment_set"]]
        assert rows == sorted(rows)
        assert len(rows) == len(set(rows))

    def test_no_locations_means_no_compartment_sets_file(self, circuit_config, tmp_path):
        result = generate(circuit_config(), tmp_path)

        assert result.compartment_sets is None
        assert "compartment_sets_file" not in result.sonata_config

    def test_empty_explicit_location_block_referenced_by_stimulus_is_rejected(
        self, me_model_config, tmp_path
    ):
        config = _me_model_locations_config(me_model_config, obi.ExplicitMorphologyLocations())

        with pytest.raises(
            ConfigValidationError,
            match="must contain at least one point before they can be used",
        ):
            generate(config, tmp_path)

    def test_explicit_locations_materialise_for_a_single_neuron(self, me_model_config, tmp_path):
        """Explicit points need no neuron set: they name the single neuron being simulated."""
        locations = EXPLICIT_LOCATIONS.model_copy(deep=True)
        config = _me_model_locations_config(me_model_config, locations)

        result = generate(config, tmp_path)

        assert len(result.compartment_sets["Locations"]["compartment_set"]) == len(
            locations.locations
        )

    def test_an_unreferenced_location_block_is_not_materialised(self, morphology_circuit, tmp_path):
        """Only locations a stimulus actually targets become compartment sets."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=morphology_circuit,
            blocks={"Unused": obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2)},
        )

        result = generate(config, tmp_path)

        assert result.compartment_sets is None


class TestStimulusRewriting:
    def test_the_stimulus_targets_the_compartment_set(self, morphology_circuit, tmp_path):
        config = _locations_config(
            morphology_circuit,
            obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2),
        )

        result = generate(config, tmp_path)

        entry = result.inputs["Clamp_0"]
        assert entry["compartment_set"] == "Locations"
        assert "node_set" not in entry
        assert "locations" not in entry

    def test_two_stimuli_sharing_a_location_block_share_one_compartment_set(
        self, morphology_circuit, tmp_path
    ):
        locations = obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=morphology_circuit,
            blocks={
                "Locations": locations,
                "First": lambda: obi.ConstantCurrentClampSomaticStimulus(
                    neuron_set=locations.ref, amplitude=0.1
                ),
                "Second": lambda: obi.ConstantCurrentClampSomaticStimulus(
                    neuron_set=locations.ref, amplitude=0.2
                ),
            },
        )

        result = generate(config, tmp_path)

        assert set(result.compartment_sets) == {"Locations"}
        assert result.inputs["First_0"]["compartment_set"] == "Locations"
        assert result.inputs["Second_0"]["compartment_set"] == "Locations"

    def test_a_location_targeting_stimulus_coexists_with_a_neuron_set_one(
        self, morphology_circuit, tmp_path
    ):
        locations = obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=morphology_circuit,
            blocks={
                "Locations": locations,
                "OnLocations": lambda: obi.ConstantCurrentClampSomaticStimulus(
                    neuron_set=locations.ref
                ),
                "OnSoma": obi.ConstantCurrentClampSomaticStimulus(),
            },
        )

        result = generate(config, tmp_path)

        assert result.inputs["OnLocations_0"]["compartment_set"] == "Locations"
        assert result.inputs["OnSoma_0"]["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET


class TestRecordingRewriting:
    def test_the_recording_targets_the_compartment_set(self, morphology_circuit, tmp_path):
        locations = obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=morphology_circuit,
            blocks={
                "Locations": locations,
                "Voltage": lambda: obi.MorphologyLocationVoltageRecording(
                    morphology_locations=locations.ref
                ),
            },
        )

        result = generate(config, tmp_path)

        assert set(result.compartment_sets) == {"Locations"}
        entry = result.reports["Voltage"]
        assert entry["compartment_set"] == "Locations"
        assert entry["type"] == "compartment_set"
        assert "sections" not in entry
        assert "compartments" not in entry

    def test_the_recording_spans_the_whole_simulation(self, morphology_circuit, tmp_path):
        locations = obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=morphology_circuit,
            blocks={
                "Locations": locations,
                "Voltage": lambda: obi.MorphologyLocationVoltageRecording(
                    morphology_locations=locations.ref
                ),
            },
            initialize={"simulation_length": 400.0},
        )

        result = generate(config, tmp_path)

        assert result.reports["Voltage"]["start_time"] == pytest.approx(0.0)
        assert result.reports["Voltage"]["end_time"] == pytest.approx(400.0)


class TestTimeWindowRecording:
    """The windowed variant records the same compartment set over a narrower interval."""

    @staticmethod
    def _config(morphology_circuit, *, window, simulation_length=500.0):
        locations = obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2)
        return build_config(
            CircuitSimulationSingleConfig,
            circuit=morphology_circuit,
            blocks={
                "Locations": locations,
                "Window": lambda: obi.TimeWindowMorphologyLocationVoltageRecording(
                    morphology_locations=locations.ref, **window
                ),
            },
            initialize={"simulation_length": simulation_length},
        )

    def test_the_window_bounds_are_used_verbatim(self, morphology_circuit, tmp_path):
        config = self._config(morphology_circuit, window={"start_time": 20.0, "end_time": 60.0})

        result = generate(config, tmp_path)

        entry = result.reports["Window"]
        assert entry["compartment_set"] == "Locations"
        assert entry["type"] == "compartment_set"
        assert entry["start_time"] == pytest.approx(20.0)
        assert entry["end_time"] == pytest.approx(60.0)

    def test_the_window_does_not_extend_to_the_simulation_length(
        self, morphology_circuit, tmp_path
    ):
        """The reason for the block: a compartment-set report can be trimmed to one epoch."""
        config = self._config(
            morphology_circuit,
            window={"start_time": 0.0, "end_time": 10.0},
            simulation_length=500.0,
        )

        result = generate(config, tmp_path)

        assert result.reports["Window"]["end_time"] == pytest.approx(10.0)

    def test_a_window_ending_before_it_starts_is_rejected(self):
        locations_ref = MorphologyLocationsReference(
            block_dict_name="morphology_locations", block_name="Locations"
        )

        with pytest.raises(OBIONEError, match="End time must be later"):
            obi.TimeWindowMorphologyLocationVoltageRecording(
                morphology_locations=locations_ref,
                start_time=60.0,
                end_time=20.0,
            )

    @pytest.mark.parametrize(
        ("start_time", "end_time"),
        [
            pytest.param([60.0], 20.0, id="start-time-sweep"),
            pytest.param(60.0, [20.0], id="end-time-sweep"),
        ],
    )
    def test_time_sweeps_defer_window_order_validation(self, start_time, end_time):
        """A sweep is resolved later, so its bounds cannot yet be compared."""
        locations_ref = MorphologyLocationsReference(
            block_dict_name="morphology_locations", block_name="Locations"
        )

        recording = obi.TimeWindowMorphologyLocationVoltageRecording(
            morphology_locations=locations_ref,
            start_time=start_time,
            end_time=end_time,
        )

        assert recording.start_time == start_time
        assert recording.end_time == end_time

    def test_locations_are_still_required(self):
        with pytest.raises(ValueError, match="require morphology locations"):
            obi.TimeWindowMorphologyLocationVoltageRecording(morphology_locations=None)


class TestLocationTargeting:
    def test_locations_without_a_neuron_set_use_the_default(self, morphology_circuit, tmp_path):
        locations = obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2)
        assert locations.neuron_set is None
        config = _locations_config(morphology_circuit, locations)

        generate(config, tmp_path)

        assert config.morphology_locations["Locations"].neuron_set.block_name == (
            DEFAULT_BIOPHYSICAL_NODE_SET
        )

    def test_an_explicit_neuron_set_restricts_the_materialised_cells(
        self, morphology_circuit, tmp_path
    ):
        cell = BiophysicalPopulationIDNeuronSet(
            population=MORPHOLOGY_POPULATION,
            neuron_ids=obi.NamedTuple(name="one_cell", elements=[0]),
        )
        built: dict = {}

        def _locations():
            built["locations"] = obi.RandomMorphologyLocations(
                random_seed=0, number_of_locations=3, neuron_set=cell.ref
            )
            return built["locations"]

        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=morphology_circuit,
            blocks={
                "Cell": cell,
                "Locations": _locations,
                "Clamp": lambda: obi.ConstantCurrentClampSomaticStimulus(
                    neuron_set=built["locations"].ref
                ),
            },
        )

        result = generate(config, tmp_path)

        node_ids = {row[0] for row in result.compartment_sets["Locations"]["compartment_set"]}
        assert node_ids == {0}

    def test_section_types_restrict_where_locations_are_placed(self, morphology_circuit, tmp_path):
        """Section types 3 and 4 are basal and apical dendrite; the soma (1) is excluded."""
        config = _locations_config(
            morphology_circuit,
            obi.RandomMorphologyLocations(random_seed=0, number_of_locations=4, section_types=(3,)),
        )

        result = generate(config, tmp_path)

        assert len(result.compartment_sets["Locations"]["compartment_set"]) > 0


class TestCompartmentSetErrors:
    def test_materialising_before_the_circuit_is_resolved_is_refused(self, circuit_config):
        task = GenerateSimulationTask(config=circuit_config())

        with pytest.raises(OBIONEError, match="Circuit must be resolved before materializing"):
            task._materialize_location_targets()

    def test_a_renamed_compartment_set_is_refused(self, morphology_circuit, tmp_path):
        config = _locations_config(
            morphology_circuit,
            obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2),
        )
        coordinate_root = tmp_path / "0"
        coordinate_root.mkdir(parents=True)
        config.scan_output_root = tmp_path
        config.coordinate_output_root = coordinate_root

        task = GenerateSimulationTask(config=config)
        task.execute()
        renamed = next(iter(task._materialized_compartment_sets.values()))
        task._materialized_compartment_sets = {"Mismatched": renamed}

        with pytest.raises(OBIONEError, match="Materialized compartment set name mismatch"):
            task._write_materialized_compartment_sets_file()
