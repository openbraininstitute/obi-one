"""End-to-end tests for SynapseParameterizationTask.execute against a local circuit.

Mirrors the circuit-extraction task tests: run the task on a tiny local circuit with no
db_client, so the parameterization/output path is exercised while the entitycore
registration branch (which needs a db_client and a parent entity) is skipped.
"""

import bluepysnap as snap
import pytest

import obi_one as obi
from obi_one.core.schema import SchemaKey
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.tasks.synapse_parameterization.config import DEFAULT_SYNAPTIC_MODEL_NAME
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag

from tests.utils import CIRCUIT_DIR

# Intrinsic biophysical -> biophysical edge population of the tiny test circuit.
EDGE_POPULATION_NAME = "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical"


def _local_circuit():
    return obi.Circuit(
        name="N_10__top_nodes_dim6",
        path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
    )


def _build_config(tmp_path):
    """A minimal single-config: one excitatory model applied to every synapse."""
    config = obi.SynapseParameterizationSingleConfig.empty_config()
    config.set(
        obi.Info(campaign_name="Test", campaign_description="Test parameterization"),
        name="info",
    )
    config.set(config.Initialize(circuit=_local_circuit()), name="initialize")

    conductance = obi.GammaDistribution(shape=4.0, scale=0.25)
    config.add(conductance, "Excitatory conductance distribution")
    model = obi.ExcitatoryTsodyksMarkramSynapticModel(conductance_distribution=conductance.ref)
    config.add(model, "Excitatory synaptic model")
    config.add(
        obi.AllPairsSynapticModelAssigner(
            edge_population_name=EDGE_POPULATION_NAME,
            synaptic_model=model.ref,
        ),
        name="all_pairs",
    )
    config.fill_block_references_and_names()

    config.scan_output_root = tmp_path / "scan"
    config.coordinate_output_root = tmp_path / "scan" / "parameterized"
    return config


@pytest.mark.filterwarnings("ignore::FutureWarning")
def test_execute_parameterizes_local_circuit(tmp_path):
    config = _build_config(tmp_path)

    result = obi.SynapseParameterizationTask(config=config).execute(db_client=None)

    # Local circuit has no parent entity, so nothing is registered and no id is returned.
    assert result is None

    # The parameterized circuit is written to the coordinate output directory.
    output_config = config.coordinate_output_root / "circuit_config.json"
    assert output_config.exists()

    result_circuit = snap.Circuit(str(output_config))

    # The output is a full copy of the circuit, not just the modified edge file: every
    # edge population of the source survives, including the ones no assigner touched.
    source = _local_circuit().sonata_circuit
    assert set(result_circuit.edges.population_names) == set(source.edges.population_names)

    edges = result_circuit.edges[EDGE_POPULATION_NAME]

    # Every Tsodyks-Markram parameter is present on the edge population.
    for parameter in ExcitatoryTsodyksMarkramSynapticModel.parameter_names():
        assert parameter in edges.property_names

    # Every synapse carries the excitatory model's syn_type_id (the all-pairs assigner).
    expected_syn_type_id = ExcitatoryTsodyksMarkramSynapticModel().syn_type_id
    syn_type_ids = set(edges.get(edges.ids(), properties=["syn_type_id"])["syn_type_id"])
    assert syn_type_ids == {expected_syn_type_id}


def test_execute_rejects_output_dir_that_already_exists(tmp_path):
    """Running twice into the same coordinate output must not silently overwrite."""
    config = _build_config(tmp_path)

    with pytest.warns(FutureWarning):
        obi.SynapseParameterizationTask(config=config).execute(db_client=None)

    # A second run against the same output directory fails rather than clobbering it.
    with pytest.raises(FileExistsError):
        obi.SynapseParameterizationTask(config=config).execute(db_client=None)


def _unset_config(tmp_path):
    """A config that names no synaptic model or distributions: everything relies on defaults.

    The assigner's synaptic_model is left unset, so nothing but the edge population and the
    circuit is specified. This is the shape a config takes when the user accepts every default.
    """
    config = obi.SynapseParameterizationSingleConfig.empty_config()
    config.set(
        obi.Info(campaign_name="Test", campaign_description="Test defaults"),
        name="info",
    )
    config.set(config.Initialize(circuit=_local_circuit()), name="initialize")
    config.add(
        obi.AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
        name="all_pairs",
    )
    config.fill_block_references_and_names()
    config.scan_output_root = tmp_path / "scan"
    config.coordinate_output_root = tmp_path / "scan" / "parameterized"
    return config


def test_fill_materializes_defaults_under_resolved_names():
    """Filling an unset config materializes each default as a "Resolved Default: ..." block.

    The schema still advertises the unset field's default as "Default: ..."; the materialized
    block takes the distinct "Resolved Default: ..." name so a reloaded config shows it as its
    own entry rather than as the implicit default. The assigner's reference points at the
    resolved name and survives a serialize/reload round-trip.
    """
    config = obi.SynapseParameterizationScanConfig.empty_config()
    config.set(
        obi.Info(campaign_name="Test", campaign_description="Test defaults"),
        name="info",
    )
    config.set(config.Initialize(circuit=_local_circuit()), name="initialize")
    config.add(
        obi.AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
        name="all_pairs",
    )
    config.fill_block_references_and_names()

    # The schema label for the unset field stays "Default: ...".
    schema_defaults = obi.SynapseParameterizationScanConfig.model_config["json_schema_extra"][
        SchemaKey.REFERENCE_TAG_DEFAULTS
    ]
    assert schema_defaults[ReferenceTag.SYNAPTIC_MODEL]["name"] == DEFAULT_SYNAPTIC_MODEL_NAME
    assert DEFAULT_SYNAPTIC_MODEL_NAME.startswith("Default: ")

    config.fill_none_references()

    # The materialized blocks take the "Resolved Default: ..." name.
    assert list(config.synaptic_models) == ["Resolved Default: Excitatory Tsodyks-Markram"]
    assert config.distributions
    assert all(name.startswith("Resolved Default: ") for name in config.distributions)

    # The assigner's reference now points at the resolved block, and resolves on reload.
    reloaded = obi.SynapseParameterizationScanConfig.model_validate(config.model_dump(mode="json"))
    assigner = reloaded.synapse_model_assigners["all_pairs"]
    assert assigner.synaptic_model.block_name == "Resolved Default: Excitatory Tsodyks-Markram"
    assert isinstance(assigner.synaptic_model.block, ExcitatoryTsodyksMarkramSynapticModel)


def test_execute_rejects_a_config_with_no_assigners(tmp_path):
    """A config with no assigners parameterizes nothing and must be rejected, not run silently."""
    config = obi.SynapseParameterizationSingleConfig.empty_config()
    config.set(
        obi.Info(campaign_name="Test", campaign_description="Test empty"),
        name="info",
    )
    config.set(config.Initialize(circuit=_local_circuit()), name="initialize")
    config.fill_block_references_and_names()
    config.scan_output_root = tmp_path / "scan"
    config.coordinate_output_root = tmp_path / "scan" / "parameterized"

    with pytest.raises(ValueError, match="No synaptic model assigners"):
        obi.SynapseParameterizationTask(config=config).execute(db_client=None)


@pytest.mark.filterwarnings("ignore::FutureWarning")
def test_execute_parameterizes_a_defaults_only_config(tmp_path):
    """A config naming no synaptic model parameterizes from the resolved defaults.

    Defaults are materialized by the generation step (mirrored here by calling
    fill_none_references before execute), so by the time the task runs the assigner's
    synaptic model and its distributions are in place.
    """
    config = _unset_config(tmp_path)
    config.fill_none_references()  # done by ScanGenerationTask before serialization

    obi.SynapseParameterizationTask(config=config).execute(db_client=None)

    output_config = config.coordinate_output_root / "circuit_config.json"
    edges = snap.Circuit(str(output_config)).edges[EDGE_POPULATION_NAME]

    # All parameters were written, from the resolved default model.
    for parameter in ExcitatoryTsodyksMarkramSynapticModel.parameter_names():
        assert parameter in edges.property_names

    expected_syn_type_id = ExcitatoryTsodyksMarkramSynapticModel().syn_type_id
    syn_type_ids = set(edges.get(edges.ids(), properties=["syn_type_id"])["syn_type_id"])
    assert syn_type_ids == {expected_syn_type_id}


def _defaults_only_scan_config(*assigner_names):
    """A scan config whose assigners all rely on the default synaptic model."""
    config = obi.SynapseParameterizationScanConfig.empty_config()
    config.set(
        obi.Info(campaign_name="Test", campaign_description="Test reload"),
        name="info",
    )
    config.set(config.Initialize(circuit=_local_circuit()), name="initialize")
    for name in assigner_names:
        config.add(
            obi.AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
            name=name,
        )
    config.fill_block_references_and_names()
    return config


def _reload(config):
    """Round-trip a config through JSON the way a stored campaign is loaded back."""
    return obi.SynapseParameterizationScanConfig.model_validate(config.model_dump(mode="json"))


def test_fill_shares_one_resolved_default_across_assigners():
    """Two assigners relying on the default resolve to a single materialized block, not two."""
    config = _defaults_only_scan_config("a", "b")
    config.fill_none_references()

    assert list(config.synaptic_models) == ["Resolved Default: Excitatory Tsodyks-Markram"]
    assert len(config.distributions) == len(
        ExcitatoryTsodyksMarkramSynapticModel.default_distributions_by_tag()
    )
    resolved_name = "Resolved Default: Excitatory Tsodyks-Markram"
    assert config.synapse_model_assigners["a"].synaptic_model.block_name == resolved_name
    assert config.synapse_model_assigners["b"].synaptic_model.block_name == resolved_name


def test_fill_reuses_a_reloaded_resolved_default_rather_than_stacking():
    """Adding an assigner to a reloaded campaign reuses its resolved default, not a duplicate.

    The stored campaign already carries a fully materialized "Resolved Default: ..." model and
    its distributions. Filling again for a newly added assigner must recognize the same default
    and point at it, rather than materializing a second identical "Resolved (1) Default: ..."
    block.
    """
    stored = _defaults_only_scan_config("all_pairs")
    stored.fill_none_references()

    reloaded = _reload(stored)
    reloaded.add(
        obi.AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
        name="all_pairs_2",
    )
    reloaded.fill_none_references()

    resolved_name = "Resolved Default: Excitatory Tsodyks-Markram"
    assert list(reloaded.synaptic_models) == [resolved_name]
    assert len(reloaded.distributions) == len(stored.distributions)
    assert reloaded.synapse_model_assigners["all_pairs"].synaptic_model.block_name == resolved_name
    assert (
        reloaded.synapse_model_assigners["all_pairs_2"].synaptic_model.block_name == resolved_name
    )


def test_fill_stacks_a_new_default_beside_an_edited_resolved_default():
    """An edited resolved default is left untouched; a new assigner gets a fresh default beside.

    If the user changed a parameter inside the materialized "Resolved Default: ..." model, a
    newly added assigner asking for the pristine default must not attach to the edited block nor
    overwrite it. The pristine default stacks as "Resolved (1) Default: ...".
    """
    stored = _defaults_only_scan_config("all_pairs")
    stored.fill_none_references()

    dumped = stored.model_dump(mode="json")
    resolved_name = "Resolved Default: Excitatory Tsodyks-Markram"
    # A real edit to the materialized model: enable a flag the pristine default leaves off.
    dumped["synaptic_models"][resolved_name]["facilitation_time_shared_within"] = True
    edited = obi.SynapseParameterizationScanConfig.model_validate(dumped)
    edited.add(
        obi.AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
        name="all_pairs_2",
    )
    edited.fill_none_references()

    stacked_name = "Resolved (1) Default: Excitatory Tsodyks-Markram"
    assert set(edited.synaptic_models) == {resolved_name, stacked_name}
    # The user's edit survives, and the newly stacked default is pristine.
    assert edited.synaptic_models[resolved_name].facilitation_time_shared_within is True
    assert edited.synaptic_models[stacked_name].facilitation_time_shared_within is False
    assert edited.synapse_model_assigners["all_pairs_2"].synaptic_model.block_name == stacked_name


def test_fill_stacks_a_second_index_beside_two_differing_defaults():
    """A third, distinct default stacks as "Resolved (2) ..." past two blocks already taken.

    Two separate edits to the materialized model leave two differing blocks under the base name
    ("Resolved Default: ..." and "Resolved (1) ..."); a newly added assigner asking for the
    pristine default must walk past both and stack at "Resolved (2) ...".
    """
    stored = _defaults_only_scan_config("all_pairs")
    stored.fill_none_references()

    dumped = stored.model_dump(mode="json")
    plain = "Resolved Default: Excitatory Tsodyks-Markram"
    stacked_1 = "Resolved (1) Default: Excitatory Tsodyks-Markram"
    stacked_2 = "Resolved (2) Default: Excitatory Tsodyks-Markram"
    # Two pre-existing, differently-edited copies of the resolved default under the base name.
    dumped["synaptic_models"][plain]["facilitation_time_shared_within"] = True
    edited_1 = dumped["synaptic_models"][plain].copy()
    edited_1["depression_time_shared_within"] = True
    dumped["synaptic_models"][stacked_1] = edited_1
    # The assigner still points at the plain block; the stacked one is just carried along.
    prefilled = obi.SynapseParameterizationScanConfig.model_validate(dumped)
    prefilled.add(
        obi.AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
        name="all_pairs_2",
    )
    prefilled.fill_none_references()

    assert set(prefilled.synaptic_models) == {plain, stacked_1, stacked_2}
    # The two pre-existing edits survive, and the newly stacked default is pristine.
    assert prefilled.synaptic_models[plain].facilitation_time_shared_within is True
    assert prefilled.synaptic_models[stacked_1].depression_time_shared_within is True
    assert prefilled.synaptic_models[stacked_2].facilitation_time_shared_within is False
    assert prefilled.synaptic_models[stacked_2].depression_time_shared_within is False
    assert prefilled.synapse_model_assigners["all_pairs_2"].synaptic_model.block_name == stacked_2


def test_fill_is_idempotent_after_a_reload_and_refill():
    """Filling an already-filled reloaded config a second time changes nothing.

    Once a reloaded campaign has been refilled for a newly added assigner, nothing is unset, so
    a further fill must be a no-op - no block renamed, added, or restacked.
    """
    stored = _defaults_only_scan_config("all_pairs")
    stored.fill_none_references()

    reloaded = _reload(stored)
    reloaded.add(
        obi.AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
        name="all_pairs_2",
    )
    reloaded.fill_none_references()
    after_first = reloaded.model_dump(mode="json")

    reloaded.fill_none_references()

    assert reloaded.model_dump(mode="json") == after_first
