"""How manipulation blocks reach the generated SONATA config.

Synaptic manipulations become ``connection_overrides``; neuronal manipulations split between
``conditions.modifications`` (RANGE variables) and ``conditions.mechanisms`` (GLOBAL variables).
The split, the merge into pre-existing mechanisms, and the list ordering are all the task's
responsibility rather than the blocks'.
"""

import inspect
import typing

import pytest

import obi_one as obi
from obi_one.scientific.blocks.neuron_sets.id import BiophysicalPopulationIDNeuronSet
from obi_one.scientific.blocks.neuronal_manipulations.neuronal_manipulations import (
    ByNeuronMechanismVariableNeuronalManipulation,
    ByNeuronModification,
    BySectionListMechanismVariableNeuronalManipulation,
    BySectionListModification,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.unions_and_references.manipulations import SynapticManipulationsUnion
from obi_one.scientific.unions_and_references.neuronal_manipulations import (
    NeuronalManipulationReference,
    NeuronalManipulationUnion,
)

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    BIOPHYSICAL_POPULATION,
    DEFAULT_BIOPHYSICAL_NODE_SET,
    build_config,
    generate,
)

SYNAPTIC_MANIPULATIONS = {
    "SynapticMgManipulation": obi.SynapticMgManipulation(magnesium_value=2.4),
    "ScaleAcetylcholineUSESynapticManipulation": obi.ScaleAcetylcholineUSESynapticManipulation(
        use_scaling=0.7
    ),
    "ConnectSynapticManipulation": obi.ConnectSynapticManipulation(),
    "DisconnectSynapticManipulation": obi.DisconnectSynapticManipulation(),
}


def _union_member_names(union) -> set[str]:
    inner = typing.get_args(union)[0]
    if inspect.isclass(inner):
        return {inner.__name__}
    return {cls.__name__ for cls in typing.get_args(inner) if inspect.isclass(cls)}


class TestUnionCoverage:
    def test_every_synaptic_manipulation_is_exercised(self):
        assert _union_member_names(SynapticManipulationsUnion) == set(SYNAPTIC_MANIPULATIONS)

    def test_every_neuronal_manipulation_is_exercised(self):
        assert _union_member_names(NeuronalManipulationUnion) == {
            "BySectionListMechanismVariableNeuronalManipulation",
            "ByNeuronMechanismVariableNeuronalManipulation",
        }


class TestSynapticManipulations:
    def test_no_manipulations_means_no_connection_overrides_key(self, circuit_config, tmp_path):
        result = generate(circuit_config(), tmp_path)

        assert "connection_overrides" not in result.sonata_config

    def test_magnesium_manipulation(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Magnesium": obi.SynapticMgManipulation(magnesium_value=2.4)},
        )

        result = generate(config, tmp_path)

        assert result.sonata_config["connection_overrides"] == [
            {
                "name": "Magnesium",
                "source": DEFAULT_BIOPHYSICAL_NODE_SET,
                "target": DEFAULT_BIOPHYSICAL_NODE_SET,
                "modoverride": "GluSynapse",
                "synapse_configure": "mg = 2.4",
            }
        ]

    def test_acetylcholine_use_scaling(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Acetylcholine": obi.ScaleAcetylcholineUSESynapticManipulation(use_scaling=0.5)
            },
        )

        result = generate(config, tmp_path)

        assert result.sonata_config["connection_overrides"] == [
            {
                "name": "Acetylcholine",
                "source": DEFAULT_BIOPHYSICAL_NODE_SET,
                "target": DEFAULT_BIOPHYSICAL_NODE_SET,
                "synapse_configure": "%s.Use *= 0.5",
            }
        ]

    def test_connect_and_disconnect_emit_weighted_overrides(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Disconnect": obi.DisconnectSynapticManipulation(),
                "Connect": obi.ConnectSynapticManipulation(),
            },
        )

        result = generate(config, tmp_path)

        overrides = result.sonata_config["connection_overrides"]
        weights = {override["name"]: override.get("weight") for override in overrides}
        assert weights["Disconnect"] == pytest.approx(0.0)
        assert weights["Connect"] == pytest.approx(1.0)

    def test_pre_and_post_synaptic_targets_are_honoured(self, circuit, tmp_path):
        presynaptic = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="pre", elements=[0, 1]),
        )
        postsynaptic = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="post", elements=[2, 3]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Pre": presynaptic,
                "Post": postsynaptic,
                "Magnesium": lambda: obi.SynapticMgManipulation(
                    magnesium_value=2.0,
                    presynaptic_neuron_set=presynaptic.ref,
                    postsynaptic_neuron_set=postsynaptic.ref,
                ),
            },
        )

        result = generate(config, tmp_path)

        override = result.sonata_config["connection_overrides"][0]
        assert override["source"] == "Pre"
        assert override["target"] == "Post"

    def test_manipulations_keep_their_dictionary_order(self, circuit, tmp_path):
        """SONATA applies connection overrides in order, so the config order must survive."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Acetylcholine": obi.ScaleAcetylcholineUSESynapticManipulation(use_scaling=0.5),
                "Magnesium": obi.SynapticMgManipulation(magnesium_value=2.0),
                "Disconnect": obi.DisconnectSynapticManipulation(),
            },
        )

        result = generate(config, tmp_path)

        names = [override["name"] for override in result.sonata_config["connection_overrides"]]
        assert names == ["Acetylcholine", "Magnesium", "Disconnect"]


class TestNeuronalManipulations:
    """Neuronal manipulations live on the ME model config."""

    @staticmethod
    def _config(me_model_config, manipulations):
        return me_model_config(blocks=manipulations)

    def test_no_manipulations_leaves_conditions_untouched(self, me_model_config, tmp_path):
        result = generate(me_model_config(), tmp_path)

        assert "modifications" not in result.conditions
        assert "mechanisms" not in result.conditions

    def test_neuronal_manipulations_can_be_added_through_the_reference_api(self, me_model_config):
        """``NeuronalManipulationReference`` is registered, so ``ScanConfig.add`` routes a
        neuronal manipulation into the right block dictionary."""
        config = me_model_config()
        manipulation = ByNeuronMechanismVariableNeuronalManipulation(
            modification=ByNeuronModification(variable_name="cm", new_value=1.0)
        )

        config.add(manipulation, name="Capacitance")

        assert config.neuronal_manipulations == {"Capacitance": manipulation}
        assert isinstance(manipulation.ref, NeuronalManipulationReference)
        assert manipulation.ref.block_dict_name == "neuronal_manipulations"

    def test_range_variables_become_condition_modifications(self, me_model_config, tmp_path):
        config = self._config(
            me_model_config,
            {
                "Capacitance": BySectionListMechanismVariableNeuronalManipulation(
                    modification=BySectionListModification(
                        variable_name="cm",
                        section_list_modifications={"somatic": 1.5},
                    )
                )
            },
        )

        result = generate(config, tmp_path)

        assert result.conditions["modifications"] == [
            {
                "name": "modify_cm_somatic",
                "node_set": DEFAULT_BIOPHYSICAL_NODE_SET,
                "type": "section_list",
                "section_configure": "somatic.cm = 1.5",
            }
        ]
        assert "mechanisms" not in result.conditions

    def test_a_section_list_modification_expands_per_section_list(self, me_model_config, tmp_path):
        config = self._config(
            me_model_config,
            {
                "Capacitance": BySectionListMechanismVariableNeuronalManipulation(
                    modification=BySectionListModification(
                        variable_name="cm",
                        section_list_modifications={"somatic": 1.0, "axonal": 2.0},
                    )
                )
            },
        )

        result = generate(config, tmp_path)

        names = [entry["name"] for entry in result.conditions["modifications"]]
        assert names == ["modify_cm_somatic", "modify_cm_axonal"]

    def test_global_variables_become_condition_mechanisms(self, me_model_config, tmp_path):
        config = self._config(
            me_model_config,
            {
                "ChannelGlobal": ByNeuronMechanismVariableNeuronalManipulation(
                    modification=ByNeuronModification(
                        channel_name="StochKv3",
                        variable_name="vmin_StochKv3",
                        variable_type="GLOBAL",
                        new_value=0.5,
                    )
                )
            },
        )

        result = generate(config, tmp_path)

        assert result.conditions["mechanisms"] == {"StochKv3": {"vmin_StochKv3": 0.5}}
        assert "modifications" not in result.conditions

    def test_global_variables_for_one_channel_are_merged(self, me_model_config, tmp_path):
        config = self._config(
            me_model_config,
            {
                "First": ByNeuronMechanismVariableNeuronalManipulation(
                    modification=ByNeuronModification(
                        channel_name="StochKv3",
                        variable_name="vmin_StochKv3",
                        variable_type="GLOBAL",
                        new_value=0.5,
                    )
                ),
                "Second": ByNeuronMechanismVariableNeuronalManipulation(
                    modification=ByNeuronModification(
                        channel_name="StochKv3",
                        variable_name="vmax_StochKv3",
                        variable_type="GLOBAL",
                        new_value=1.5,
                    )
                ),
            },
        )

        result = generate(config, tmp_path)

        assert result.conditions["mechanisms"] == {
            "StochKv3": {"vmin_StochKv3": 0.5, "vmax_StochKv3": 1.5}
        }

    def test_by_neuron_range_variables_configure_all_sections(self, me_model_config, tmp_path):
        config = self._config(
            me_model_config,
            {
                "Resistance": ByNeuronMechanismVariableNeuronalManipulation(
                    modification=ByNeuronModification(
                        variable_name="Ra",
                        variable_type="RANGE",
                        new_value=120.0,
                    )
                )
            },
        )

        result = generate(config, tmp_path)

        assert result.conditions["modifications"] == [
            {
                "name": "modify_Ra_all",
                "node_set": DEFAULT_BIOPHYSICAL_NODE_SET,
                "type": "configure_all_sections",
                "section_configure": "%s.Ra = 120.0",
            }
        ]

    def test_range_and_global_manipulations_coexist(self, me_model_config, tmp_path):
        config = self._config(
            me_model_config,
            {
                "Range": ByNeuronMechanismVariableNeuronalManipulation(
                    modification=ByNeuronModification(
                        variable_name="Ra", variable_type="RANGE", new_value=100.0
                    )
                ),
                "Global": ByNeuronMechanismVariableNeuronalManipulation(
                    modification=ByNeuronModification(
                        channel_name="StochKv3",
                        variable_name="vmin_StochKv3",
                        variable_type="GLOBAL",
                        new_value=0.5,
                    )
                ),
            },
        )

        result = generate(config, tmp_path)

        assert len(result.conditions["modifications"]) == 1
        assert result.conditions["mechanisms"] == {"StochKv3": {"vmin_StochKv3": 0.5}}

    def test_a_manipulation_without_a_new_value_contributes_nothing(
        self, me_model_config, tmp_path
    ):
        config = self._config(
            me_model_config,
            {
                "Unset": ByNeuronMechanismVariableNeuronalManipulation(
                    modification=ByNeuronModification(
                        channel_name="StochKv3",
                        variable_name="vmin_StochKv3",
                        variable_type="GLOBAL",
                        new_value=None,
                    )
                )
            },
        )

        result = generate(config, tmp_path)

        assert "modifications" not in result.conditions
        assert "mechanisms" not in result.conditions

    def test_a_circuit_config_keeps_its_synapse_mechanisms(
        self, me_model_with_synapses_config, tmp_path
    ):
        """A circuit-derived config already has ``conditions.mechanisms`` from the base config."""
        result = generate(me_model_with_synapses_config(), tmp_path)

        assert set(result.conditions["mechanisms"]) == {"ProbAMPANMDA_EMS", "ProbGABAAB_EMS"}
