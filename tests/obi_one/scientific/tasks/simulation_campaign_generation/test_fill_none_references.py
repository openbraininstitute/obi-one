"""The declarative layer that decides what an unset block reference means.

Every reference field a simulation block can hold declares its role with a
``SchemaKey.REFERENCE_TAG``, and ``GenerateSimulationTask`` maps each role to the reference to
substitute. Nothing else in generation is allowed to invent a fallback, so these tests guard the
two halves that make that safe: no field may go untagged, and no tag may go unhandled.

They are deliberately introspective rather than example-based. A new block or a new reference
field fails them until someone decides what leaving it unset should mean.
"""

import abc
import inspect

import pytest

import obi_one as obi
from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.schema import SchemaKey
from obi_one.scientific.blocks.stimuli.brian2_poisson import Brian2DirectPoissonStimulus
from obi_one.scientific.tasks.generate_simulations.config.base import BaseSimulationScanConfig
from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_circuit import (
    Brian2CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.learning_engine.le_circuit import (
    LearningEngineCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    BLOCK_SUPPLIED_REFERENCE_TAGS,
    DEFAULT_BRIAN2_STIMULUS_NODE_SET,
    build_config,
    generate,
    reference_types_in,
    unfilled_reference_fields,
)

# The block modules that simulation generation resolves references for. Blocks belonging to other
# tasks -- synapse parameterization, circuit extraction -- are not filled by this mechanism and so
# are not required to carry tags.
SIMULATION_BLOCK_MODULES = (
    "blocks/stimuli/",
    "blocks/recordings/",
    "blocks/neuron_sets/combined",
    "blocks/synaptic_manipulations/",
    "blocks/neuronal_manipulations/",
    "blocks/morphology_locations/",
    "tasks/generate_simulations/",
)


def _all_block_subclasses() -> set[type]:
    todo, seen = [Block], set()
    while todo:
        cls = todo.pop()
        if cls in seen:
            continue
        seen.add(cls)
        todo.extend(cls.__subclasses__())
    return seen


def _is_concrete(cls: type) -> bool:
    """Abstract bases declare placeholder fields that every concrete subclass overrides."""
    return abc.ABC not in cls.__bases__ and not inspect.isabstract(cls)


def _simulation_reference_fields() -> list[tuple[type, str, object]]:
    """Every reference field a concrete simulation block has, with the tag it carries.

    Inherited fields count: what matters is that a block a user can actually build has no
    reference field whose meaning when unset is undeclared.
    """
    fields = []
    for cls in _all_block_subclasses():
        if not _is_concrete(cls):
            continue
        try:
            source = inspect.getfile(cls)
        except TypeError:  # pragma: no cover - builtins have no source file
            continue
        if not any(module in source for module in SIMULATION_BLOCK_MODULES):
            continue
        for name, field_info in cls.model_fields.items():
            if not reference_types_in(field_info.annotation):
                continue
            extra = field_info.json_schema_extra
            tag = extra.get(SchemaKey.REFERENCE_TAG) if isinstance(extra, dict) else None
            fields.append((cls, name, tag))
    return fields


class TestEveryReferenceFieldDeclaresItsRole:
    def test_no_simulation_reference_field_is_untagged(self):
        untagged = [
            f"{cls.__name__}.{name}" for cls, name, tag in _simulation_reference_fields() if not tag
        ]

        assert untagged == []

    def test_the_introspection_actually_finds_fields(self):
        """Guards the sweep above against silently matching nothing."""
        assert len(_simulation_reference_fields()) > 20

    def test_combined_neuron_sets_tag_their_operands_by_population_type(self):
        """Each combined subclass means a different thing by an unset operand."""
        expected = {
            obi.CombinedNeuronSet: ReferenceTag.ANY_NEURON_SET_OPERAND,
            obi.BiophysicalCombinedNeuronSet: ReferenceTag.BIOPHYSICAL_NEURON_SET_OPERAND,
            obi.PointCombinedNeuronSet: ReferenceTag.POINT_NEURON_SET_OPERAND,
            obi.VirtualCombinedNeuronSet: ReferenceTag.VIRTUAL_NEURON_SET_OPERAND,
            obi.NonVirtualCombinedNeuronSet: ReferenceTag.NON_VIRTUAL_NEURON_SET_OPERAND,
        }

        for cls, tag in expected.items():
            for field in ("base_neuron_set", "combined_with"):
                assert cls.model_fields[field].json_schema_extra[SchemaKey.REFERENCE_TAG] == tag


class TestEveryTagIsHandled:
    """A tag with no default silently leaves its field unset, so the split is pinned explicitly."""

    def test_the_config_supplies_a_default_for_every_tag_it_does_not_delegate(
        self, circuit_config, circuit
    ):
        supplied = set(circuit_config().default_block_references(circuit))

        assert supplied == set(ReferenceTag) - BLOCK_SUPPLIED_REFERENCE_TAGS

    def test_the_delegated_tags_are_the_two_spike_distributions(self):
        """Their defaults depend on the stimulus's own parameters, so no task can supply them."""
        assert {
            ReferenceTag.INTER_SPIKE_INTERVAL_DISTRIBUTION,
            ReferenceTag.SPIKE_TIME_DISTRIBUTION,
        } == BLOCK_SUPPLIED_REFERENCE_TAGS

    def test_every_default_is_a_resolved_block_reference(self, circuit_config, circuit):
        for tag, default in circuit_config().default_block_references(circuit).items():
            assert isinstance(default, BlockReference), tag
            assert default.has_block(), tag

    @pytest.mark.parametrize("tag", sorted(BLOCK_SUPPLIED_REFERENCE_TAGS))
    def test_a_delegated_tag_leaves_its_field_alone(self, tag, circuit, tmp_path):
        stimulus_names = {
            ReferenceTag.INTER_SPIKE_INTERVAL_DISTRIBUTION: (
                "InterSpikeIntervalDistributionSpikeStimulus"
            ),
            ReferenceTag.SPIKE_TIME_DISTRIBUTION: "SpikeTimeDistributionSpikeStimulus",
        }
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Stim": getattr(obi, stimulus_names[tag])()},
        )

        generate(config, tmp_path)

        assert config.stimuli["Stim"].distribution is None


class TestTheInvariantHoldsForEveryConfigFamily:
    """After the fill, no config of any family has a tagged reference left unset."""

    def test_neuron_circuit(self, circuit_config, tmp_path):
        config = circuit_config(
            blocks={
                "Clamp": obi.ConstantCurrentClampSomaticStimulus(),
                "Spikes": obi.PoissonSpikeStimulus(),
                "Voltage": obi.SomaVoltageRecording(),
                "Magnesium": obi.SynapticMgManipulation(),
            }
        )

        generate(config, tmp_path)

        assert unfilled_reference_fields(config) == []

    def test_me_model(self, me_model_config, tmp_path):
        config = me_model_config(
            blocks={
                "Clamp": obi.ConstantCurrentClampSomaticStimulus(),
                "Voltage": obi.SomaVoltageRecording(),
                "Locations": obi.RandomMorphologyLocations(),
            }
        )

        generate(config, tmp_path)

        assert unfilled_reference_fields(config) == []

    def test_brian2(self, brian2_config, tmp_path):
        config = brian2_config(blocks={"Poisson": Brian2DirectPoissonStimulus()})

        generate(config, tmp_path)

        assert unfilled_reference_fields(config) == []

    def test_learning_engine(self, learning_engine_config, tmp_path):
        config = learning_engine_config(blocks={"Clamp": obi.ConstantCurrentClampSomaticStimulus()})

        generate(config, tmp_path)

        assert unfilled_reference_fields(config) == []


class TestTheStimulusTargetTagVariesByConfigFamily:
    """The one role whose meaning genuinely differs between simulators."""

    def test_brian2_points_an_untargeted_stimulus_at_the_sugar_node_set(
        self, brian2_config, tmp_path
    ):
        config = brian2_config(blocks={"Poisson": Brian2DirectPoissonStimulus()})

        result = generate(config, tmp_path)

        assert config.stimuli["Poisson"].neuron_set.block_name == (DEFAULT_BRIAN2_STIMULUS_NODE_SET)
        assert result.inputs["Poisson"]["node_set"] == DEFAULT_BRIAN2_STIMULUS_NODE_SET

    def test_a_neuron_simulation_points_it_at_the_simulation_default(
        self, circuit_config, tmp_path
    ):
        config = circuit_config(blocks={"Clamp": obi.ConstantCurrentClampSomaticStimulus()})

        generate(config, tmp_path)

        assert config.stimuli["Clamp"].neuron_set.block_name == (
            CircuitSimulationSingleConfig.default_node_set_name
        )

    @pytest.mark.parametrize(
        "config_class",
        [
            CircuitSimulationSingleConfig,
            MEModelSimulationSingleConfig,
            LearningEngineCircuitSimulationSingleConfig,
        ],
    )
    def test_other_families_inherit_the_base_mapping(self, config_class):
        """They vary only through default_neuron_set_type, not by rewriting the mapping."""
        assert (
            config_class.default_block_references
            is BaseSimulationScanConfig.default_block_references
        )

    def test_brian2_is_the_one_family_that_overrides_the_mapping(self):
        assert (
            Brian2CircuitSimulationSingleConfig.default_block_references
            is not BaseSimulationScanConfig.default_block_references
        )

    def test_the_two_roles_coincide_when_a_family_does_not_override(self, circuit_config, circuit):
        """Everywhere but Brian2, an untargeted stimulus drives whatever the simulation runs."""
        defaults = circuit_config().default_block_references(circuit)

        assert (
            defaults[ReferenceTag.STIMULUS_TARGET].block_name
            == defaults[ReferenceTag.SIMULATION_TARGET].block_name
        )

    def test_brian2_keeps_the_two_roles_apart(self, brian2_config, point_circuit):
        defaults = brian2_config().default_block_references(point_circuit)

        assert defaults[ReferenceTag.STIMULUS_TARGET].block_name == (
            DEFAULT_BRIAN2_STIMULUS_NODE_SET
        )
        assert defaults[ReferenceTag.SIMULATION_TARGET].block_name != (
            DEFAULT_BRIAN2_STIMULUS_NODE_SET
        )


SIMULATION_CONFIG_CLASSES = (
    CircuitSimulationSingleConfig,
    MEModelSimulationSingleConfig,
    Brian2CircuitSimulationSingleConfig,
    LearningEngineCircuitSimulationSingleConfig,
)


class TestTheDefaultNamesReachTheSchema:
    """What the UI shows as a placeholder has to be what generation will actually do."""

    @pytest.mark.parametrize("config_class", SIMULATION_CONFIG_CLASSES)
    def test_every_role_has_a_name(self, config_class):
        assert set(config_class.default_block_reference_names()) == set(ReferenceTag)

    @pytest.mark.parametrize("config_class", SIMULATION_CONFIG_CLASSES)
    def test_every_name_is_a_string(self, config_class):
        """A stray trailing comma turns one of these into a tuple, which the UI cannot show."""
        for tag, name in config_class.default_block_reference_names().items():
            assert isinstance(name, str), (tag, name)
            assert name

    @pytest.mark.parametrize("config_class", SIMULATION_CONFIG_CLASSES)
    def test_the_names_are_published_in_the_json_schema(self, config_class):
        published = config_class.model_json_schema()[SchemaKey.REFERENCE_TAG_DEFAULTS]

        assert published == config_class.default_block_reference_names()

    def test_the_names_agree_with_the_references_they_describe(self, circuit_config, circuit):
        """The anti-drift check: a shown placeholder naming a different block would be a lie."""
        config = circuit_config()
        names = config.default_block_reference_names()

        for tag, reference in config.default_block_references(circuit).items():
            assert reference.block_name == names[tag], tag
            assert reference.block.block_name == names[tag], tag

    def test_the_names_agree_for_brian2_too(self, brian2_config, point_circuit):
        """Brian2 is the family that overrides both, so it is where they could diverge."""
        config = brian2_config()
        names = config.default_block_reference_names()

        for tag, reference in config.default_block_references(point_circuit).items():
            assert reference.block_name == names[tag], tag

    def test_the_roles_the_task_does_not_fill_are_still_named(self, circuit_config, circuit):
        """The UI shows a placeholder for them even though a block, not the task, supplies it."""
        config = circuit_config()
        names = config.default_block_reference_names()
        filled = set(config.default_block_references(circuit))

        for tag in BLOCK_SUPPLIED_REFERENCE_TAGS:
            assert tag not in filled
            assert names[tag]

    def test_brian2_names_the_stimulus_and_simulation_roles_differently(self):
        """The distinction a type-keyed label cannot make: both are point neuron references."""
        names = Brian2CircuitSimulationSingleConfig.default_block_reference_names()

        assert names[ReferenceTag.STIMULUS_TARGET] == DEFAULT_BRIAN2_STIMULUS_NODE_SET
        assert names[ReferenceTag.SIMULATION_TARGET] != names[ReferenceTag.STIMULUS_TARGET]


class TestTheConfigOwnsItsSimulationTarget:
    """The other two things that vary by family, so the task needs no isinstance checks."""

    def test_only_brian2_skips_the_virtual_target_check(self):
        assert (
            Brian2CircuitSimulationSingleConfig.check_simulation_target
            is not BaseSimulationScanConfig.check_simulation_target
        )
        for config_class in (
            CircuitSimulationSingleConfig,
            MEModelSimulationSingleConfig,
            LearningEngineCircuitSimulationSingleConfig,
        ):
            assert (
                config_class.check_simulation_target
                is BaseSimulationScanConfig.check_simulation_target
            )

    def test_the_node_set_name_is_the_filled_target(self, circuit_config, tmp_path):
        config = circuit_config()

        generate(config, tmp_path)

        assert (
            config.simulation_node_set_name == CircuitSimulationSingleConfig.default_node_set_name
        )

    def test_a_config_with_no_target_to_choose_falls_back_to_its_default(self, me_model_config):
        """An ME model offers no target and holds no neuron sets, so the default names itself."""
        config = me_model_config()
        assert not hasattr(config.initialize, "node_set")

        assert (
            config.simulation_node_set_name == MEModelSimulationSingleConfig.default_node_set_name
        )

    def test_the_generated_config_records_that_node_set(self, circuit_config, tmp_path):
        config = circuit_config()

        result = generate(config, tmp_path)

        assert result.sonata_config["node_set"] == config.simulation_node_set_name


class TestTagValuesAreStable:
    """Tags are written into the published JSON schema, so their values are part of the contract."""

    def test_every_tag_value_is_its_lowercase_name(self):
        for tag in ReferenceTag:
            assert tag.value == tag.name.lower()

    def test_tags_reach_the_generated_json_schema(self):
        schema = obi.ConstantCurrentClampSomaticStimulus.model_json_schema()

        assert schema["properties"]["neuron_set"][SchemaKey.REFERENCE_TAG] == (
            ReferenceTag.STIMULUS_TARGET
        )
        assert schema["properties"]["timestamps"][SchemaKey.REFERENCE_TAG] == (
            ReferenceTag.TIMESTAMPS
        )


def test_no_block_config_method_still_takes_a_default_reference():
    """The defaults reach blocks through the fill, never as a ``config()`` argument any more."""
    offenders = []
    for cls in _all_block_subclasses():
        config_method = cls.__dict__.get("config")
        if config_method is None:
            continue
        offenders += [
            f"{cls.__name__}.config({name})"
            for name in inspect.signature(config_method).parameters
            if name.startswith("default_")
        ]

    assert offenders == []
