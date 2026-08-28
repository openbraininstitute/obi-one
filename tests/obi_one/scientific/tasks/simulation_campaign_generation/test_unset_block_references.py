"""Blocks whose optional block-reference fields are left unset.

Most reference fields default to ``None``, so "the user added a block and targeted nothing" is the
most common config there is. Specialized blocks may require a target and are covered by dedicated
tests rather than the untargeted sweeps below. Resolving those ``None``s is spread across several
places -- the task fills some in on the block itself before generating, while others stay ``None``
and are resolved to a bare node set *name* inside the block's own ``config()``. These tests pin
what an unset reference currently produces, so that consolidating the two mechanisms can be
checked against real output rather than by reading.

The parametrised sweeps build their cases from the block unions themselves, so a newly added
block type is covered here without anyone editing this file.
"""

import pytest

import obi_one as obi
from obi_one.scientific.blocks.neuron_sets.deprecated import AllNeurons
from obi_one.scientific.blocks.neuron_sets.population import PointPopulationNeuronSet
from obi_one.scientific.blocks.neuronal_manipulations.neuronal_manipulations import (
    ByNeuronMechanismVariableNeuronalManipulation,
    ByNeuronModification,
    BySectionListMechanismVariableNeuronalManipulation,
    BySectionListModification,
)
from obi_one.scientific.blocks.stimuli.brian2_poisson import Brian2DirectPoissonStimulus
from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    NEURONSimulationNeuronSetUnion,
)
from obi_one.scientific.unions_and_references.manipulations import SynapticManipulationsUnion
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationUnion,
)
from obi_one.scientific.unions_and_references.neuronal_manipulations import (
    NeuronalManipulationUnion,
)
from obi_one.scientific.unions_and_references.recordings import RecordingUnion
from obi_one.scientific.unions_and_references.stimuli import CircuitStimulusUnion

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    DEFAULT_BIOPHYSICAL_NODE_SET,
    DEFAULT_BRIAN2_STIMULUS_NODE_SET,
    DEFAULT_POINT_NODE_SET,
    DEFAULT_VIRTUAL_NODE_SET,
    POINT_POPULATION,
    build_config,
    generate,
    reference_field_names,
    reference_types_in,
    union_member_names,
)

# Most blocks in these unions are constructible with no arguments, so "all references unset" is
# the default construction. Required-target blocks are kept out of the untargeted sweeps below.
CIRCUIT_STIMULI = sorted(union_member_names(CircuitStimulusUnion))
RECORDINGS = sorted(union_member_names(RecordingUnion))
REQUIRED_TARGET_RECORDINGS = {"MorphologyLocationVoltageRecording"}
UNTARGETED_RECORDINGS = sorted(
    name for name in RECORDINGS if name not in REQUIRED_TARGET_RECORDINGS
)
SYNAPTIC_MANIPULATIONS = sorted(union_member_names(SynapticManipulationsUnion))
MORPHOLOGY_LOCATIONS = sorted(union_member_names(MorphologyLocationUnion))
COMBINED_NEURON_SETS = sorted(
    name for name in union_member_names(NEURONSimulationNeuronSetUnion) if "Combined" in name
)

ALL_BLOCK_UNIONS = (
    CircuitStimulusUnion,
    RecordingUnion,
    SynapticManipulationsUnion,
    NeuronalManipulationUnion,
    MorphologyLocationUnion,
    NEURONSimulationNeuronSetUnion,
)

BLOCK_CLASSES = {
    name: cls
    for union in ALL_BLOCK_UNIONS
    for name in union_member_names(union)
    for cls in [
        getattr(obi, name, None)
        or {
            "ByNeuronMechanismVariableNeuronalManipulation": (
                ByNeuronMechanismVariableNeuronalManipulation
            ),
            "BySectionListMechanismVariableNeuronalManipulation": (
                BySectionListMechanismVariableNeuronalManipulation
            ),
            "AllNeurons": AllNeurons,
        }[name]
    ]
}

# Seven named neuron sets, one names timestamps, one names a distribution, and one names
# morphology locations (the latter is required by its specialized recording block).
COVERED_REFERENCE_FIELDS = {
    "neuron_set",
    "source_neuron_set",
    "targeted_neuron_set",
    "presynaptic_neuron_set",
    "postsynaptic_neuron_set",
    "base_neuron_set",
    "combined_with",
    "initialize.node_set",
    "timestamps",
    "distribution",
    "morphology_locations",
}

# Neuronal manipulations take a required `modification`, so each needs a factory rather than
# bare construction. Their `neuron_set` is still left unset, which is what these cases are for.
NEURONAL_MANIPULATIONS = {
    "ByNeuronMechanismVariableNeuronalManipulation": lambda: (
        ByNeuronMechanismVariableNeuronalManipulation(
            modification=ByNeuronModification(
                variable_name="Ra", variable_type="RANGE", new_value=100.0
            )
        )
    ),
    "BySectionListMechanismVariableNeuronalManipulation": lambda: (
        BySectionListMechanismVariableNeuronalManipulation(
            modification=BySectionListModification(
                variable_name="cm", section_list_modifications={"somatic": 1.5}
            )
        )
    ),
}

# Which default a combined set with an unset base falls back to, by its own population type.
EXPECTED_COMBINED_DEFAULTS = {
    "BiophysicalCombinedNeuronSet": DEFAULT_BIOPHYSICAL_NODE_SET,
    "NonVirtualCombinedNeuronSet": DEFAULT_BIOPHYSICAL_NODE_SET,
    "VirtualCombinedNeuronSet": DEFAULT_VIRTUAL_NODE_SET,
    "PointCombinedNeuronSet": DEFAULT_POINT_NODE_SET,
}


def _block(name: str):
    """Construct a block by class name with every field, references included, left at default."""
    cls = getattr(obi, name)
    if cls is obi.ExplicitMorphologyLocations:
        return cls(locations=(obi.MorphologyLocationPoint(section_id=1, offset=0.5),))
    return cls()


def _input_entry(result, name: str) -> dict:
    """The generated input for a stimulus, whichever key convention it used.

    Continuous stimuli emit one entry per timestamp (``Clamp_0``); spike stimuli emit a single
    entry under the bare block name.
    """
    if name in result.inputs:
        return result.inputs[name]
    return result.inputs[f"{name}_0"]


class TestEveryReferenceFieldIsExercised:
    """Proves the sweeps below reach every reference field, not just the neuron set ones.

    Simulation-generation blocks carry three kinds of reference: neuron sets (seven differently
    named fields), timestamps and distributions. It is easy to cover the neuron set fields and
    assume the rest came along, so the covered set is asserted against what introspection finds.
    A new reference field on any block fails this test until it is added to the list and given a
    case below.
    """

    def test_the_covered_fields_are_all_the_fields_there_are(self):
        found = {
            field
            for union in ALL_BLOCK_UNIONS
            for name in union_member_names(union)
            for field in reference_field_names(BLOCK_CLASSES[name])
        }
        found |= {
            f"initialize.{field}"
            for field in reference_field_names(CircuitSimulationSingleConfig.Initialize)
        }

        assert found == COVERED_REFERENCE_FIELDS

    def test_the_three_reference_kinds_are_all_represented(self):
        kinds = {
            reference.__name__
            for union in ALL_BLOCK_UNIONS
            for name in union_member_names(union)
            for field_info in BLOCK_CLASSES[name].model_fields.values()
            for reference in reference_types_in(field_info.annotation)
        }

        assert "TimestampsReference" in kinds
        assert "AllDistributionsReference" in kinds
        assert "MorphologyLocationsReference" in kinds
        assert any(name.endswith("NeuronSetReference") for name in kinds)

    @pytest.mark.parametrize(
        "name",
        CIRCUIT_STIMULI + UNTARGETED_RECORDINGS + SYNAPTIC_MANIPULATIONS + MORPHOLOGY_LOCATIONS,
    )
    def test_every_reference_field_defaults_to_none(self, name):
        block_class = getattr(obi, name)
        fields = reference_field_names(block_class)

        assert fields, f"{name} was expected to have at least one reference field"
        for field in fields:
            assert block_class.model_fields[field].default is None

    @pytest.mark.parametrize("name", COMBINED_NEURON_SETS)
    def test_a_combined_neuron_set_starts_with_no_operands(self, name):
        """``combined_with`` is the one reference field that defaults to empty rather than None."""
        block_class = getattr(obi, name)

        assert block_class.model_fields["base_neuron_set"].default is None
        assert block_class.model_fields["combined_with"].default == ()

    def test_a_block_constructed_with_no_arguments_has_no_targets(self):
        stimulus = obi.ConstantCurrentClampSomaticStimulus()

        assert stimulus.neuron_set is None
        assert stimulus.timestamps is None


class TestUnsetReferencesResolveToTheDefault:
    """Whatever the mechanism, an unset reference must end up naming the default neuron set."""

    @pytest.mark.parametrize("name", CIRCUIT_STIMULI)
    def test_stimulus_targets_the_default_neuron_set(self, name, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig, circuit=circuit, blocks={"Stim": _block(name)}
        )

        result = generate(config, tmp_path)

        assert _input_entry(result, "Stim")["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET

    @pytest.mark.parametrize("name", UNTARGETED_RECORDINGS)
    def test_recording_records_the_default_neuron_set(self, name, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig, circuit=circuit, blocks={"Rec": _block(name)}
        )

        result = generate(config, tmp_path)

        assert result.reports["Rec"]["cells"] == DEFAULT_BIOPHYSICAL_NODE_SET

    @pytest.mark.parametrize("name", SYNAPTIC_MANIPULATIONS)
    def test_synaptic_manipulation_spans_the_default_on_both_sides(self, name, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig, circuit=circuit, blocks={"Manip": _block(name)}
        )

        result = generate(config, tmp_path)

        override = result.sonata_config["connection_overrides"][0]
        assert override["source"] == DEFAULT_BIOPHYSICAL_NODE_SET
        assert override["target"] == DEFAULT_BIOPHYSICAL_NODE_SET

    @pytest.mark.parametrize("name", COMBINED_NEURON_SETS)
    def test_combined_neuron_set_base_is_filled_with_its_population_default(
        self, name, circuit, point_circuit, tmp_path
    ):
        """Each combined set picks up the default for its own population type.

        A point combined set needs a circuit with a point population to resolve against, and a
        simulation target that is itself a point set, so it gets the drosophila circuit.
        """
        is_point = name == "PointCombinedNeuronSet"
        blocks: dict = {"Combined": _block(name)}
        if is_point:
            target = PointPopulationNeuronSet(population=POINT_POPULATION)
            blocks = {"Target": target, **blocks}

        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=point_circuit if is_point else circuit,
            blocks=blocks,
        )
        if is_point:
            config.initialize.node_set = config.neuron_sets["Target"].ref

        result = generate(config, tmp_path)

        base = config.neuron_sets["Combined"].base_neuron_set
        assert base is not None
        assert base.block_name == (
            DEFAULT_POINT_NODE_SET if is_point else EXPECTED_COMBINED_DEFAULTS[name]
        )
        assert base.block_name in result.node_sets

    @pytest.mark.parametrize("name", COMBINED_NEURON_SETS)
    def test_combined_neuron_set_operands_are_filled_too(
        self, name, circuit, point_circuit, tmp_path
    ):
        """``combined_with`` entries are ``(reference, operation)`` pairs whose reference can
        also be unset, and each one is filled with the same population default as the base."""
        is_point = name == "PointCombinedNeuronSet"
        combined = getattr(obi, name)(
            base_neuron_set=None, combined_with=((None, "union"), (None, "union"))
        )
        blocks: dict = {"Combined": combined}
        if is_point:
            blocks = {"Target": PointPopulationNeuronSet(population=POINT_POPULATION), **blocks}

        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=point_circuit if is_point else circuit,
            blocks=blocks,
        )
        if is_point:
            config.initialize.node_set = config.neuron_sets["Target"].ref

        generate(config, tmp_path)

        expected = EXPECTED_COMBINED_DEFAULTS[name]
        operands = config.neuron_sets["Combined"].combined_with
        assert len(operands) == 2
        for reference, _operation in operands:
            assert reference is not None
            assert reference.block_name == expected

    @pytest.mark.parametrize("name", MORPHOLOGY_LOCATIONS)
    def test_morphology_locations_target_the_default_neuron_set(
        self, name, morphology_circuit, tmp_path
    ):
        locations = _block(name)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=morphology_circuit,
            blocks={
                "Locations": locations,
                "Clamp": lambda: obi.ConstantCurrentClampSomaticStimulus(neuron_set=locations.ref),
            },
        )

        generate(config, tmp_path)

        assert config.morphology_locations["Locations"].neuron_set.block_name == (
            DEFAULT_BIOPHYSICAL_NODE_SET
        )

    def test_neuronal_manipulation_applies_to_the_default_neuron_set(
        self, me_model_config, tmp_path
    ):
        config = me_model_config(
            blocks={
                "Manip": ByNeuronMechanismVariableNeuronalManipulation(
                    modification=ByNeuronModification(
                        variable_name="Ra", variable_type="RANGE", new_value=100.0
                    )
                )
            }
        )

        result = generate(config, tmp_path)

        assert result.conditions["modifications"][0]["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET

    def test_unset_simulation_target_resolves_to_the_default(self, circuit_config, tmp_path):
        config = circuit_config()
        assert config.initialize.node_set is None

        result = generate(config, tmp_path)

        assert result.sonata_config["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET


class TestNoDanglingNodeSetReferences:
    """The invariant that matters: a name the config points at must exist in node_sets.json.

    The default neuron set is created as a side effect of resolving an unset reference. If that
    side effect is ever lost -- or happens after the node sets file is written -- the generated
    config silently references a node set that is not there, and the simulator fails at run time
    rather than here.
    """

    @pytest.mark.parametrize("name", CIRCUIT_STIMULI)
    def test_a_single_untargeted_stimulus_leaves_nothing_dangling(self, name, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig, circuit=circuit, blocks={"Stim": _block(name)}
        )

        result = generate(config, tmp_path)

        assert result.dangling_node_sets() == set()

    def test_a_config_whose_only_block_is_a_manipulation(self, circuit, tmp_path):
        """Nothing else creates the default here, so only the manipulation can have done it."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Manip": obi.SynapticMgManipulation()},
        )

        result = generate(config, tmp_path)

        assert result.referenced_node_sets() == {DEFAULT_BIOPHYSICAL_NODE_SET}
        assert result.dangling_node_sets() == set()

    def test_every_block_family_untargeted_at_once(self, circuit, tmp_path):
        """One block of each kind, none of them targeting anything."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Clamp": obi.ConstantCurrentClampSomaticStimulus(),
                "Spikes": obi.PoissonSpikeStimulus(),
                "Voltage": obi.SomaVoltageRecording(),
                "Window": obi.TimeWindowSomaVoltageRecording(start_time=0.0, end_time=10.0),
                "Magnesium": obi.SynapticMgManipulation(),
                "Acetylcholine": obi.ScaleAcetylcholineUSESynapticManipulation(),
                "Combined": obi.BiophysicalCombinedNeuronSet(),
            },
        )

        result = generate(config, tmp_path)

        assert result.dangling_node_sets() == set()

    def test_untargeted_me_model_blocks_leave_nothing_dangling(self, me_model_config, tmp_path):
        config = me_model_config(
            blocks={
                "Clamp": obi.ConstantCurrentClampSomaticStimulus(),
                "Voltage": obi.SomaVoltageRecording(),
            }
        )

        result = generate(config, tmp_path)

        assert result.dangling_node_sets() == set()

    def test_untargeted_brian2_stimulus_leaves_nothing_dangling(self, brian2_config, tmp_path):
        """Brian2 resolves two different defaults, and both node sets have to be written."""
        config = brian2_config(blocks={"DirectPoisson": Brian2DirectPoissonStimulus()})

        result = generate(config, tmp_path)

        assert result.referenced_node_sets() == {
            DEFAULT_POINT_NODE_SET,
            DEFAULT_BRIAN2_STIMULUS_NODE_SET,
        }
        assert result.dangling_node_sets() == set()

    def test_untargeted_learning_engine_stimulus_leaves_nothing_dangling(
        self, learning_engine_config, tmp_path
    ):
        config = learning_engine_config(blocks={"Clamp": obi.ConstantCurrentClampSomaticStimulus()})

        result = generate(config, tmp_path)

        assert result.dangling_node_sets() == set()

    def test_the_default_is_created_exactly_once(self, circuit, tmp_path):
        """Several untargeted blocks share one injected default rather than each adding one."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "First": obi.ConstantCurrentClampSomaticStimulus(),
                "Second": obi.HyperpolarizingCurrentClampSomaticStimulus(),
                "Voltage": obi.SomaVoltageRecording(),
            },
        )

        generate(config, tmp_path)

        assert list(config.neuron_sets) == [DEFAULT_BIOPHYSICAL_NODE_SET]


class TestWhichReferencesAreFilledInPlace:
    """Characterisation of the current split between the two resolution mechanisms.

    Stimuli, recordings, morphology locations and combined neuron sets have their unset
    references replaced with a real reference on the block before generation. Timestamps,
    distributions and both kinds of manipulation are left ``None`` and resolved to a node set
    name inside the block's own ``config()``. The generated SONATA is the same either way, which
    is exactly why the divergence is easy to miss -- these assertions make it visible.
    """

    def test_stimulus_and_recording_targets_are_filled_on_the_block(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Clamp": obi.ConstantCurrentClampSomaticStimulus(),
                "Voltage": obi.SomaVoltageRecording(),
            },
        )

        generate(config, tmp_path)

        assert config.stimuli["Clamp"].neuron_set is not None
        assert config.recordings["Voltage"].neuron_set is not None

    def test_spike_stimulus_source_and_target_are_both_filled(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Spikes": obi.PoissonSpikeStimulus()},
        )

        generate(config, tmp_path)

        stimulus = config.stimuli["Spikes"]
        assert stimulus.source_neuron_set.block_name == DEFAULT_BIOPHYSICAL_NODE_SET
        assert stimulus.targeted_neuron_set.block_name == DEFAULT_BIOPHYSICAL_NODE_SET

    def test_timestamps_are_left_unset_on_the_block(self, circuit, tmp_path):
        """The default timestamps never reach the config; they are applied during generation."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Clamp": obi.ConstantCurrentClampSomaticStimulus()},
        )

        result = generate(config, tmp_path)

        assert config.stimuli["Clamp"].timestamps is None
        assert result.inputs["Clamp_0"]["delay"] == pytest.approx(0.0)

    def test_manipulation_targets_are_left_unset_on_the_block(self, circuit, tmp_path):
        """Unlike stimuli, a manipulation keeps its ``None`` and is resolved by name later."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Magnesium": obi.SynapticMgManipulation()},
        )

        result = generate(config, tmp_path)

        manipulation = config.synaptic_manipulations["Magnesium"]
        assert manipulation.presynaptic_neuron_set is None
        assert manipulation.postsynaptic_neuron_set is None
        assert result.sonata_config["connection_overrides"][0]["source"] == (
            DEFAULT_BIOPHYSICAL_NODE_SET
        )

    def test_neuronal_manipulation_target_is_left_unset_on_the_block(
        self, me_model_config, tmp_path
    ):
        config = me_model_config(
            blocks={
                "Manip": ByNeuronMechanismVariableNeuronalManipulation(
                    modification=ByNeuronModification(
                        variable_name="Ra", variable_type="RANGE", new_value=100.0
                    )
                )
            }
        )

        result = generate(config, tmp_path)

        assert config.neuronal_manipulations["Manip"].neuron_set is None
        assert result.conditions["modifications"][0]["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET


class TestConfigWithoutANeuronSetsDictionary:
    """The ME model config has no ``neuron_sets`` field, so nothing is filled in on its blocks.

    It reaches the same SONATA output through the blocks' own default-node-set fallback. That is
    the second mechanism producing the first mechanism's result, on a different config family.
    """

    def test_references_stay_unset_on_the_blocks(self, me_model_config, tmp_path):
        config = me_model_config(
            blocks={
                "Clamp": obi.ConstantCurrentClampSomaticStimulus(),
                "Voltage": obi.SomaVoltageRecording(),
            }
        )
        assert not hasattr(config, "neuron_sets")

        generate(config, tmp_path)

        assert config.stimuli["Clamp"].neuron_set is None
        assert config.recordings["Voltage"].neuron_set is None

    def test_the_output_still_names_the_default(self, me_model_config, tmp_path):
        config = me_model_config(
            blocks={
                "Clamp": obi.ConstantCurrentClampSomaticStimulus(),
                "Voltage": obi.SomaVoltageRecording(),
            }
        )

        result = generate(config, tmp_path)

        assert result.inputs["Clamp_0"]["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET
        assert result.reports["Voltage"]["cells"] == DEFAULT_BIOPHYSICAL_NODE_SET

    def test_the_default_node_set_is_still_written(self, me_model_config, tmp_path):
        result = generate(me_model_config(), tmp_path)

        assert DEFAULT_BIOPHYSICAL_NODE_SET in result.node_sets


class TestUnsetTimestampsAndDistributions:
    """The two reference kinds that do not name a neuron set."""

    @pytest.mark.parametrize("name", CIRCUIT_STIMULI)
    def test_an_unset_timestamps_reference_starts_the_stimulus_at_zero(
        self, name, circuit, tmp_path
    ):
        config = build_config(
            CircuitSimulationSingleConfig, circuit=circuit, blocks={"Stim": _block(name)}
        )

        result = generate(config, tmp_path)

        assert _input_entry(result, "Stim")["delay"] == pytest.approx(0.0)

    def test_a_continuous_stimulus_without_timestamps_emits_exactly_one_input(
        self, circuit, tmp_path
    ):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Clamp": obi.ConstantCurrentClampSomaticStimulus()},
        )

        result = generate(config, tmp_path)

        assert set(result.inputs) == {"Clamp_0"}

    @pytest.mark.parametrize(
        "name", ["ConnectSynapticManipulation", "DisconnectSynapticManipulation"]
    )
    def test_a_delayed_manipulation_without_timestamps_applies_at_zero(
        self, name, circuit, tmp_path
    ):
        """These two are the only manipulations carrying a timestamps reference."""
        config = build_config(
            CircuitSimulationSingleConfig, circuit=circuit, blocks={"Manip": _block(name)}
        )

        result = generate(config, tmp_path)

        assert config.synaptic_manipulations["Manip"].timestamps is None
        overrides = result.sonata_config["connection_overrides"]
        assert len(overrides) == 1
        assert overrides[0]["delay"] == pytest.approx(0.0)

    @pytest.mark.parametrize(
        "name",
        [
            "InterSpikeIntervalDistributionSpikeStimulus",
            "SpikeTimeDistributionSpikeStimulus",
        ],
    )
    def test_a_distribution_driven_stimulus_generates_without_a_distribution(
        self, name, circuit, tmp_path
    ):
        """These stimuli fall back to their own distribution rather than failing."""
        config = build_config(
            CircuitSimulationSingleConfig, circuit=circuit, blocks={"Stim": _block(name)}
        )

        result = generate(config, tmp_path)

        assert config.stimuli["Stim"].distribution is None
        assert result.inputs["Stim"]["spike_file"] == "Stim_spikes.h5"
        assert (result.directory / "Stim_spikes.h5").exists()


class TestUnsetReferencesAcrossEveryBlockAtOnce:
    def test_a_config_of_entirely_untargeted_blocks_generates_valid_sonata(self, circuit, tmp_path):
        """The end state this module is really about: nothing anywhere points at anything."""
        blocks = {name: _block(name) for name in CIRCUIT_STIMULI}
        blocks |= {name: _block(name) for name in UNTARGETED_RECORDINGS}
        blocks |= {name: _block(name) for name in SYNAPTIC_MANIPULATIONS}

        config = build_config(CircuitSimulationSingleConfig, circuit=circuit, blocks=blocks)

        result = generate(config, tmp_path)

        assert result.dangling_node_sets() == set()
        assert result.referenced_node_sets() == {DEFAULT_BIOPHYSICAL_NODE_SET}
        assert len(result.inputs) == len(CIRCUIT_STIMULI)
        assert len(result.reports) == len(UNTARGETED_RECORDINGS)
        assert len(result.sonata_config["connection_overrides"]) == len(SYNAPTIC_MANIPULATIONS)

    def test_spike_stimuli_are_the_only_ones_that_can_target_a_virtual_source(
        self, circuit, tmp_path
    ):
        """An unset spike source defaults to the biophysical set, not a virtual population.

        The source is allowed to be virtual, so the default could plausibly have been the virtual
        one; it is not, and replay spikes are generated from the biophysical cells instead.
        """
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Spikes": obi.PoissonSpikeStimulus()},
        )

        result = generate(config, tmp_path)

        assert isinstance(config.stimuli["Spikes"], SpikeStimulus)
        assert config.stimuli["Spikes"].source_neuron_set.block_name == (
            DEFAULT_BIOPHYSICAL_NODE_SET
        )
        assert (result.directory / "Spikes_spikes.h5").exists()


class TestUntargetedNeuronalManipulations:
    """Neuronal manipulations need a ``modification``, so they cannot use the sweeps above."""

    @pytest.mark.parametrize("name", sorted(union_member_names(NeuronalManipulationUnion)))
    def test_the_target_is_optional_and_unset_by_default(self, name):
        block_class = NEURONAL_MANIPULATIONS[name]().__class__

        assert "neuron_set" in reference_field_names(block_class)
        assert block_class.model_fields["neuron_set"].default is None

    @pytest.mark.parametrize("name", sorted(NEURONAL_MANIPULATIONS))
    def test_an_untargeted_manipulation_applies_to_the_default(
        self, name, me_model_config, tmp_path
    ):
        config = me_model_config(blocks={"Manip": NEURONAL_MANIPULATIONS[name]()})

        result = generate(config, tmp_path)

        assert config.neuronal_manipulations["Manip"].neuron_set is None
        modifications = result.conditions["modifications"]
        assert modifications
        for modification in modifications:
            assert modification["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET

    def test_an_untargeted_manipulation_leaves_nothing_dangling(self, me_model_config, tmp_path):
        config = me_model_config(
            blocks={name: factory() for name, factory in NEURONAL_MANIPULATIONS.items()}
        )

        result = generate(config, tmp_path)

        assert result.dangling_node_sets() == set()
