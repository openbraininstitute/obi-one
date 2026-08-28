"""Tests for neuronal manipulation block config() methods."""

from unittest.mock import MagicMock

from obi_one.scientific.blocks.neuronal_manipulations.neuronal_manipulations import (
    ByNeuronMechanismVariableNeuronalManipulation,
    ByNeuronModification,
    BySectionListMechanismVariableNeuronalManipulation,
    BySectionListModification,
    CircuitByNeuronMechanismVariableNeuronalManipulation,
    CircuitBySectionListMechanismVariableNeuronalManipulation,
)
from obi_one.scientific.tasks.generate_simulations.task.task import (
    GenerateSimulationTask,
)


class TestBySectionListMechanismVariableNeuronalManipulationConfig:
    """Tests for BySectionListMechanismVariableNeuronalManipulation.config()."""

    def test_config_with_somatic_section_list(self):
        """Config generates correct SONATA modification for somatic section list."""
        mod = BySectionListModification(
            variable_name="gNaTgbar_NaTg",
            section_list_modifications={"somatic": 0.1},
        )
        block = BySectionListMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        result = block.config(default_node_set="All")
        assert len(result) == 1
        assert result[0]["node_set"] == "All"
        assert result[0]["type"] == "section_list"
        assert "somatic.gNaTgbar_NaTg = 0.1" in result[0]["section_configure"]

    def test_config_with_all_section_list(self):
        """Config generates configure_all_sections for 'all' section list."""
        mod = BySectionListModification(
            variable_name="gkbar_hh",
            section_list_modifications={"all": 0.5},
        )
        block = BySectionListMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        result = block.config(default_node_set="All")
        assert len(result) == 1
        assert result[0]["type"] == "configure_all_sections"
        assert "%s.gkbar_hh = 0.5" in result[0]["section_configure"]

    def test_config_with_multiloc_alias(self):
        """Config expands multiloc aliases (e.g. 'alldend' → apical + basal)."""
        mod = BySectionListModification(
            variable_name="gkbar_hh",
            section_list_modifications={"alldend": 0.2},
        )
        block = BySectionListMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        result = block.config(default_node_set="All")
        assert len(result) == 2
        section_lists = [r["section_configure"].split(".")[0] for r in result]
        assert "apical" in section_lists
        assert "basal" in section_lists

    def test_config_with_multiple_section_lists(self):
        """Config generates entries for multiple section lists."""
        mod = BySectionListModification(
            variable_name="gkbar_hh",
            section_list_modifications={"somatic": 0.1, "axonal": 0.2},
        )
        block = BySectionListMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        result = block.config(default_node_set="All")
        assert len(result) == 2

    def test_config_with_neuron_set_ref(self):
        """Config resolves neuron_set reference to block_name."""
        mock_neuron_set = MagicMock()
        mock_neuron_set.block.block_name = "MyNeuronSet"
        mod = BySectionListModification(
            variable_name="gkbar_hh",
            section_list_modifications={"somatic": 0.1},
        )
        block = BySectionListMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        block.neuron_set = mock_neuron_set
        result = block.config(default_node_set="All")
        assert result[0]["node_set"] == "MyNeuronSet"

    def test_config_empty_modifications(self):
        """Empty section_list_modifications returns empty list."""
        mod = BySectionListModification(
            variable_name="gkbar_hh",
            section_list_modifications={},
        )
        block = BySectionListMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        result = block.config(default_node_set="All")
        assert result == []


class TestByNeuronMechanismVariableNeuronalManipulationConfig:
    """Tests for ByNeuronMechanismVariableNeuronalManipulation.config()."""

    def test_config_none_value_returns_empty(self):
        """When new_value is None, returns empty list."""
        mod = ByNeuronModification(
            variable_name="gNaTgbar_NaTg",
            variable_type="RANGE",
            new_value=None,
        )
        block = ByNeuronMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        result = block.config(default_node_set="All")
        assert result == []

    def test_config_range_variable(self):
        """RANGE variable generates configure_all_sections entry."""
        mod = ByNeuronModification(
            variable_name="gNaTgbar_NaTg",
            variable_type="RANGE",
            new_value=0.1,
        )
        block = ByNeuronMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        result = block.config(default_node_set="All")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["type"] == "configure_all_sections"
        assert "%s.gNaTgbar_NaTg = 0.1" in result[0]["section_configure"]
        assert result[0]["node_set"] == "All"

    def test_config_global_variable(self):
        """GLOBAL variable returns dict for conditions.mechanisms."""
        mod = ByNeuronModification(
            channel_name="StochKv3",
            variable_name="vmin_StochKv3",
            variable_type="GLOBAL",
            new_value=0.5,
        )
        block = ByNeuronMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        result = block.config(default_node_set="All")
        assert isinstance(result, dict)
        assert result == {"StochKv3": {"vmin_StochKv3": 0.5}}

    def test_config_range_with_neuron_set_ref(self):
        """RANGE variable resolves neuron_set reference."""
        mock_neuron_set = MagicMock()
        mock_neuron_set.block.block_name = "MyNeuronSet"
        mod = ByNeuronModification(
            variable_name="gNaTgbar_NaTg",
            variable_type="RANGE",
            new_value=0.1,
        )
        block = ByNeuronMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        block.neuron_set = mock_neuron_set
        result = block.config(default_node_set="All")
        assert result[0]["node_set"] == "MyNeuronSet"


class TestCircuitVariantsConfig:
    """Tests that Circuit variants inherit config() behavior correctly."""

    def test_circuit_by_section_list_config(self):
        """CircuitBySectionList variant produces same config as base."""
        mod = BySectionListModification(
            variable_name="gkbar_hh",
            section_list_modifications={"somatic": 0.1},
        )
        block = CircuitBySectionListMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        result = block.config(default_node_set="All")
        assert len(result) == 1
        assert result[0]["type"] == "section_list"

    def test_circuit_by_neuron_range_config(self):
        """CircuitByNeuron variant with RANGE produces same config as base."""
        mod = ByNeuronModification(
            variable_name="gNaTgbar_NaTg",
            variable_type="RANGE",
            new_value=0.1,
        )
        block = CircuitByNeuronMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        result = block.config(default_node_set="All")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["type"] == "configure_all_sections"

    def test_circuit_by_neuron_global_config(self):
        """CircuitByNeuron variant with GLOBAL produces dict."""
        mod = ByNeuronModification(
            channel_name="Ca_HVA2",
            variable_name="gCa_HVAbar_Ca_HVA2",
            variable_type="GLOBAL",
            new_value=0.3,
        )
        block = CircuitByNeuronMechanismVariableNeuronalManipulation(
            modification=mod,
        )
        result = block.config(default_node_set="All")
        assert result == {"Ca_HVA2": {"gCa_HVAbar_Ca_HVA2": 0.3}}


class TestGlobalMechanismsMerge:
    """Regression test: GLOBAL neuronal manipulation must merge into existing mechanisms dict.

    Before the fix, _add_sonata_simulation_config_manipulations replaced
    conditions["mechanisms"] entirely, wiping ProbAMPANMDA_EMS and ProbGABAAB_EMS.
    """

    def test_global_manipulation_merges_into_existing_mechanisms(self):
        """GLOBAL variable config is merged into conditions.mechanisms, not replaced."""
        # Build a mock config with a GLOBAL neuronal manipulation
        mod = ByNeuronModification(
            channel_name="NaTg",
            variable_name="vhalf_NaTg",
            variable_type="GLOBAL",
            new_value=-52.0,
        )
        block = ByNeuronMechanismVariableNeuronalManipulation(modification=mod)
        block.set_block_name("mod_NaTg")

        mock_config = MagicMock()
        mock_config.default_node_set_name = "All"
        mock_config.neuronal_manipulations = {"mod_NaTg": block}
        # No synaptic_manipulations attribute → hasattr returns False
        del mock_config.synaptic_manipulations

        # Call the method directly without instantiating the full Pydantic task
        sonata_config = {
            "conditions": {
                "mechanisms": {
                    "ProbAMPANMDA_EMS": {"init_depleted": True, "minis_single_vesicle": True},
                    "ProbGABAAB_EMS": {"init_depleted": True, "minis_single_vesicle": True},
                }
            }
        }
        GenerateSimulationTask._add_sonata_simulation_config_manipulations(
            type(
                "_FakeTask",
                (),
                {"config": mock_config, "_sonata_config": sonata_config},
            )()
        )

        mechanisms = sonata_config["conditions"]["mechanisms"]
        # Original entries must still be present
        assert "ProbAMPANMDA_EMS" in mechanisms
        assert "ProbGABAAB_EMS" in mechanisms
        # New GLOBAL variable must be added
        assert "NaTg" in mechanisms
        assert mechanisms["NaTg"] == {"vhalf_NaTg": -52.0}
