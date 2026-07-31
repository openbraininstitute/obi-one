"""How neuron set blocks reach the generated ``node_sets.json``.

Two things are covered here. First, every neuron set type accepted by a simulation config
resolves into a node set definition under the key it was registered with. Second, the rules the
task applies when a neuron set reference is left unset -- which default gets injected, and when
that is an error.
"""

import inspect
import typing

import pytest

import obi_one as obi
from obi_one.core.exception import OBIONEError
from obi_one.scientific.blocks.neuron_sets.combined import SetOperation
from obi_one.scientific.blocks.neuron_sets.deprecated import AllNeurons
from obi_one.scientific.blocks.neuron_sets.id import (
    BiophysicalPopulationIDNeuronSet,
    PointPopulationIDNeuronSet,
    VirtualPopulationIDNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.population import (
    BiophysicalPopulationNeuronSet,
    PointPopulationNeuronSet,
    VirtualPopulationNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.predefined import (
    BiophysicalPopulationPredefinedNeuronSet,
    PointPopulationPredefinedNeuronSet,
    VirtualPopulationPredefinedNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.property import (
    BiophysicalPopulationPropertyNeuronSet,
    NeuronPropertyFilter,
    PointPopulationPropertyNeuronSet,
    VirtualPopulationPropertyNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllBiophysicalNeurons,
    AllPointNeurons,
    AllVirtualNeurons,
)
from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_circuit import (
    Brian2CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.learning_engine.le_circuit import (
    LearningEngineCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    NEURONSimulationNeuronSetUnion,
)
from obi_one.scientific.unions_and_references.neuron_sets import (
    BiophysicalNeuronSetReference,
    PointNeuronSetReference,
    VirtualNeuronSetReference,
)

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    BIOPHYSICAL_POPULATION,
    DEFAULT_BIOPHYSICAL_NODE_SET,
    DEFAULT_POINT_NODE_SET,
    DEFAULT_VIRTUAL_NODE_SET,
    POINT_POPULATION,
    VIRTUAL_POPULATION,
    build_config,
    generate,
)


def _union_member_names(union) -> set[str]:
    """The class names a discriminated block union accepts."""
    inner = typing.get_args(union)[0]
    return {cls.__name__ for cls in typing.get_args(inner) if inspect.isclass(cls)}


# One constructible instance per neuron set type in NEURONSimulationNeuronSetUnion. Combined sets
# are exercised separately because they need references to other sets, and the deprecated sets
# have their own test because they refuse to resolve at all.
BIOPHYSICAL_NEURON_SETS = {
    "AllBiophysicalNeurons": AllBiophysicalNeurons(),
    "BiophysicalPopulationNeuronSet": BiophysicalPopulationNeuronSet(
        population=BIOPHYSICAL_POPULATION,
    ),
    "BiophysicalPopulationIDNeuronSet": BiophysicalPopulationIDNeuronSet(
        population=BIOPHYSICAL_POPULATION,
        neuron_ids=obi.NamedTuple(name="ids", elements=[0, 1]),
    ),
    "BiophysicalPopulationPredefinedNeuronSet": BiophysicalPopulationPredefinedNeuronSet(
        population=BIOPHYSICAL_POPULATION,
        node_set="Excitatory",
    ),
    "BiophysicalPopulationPropertyNeuronSet": BiophysicalPopulationPropertyNeuronSet(
        population=BIOPHYSICAL_POPULATION,
        property_filter=NeuronPropertyFilter(filter_dict={"synapse_class": ["EXC"]}),
    ),
}

VIRTUAL_NEURON_SETS = {
    "VirtualPopulationNeuronSet": VirtualPopulationNeuronSet(population=VIRTUAL_POPULATION),
    "VirtualPopulationIDNeuronSet": VirtualPopulationIDNeuronSet(
        population=VIRTUAL_POPULATION,
        neuron_ids=obi.NamedTuple(name="ids", elements=[0, 1, 2]),
    ),
    "VirtualPopulationPredefinedNeuronSet": VirtualPopulationPredefinedNeuronSet(
        population=VIRTUAL_POPULATION,
        node_set="proj_Thalamocortical_VPM_Source",
    ),
    "VirtualPopulationPropertyNeuronSet": VirtualPopulationPropertyNeuronSet(
        population=VIRTUAL_POPULATION,
        property_filter=NeuronPropertyFilter(filter_dict={"model_type": ["virtual"]}),
    ),
}

POINT_NEURON_SETS = {
    "AllPointNeurons": AllPointNeurons(),
    "PointPopulationNeuronSet": PointPopulationNeuronSet(population=POINT_POPULATION),
    "PointPopulationIDNeuronSet": PointPopulationIDNeuronSet(
        population=POINT_POPULATION,
        neuron_ids=obi.NamedTuple(name="ids", elements=[0, 1]),
    ),
    "PointPopulationPredefinedNeuronSet": PointPopulationPredefinedNeuronSet(
        population=POINT_POPULATION,
        node_set="sugar",
    ),
    "PointPopulationPropertyNeuronSet": PointPopulationPropertyNeuronSet(
        population=POINT_POPULATION,
        property_filter=NeuronPropertyFilter(filter_dict={"model_type": ["brian2_point"]}),
    ),
}

# Kept for backwards compatibility with stored configs; every resolution method raises.
DEPRECATED_NEURON_SETS = {
    "AllNeurons": AllNeurons(),
    "ExcitatoryNeurons": obi.ExcitatoryNeurons(),
    "InhibitoryNeurons": obi.InhibitoryNeurons(),
    "IDNeuronSet": obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="ids", elements=[0, 1, 2])),
    "PredefinedNeuronSet": obi.PredefinedNeuronSet(node_set="Excitatory"),
    "nbS1VPMInputs": obi.nbS1VPMInputs(),
    "nbS1POmInputs": obi.nbS1POmInputs(),
    "rCA1CA3Inputs": obi.rCA1CA3Inputs(),
}

COMBINED_NEURON_SETS = {
    "BiophysicalCombinedNeuronSet",
    "VirtualCombinedNeuronSet",
    "PointCombinedNeuronSet",
    "NonVirtualCombinedNeuronSet",
}


class TestUnionCoverage:
    """Guards against a new neuron set type slipping in untested."""

    def test_every_neuron_simulation_neuron_set_is_exercised(self):
        covered = (
            set(BIOPHYSICAL_NEURON_SETS)
            | set(VIRTUAL_NEURON_SETS)
            | set(POINT_NEURON_SETS)
            | set(DEPRECATED_NEURON_SETS)
            | COMBINED_NEURON_SETS
        )

        assert _union_member_names(NEURONSimulationNeuronSetUnion) - covered == set()

    def test_all_virtual_neurons_is_not_selectable(self, circuit_config):
        """``AllVirtualNeurons`` only exists as the injected default, not as a user choice."""
        with pytest.raises(KeyError, match="AllVirtualNeurons"):
            circuit_config().add(AllVirtualNeurons(), name="Virtual")


class TestNeuronSetsReachNodeSetsFile:
    @pytest.mark.parametrize("name", sorted(BIOPHYSICAL_NEURON_SETS))
    def test_biophysical_neuron_set_is_written(self, name, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={name: BIOPHYSICAL_NEURON_SETS[name].model_copy(deep=True)},
        )

        result = generate(config, tmp_path)

        assert name in result.node_sets

    @pytest.mark.parametrize("name", sorted(VIRTUAL_NEURON_SETS))
    def test_virtual_neuron_set_is_written(self, name, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={name: VIRTUAL_NEURON_SETS[name].model_copy(deep=True)},
        )

        result = generate(config, tmp_path)

        assert name in result.node_sets

    @pytest.mark.parametrize("name", sorted(POINT_NEURON_SETS))
    def test_point_neuron_set_is_written(self, name, point_circuit, tmp_path):
        config = build_config(
            Brian2CircuitSimulationSingleConfig,
            circuit=point_circuit,
            blocks={name: POINT_NEURON_SETS[name].model_copy(deep=True)},
        )

        result = generate(config, tmp_path)

        assert name in result.node_sets

    @pytest.mark.parametrize("name", sorted(DEPRECATED_NEURON_SETS))
    def test_deprecated_neuron_set_refuses_to_resolve(self, name, circuit, tmp_path):
        """The deprecated sets stay loadable for old configs but cannot be generated from."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={name: DEPRECATED_NEURON_SETS[name].model_copy(deep=True)},
        )

        with pytest.raises(NotImplementedError, match=f"{name} is deprecated"):
            generate(config, tmp_path)

    def test_node_set_is_named_after_the_dictionary_key_not_the_block(self, circuit, tmp_path):
        """A predefined set is re-published under its key, so behaviour matches a subsampled set."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "MyExcitatory": BiophysicalPopulationPredefinedNeuronSet(
                    population=BIOPHYSICAL_POPULATION, node_set="Excitatory"
                )
            },
        )

        result = generate(config, tmp_path)

        assert "MyExcitatory" in result.node_sets
        assert result.node_sets["MyExcitatory"] != {}

    def test_id_neuron_set_resolves_to_explicit_node_ids(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Three": BiophysicalPopulationIDNeuronSet(
                    population=BIOPHYSICAL_POPULATION,
                    neuron_ids=obi.NamedTuple(name="ids", elements=[0, 1, 2]),
                )
            },
        )

        result = generate(config, tmp_path)

        assert result.node_sets["Three"] == {
            "population": BIOPHYSICAL_POPULATION,
            "node_id": [0, 1, 2],
        }

    def test_sampling_reduces_the_resolved_ids(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Half": BiophysicalPopulationIDNeuronSet(
                    population=BIOPHYSICAL_POPULATION,
                    neuron_ids=obi.NamedTuple(name="ids", elements=list(range(10))),
                    sample_percentage=50.0,
                    sample_seed=1,
                )
            },
        )

        result = generate(config, tmp_path)

        assert len(result.node_sets["Half"]["node_id"]) == 5

    def test_several_neuron_sets_coexist(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Excitatory subset": BiophysicalPopulationPredefinedNeuronSet(
                    population=BIOPHYSICAL_POPULATION, node_set="Excitatory"
                ),
                "VPM inputs": VirtualPopulationNeuronSet(population=VIRTUAL_POPULATION),
                "Everything biophysical": AllBiophysicalNeurons(),
            },
        )

        result = generate(config, tmp_path)

        assert {"Excitatory subset", "VPM inputs", "Everything biophysical"} <= set(
            result.node_sets
        )

    def test_key_must_match_the_block_name(self, circuit, tmp_path):
        """The dictionary key is authoritative; a drifting block name is refused.

        Constructing the task revalidates the config, which resets every block name to its key --
        so the rename has to happen after the task exists for the guard to be reachable.
        """
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Correct": AllBiophysicalNeurons()},
        )
        coordinate_root = tmp_path / "0"
        coordinate_root.mkdir(parents=True)
        config.scan_output_root = tmp_path
        config.coordinate_output_root = coordinate_root

        task = GenerateSimulationTask(config=config)
        task.config.neuron_sets["Correct"].set_block_name("Renamed")

        with pytest.raises(OBIONEError, match="Neuron set name mismatch!"):
            task.execute()


class TestCombinedNeuronSets:
    def test_union_of_two_id_sets(self, circuit, tmp_path):
        first = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="first", elements=[0, 1]),
        )
        second = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="second", elements=[2, 3]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "First": first,
                "Second": second,
                "Combined": lambda: obi.BiophysicalCombinedNeuronSet(
                    base_neuron_set=first.ref,
                    combined_with=((second.ref, SetOperation.UNION),),
                ),
            },
        )

        result = generate(config, tmp_path)

        assert result.node_sets["Combined"]["node_id"] == [0, 1, 2, 3]

    def test_intersection_and_difference(self, circuit, tmp_path):
        first = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="first", elements=[0, 1, 2]),
        )
        second = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="second", elements=[1, 2, 3]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "First": first,
                "Second": second,
                "Intersection": lambda: obi.BiophysicalCombinedNeuronSet(
                    base_neuron_set=first.ref,
                    combined_with=((second.ref, SetOperation.INTERSECT),),
                ),
                "Difference": lambda: obi.BiophysicalCombinedNeuronSet(
                    base_neuron_set=first.ref,
                    combined_with=((second.ref, SetOperation.DIFF),),
                ),
            },
        )

        result = generate(config, tmp_path)

        assert result.node_sets["Intersection"]["node_id"] == [1, 2]
        assert result.node_sets["Difference"]["node_id"] == [0]

    def test_unset_base_and_operand_fall_back_to_the_matching_default(self, circuit, tmp_path):
        """An empty combined set is filled with the default for its own population type."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Combined": obi.BiophysicalCombinedNeuronSet(
                    base_neuron_set=None,
                    combined_with=((None, SetOperation.UNION),),
                )
            },
        )

        generate(config, tmp_path)

        combined = config.neuron_sets["Combined"]
        assert combined.base_neuron_set.block_name == DEFAULT_BIOPHYSICAL_NODE_SET
        assert combined.combined_with[0][0].block_name == DEFAULT_BIOPHYSICAL_NODE_SET

    def test_virtual_combined_set_falls_back_to_the_virtual_default(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Combined": obi.VirtualCombinedNeuronSet(
                    base_neuron_set=None,
                    combined_with=(),
                )
            },
        )

        result = generate(config, tmp_path)

        assert config.neuron_sets["Combined"].base_neuron_set.block_name == (
            DEFAULT_VIRTUAL_NODE_SET
        )
        assert DEFAULT_VIRTUAL_NODE_SET in result.node_sets

    def test_point_combined_set_falls_back_to_the_point_default(self, point_circuit, tmp_path):
        """A NEURON config running a point circuit picks up the point default, not the
        biophysical one."""
        target = PointPopulationNeuronSet(population=POINT_POPULATION)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=point_circuit,
            blocks={
                "Target": target,
                "Combined": obi.PointCombinedNeuronSet(base_neuron_set=None, combined_with=()),
            },
        )
        config.initialize.node_set = config.neuron_sets["Target"].ref

        result = generate(config, tmp_path)

        assert config.neuron_sets["Combined"].base_neuron_set.block_name == DEFAULT_POINT_NODE_SET
        assert DEFAULT_POINT_NODE_SET in result.node_sets

    def test_brian2_point_combined_set_falls_back_to_the_point_default(
        self, point_circuit, tmp_path
    ):
        """Brian2's own default is already all point neurons, so the two coincide here."""
        config = build_config(
            Brian2CircuitSimulationSingleConfig,
            circuit=point_circuit,
            blocks={"Combined": obi.PointCombinedNeuronSet(base_neuron_set=None, combined_with=())},
        )

        result = generate(config, tmp_path)

        assert config.neuron_sets["Combined"].base_neuron_set.block_name == DEFAULT_POINT_NODE_SET
        assert DEFAULT_POINT_NODE_SET in result.node_sets

    def test_learning_engine_point_combined_set_falls_back_to_the_point_default(
        self, point_circuit, tmp_path
    ):
        config = build_config(
            LearningEngineCircuitSimulationSingleConfig,
            circuit=point_circuit,
            blocks={"Combined": obi.PointCombinedNeuronSet(base_neuron_set=None, combined_with=())},
        )

        result = generate(config, tmp_path)

        assert config.neuron_sets["Combined"].base_neuron_set.block_name == DEFAULT_POINT_NODE_SET
        assert DEFAULT_POINT_NODE_SET in result.node_sets

    def test_explicit_references_are_left_alone(self, circuit, tmp_path):
        explicit = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="ids", elements=[4]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Explicit": explicit,
                "Combined": lambda: obi.BiophysicalCombinedNeuronSet(
                    base_neuron_set=explicit.ref, combined_with=()
                ),
            },
        )

        generate(config, tmp_path)

        assert config.neuron_sets["Combined"].base_neuron_set.block_name == "Explicit"


class TestDefaultNeuronSetInjection:
    def test_default_is_created_on_demand_and_added_to_the_config(self, circuit_config, tmp_path):
        config = circuit_config()

        result = generate(config, tmp_path)

        assert isinstance(config.neuron_sets[DEFAULT_BIOPHYSICAL_NODE_SET], AllBiophysicalNeurons)
        assert result.node_sets[DEFAULT_BIOPHYSICAL_NODE_SET] == {
            "population": BIOPHYSICAL_POPULATION,
            "node_id": list(range(10)),
        }

    def test_untargeted_stimulus_and_recording_get_the_default(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Clamp": obi.ConstantCurrentClampSomaticStimulus(),
                "Voltage": obi.SomaVoltageRecording(),
            },
        )

        result = generate(config, tmp_path)

        assert config.stimuli["Clamp"].neuron_set.block_name == DEFAULT_BIOPHYSICAL_NODE_SET
        assert config.recordings["Voltage"].neuron_set.block_name == DEFAULT_BIOPHYSICAL_NODE_SET
        assert result.inputs["Clamp_0"]["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET
        assert result.reports["Voltage"]["cells"] == DEFAULT_BIOPHYSICAL_NODE_SET

    def test_explicit_targets_are_preserved(self, circuit, tmp_path):
        target = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="ids", elements=[0, 1]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Target": target,
                "Clamp": lambda: obi.ConstantCurrentClampSomaticStimulus(neuron_set=target.ref),
                "Voltage": lambda: obi.SomaVoltageRecording(neuron_set=target.ref),
            },
        )

        result = generate(config, tmp_path)

        assert result.inputs["Clamp_0"]["node_set"] == "Target"
        assert result.reports["Voltage"]["cells"] == "Target"

    def test_simulation_target_defaults_when_node_set_is_unset(self, circuit_config, tmp_path):
        config = circuit_config()
        assert config.initialize.node_set is None

        result = generate(config, tmp_path)

        assert config.initialize.node_set.block_name == DEFAULT_BIOPHYSICAL_NODE_SET
        assert result.sonata_config["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET

    def test_explicit_simulation_target_is_used(self, circuit, tmp_path):
        target = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="ids", elements=[0, 1]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Target": target},
        )
        config.initialize.node_set = config.neuron_sets["Target"].ref

        result = generate(config, tmp_path)

        assert result.sonata_config["node_set"] == "Target"

    def test_me_model_without_a_neuron_sets_dictionary_uses_the_default_name(
        self, me_model_config, tmp_path
    ):
        """An ME model config has no ``neuron_sets`` field, so the default is created inline."""
        config = me_model_config()
        assert not hasattr(config, "neuron_sets")

        result = generate(config, tmp_path)

        assert result.sonata_config["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET
        assert DEFAULT_BIOPHYSICAL_NODE_SET in result.node_sets


class TestDefaultNeuronSetErrors:
    def test_virtual_simulation_target_is_rejected(self, circuit, tmp_path):
        """The simulation itself cannot run a virtual population."""
        virtual = VirtualPopulationIDNeuronSet(
            population=VIRTUAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="ids", elements=[0, 1]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"VirtualTarget": virtual},
        )
        config.initialize.node_set = config.neuron_sets["VirtualTarget"].ref

        with pytest.raises(OBIONEError, match="'VirtualTarget' is virtual"):
            generate(config, tmp_path)

    def test_virtual_target_error_lists_the_usable_populations(self, circuit, tmp_path):
        virtual = VirtualPopulationIDNeuronSet(
            population=VIRTUAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="ids", elements=[0]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"VirtualTarget": virtual},
        )
        config.initialize.node_set = config.neuron_sets["VirtualTarget"].ref

        with pytest.raises(OBIONEError, match=f"'{BIOPHYSICAL_POPULATION}'"):
            generate(config, tmp_path)

    def test_reusing_the_default_name_for_another_type_is_rejected(self, circuit, tmp_path):
        """The default name is reserved: a user set under it must be the default type."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                DEFAULT_BIOPHYSICAL_NODE_SET: obi.PredefinedNeuronSet(node_set="Excitatory"),
                "Clamp": obi.ConstantCurrentClampSomaticStimulus(),
            },
        )

        with pytest.raises(OBIONEError, match="already exists in neuron_sets but is not an"):
            generate(config, tmp_path)

    def test_reusing_the_virtual_default_name_for_another_type_is_rejected(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                DEFAULT_VIRTUAL_NODE_SET: VirtualPopulationIDNeuronSet(
                    population=VIRTUAL_POPULATION,
                    neuron_ids=obi.NamedTuple(name="ids", elements=[0]),
                ),
                "Combined": obi.VirtualCombinedNeuronSet(base_neuron_set=None, combined_with=()),
            },
        )

        with pytest.raises(OBIONEError, match="Default virtual neuron set name"):
            generate(config, tmp_path)

    def test_reusing_the_point_default_name_for_another_type_is_rejected(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                DEFAULT_POINT_NODE_SET: PointPopulationIDNeuronSet(
                    population=POINT_POPULATION,
                    neuron_ids=obi.NamedTuple(name="ids", elements=[0]),
                ),
                "Combined": obi.PointCombinedNeuronSet(base_neuron_set=None, combined_with=()),
            },
        )

        with pytest.raises(OBIONEError, match="Default point neuron set name"):
            generate(config, tmp_path)


class TestDefaultReferenceTypes:
    """The reference each config family hands out for its default neuron set."""

    def test_circuit_default_is_biophysical(self, circuit_config):
        reference = circuit_config().default_neuron_set_reference

        assert isinstance(reference, BiophysicalNeuronSetReference)
        assert reference.block_name == DEFAULT_BIOPHYSICAL_NODE_SET
        assert isinstance(reference.block, AllBiophysicalNeurons)

    def test_circuit_virtual_and_point_defaults(self, circuit_config):
        config = circuit_config()

        assert isinstance(config.default_virtual_neuron_set_reference, VirtualNeuronSetReference)
        assert isinstance(config.default_point_neuron_set_reference, PointNeuronSetReference)
        assert isinstance(config.default_virtual_neuron_set_reference.block, AllVirtualNeurons)
        assert isinstance(config.default_point_neuron_set_reference.block, AllPointNeurons)

    def test_brian2_default_is_point(self, brian2_config):
        reference = brian2_config().default_neuron_set_reference

        assert isinstance(reference, PointNeuronSetReference)
        assert reference.block_name == DEFAULT_POINT_NODE_SET
        assert isinstance(reference.block, AllPointNeurons)

    def test_learning_engine_default_is_point(self, learning_engine_config):
        reference = learning_engine_config().default_neuron_set_reference

        assert isinstance(reference, PointNeuronSetReference)
        assert reference.block_name == DEFAULT_POINT_NODE_SET
