"""End-to-end tests for SynapseParameterizationTask.execute against a local circuit.

Mirrors the circuit-extraction task tests: run the task on a tiny local circuit with no
db_client, so the parameterization/output path is exercised while the entitycore
registration branch (which needs a db_client and a parent entity) is skipped.
"""

import json
import shutil
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bluepysnap as snap
import pytest
from entitysdk import types

from obi_one.core.exception import ConfigValidationError
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey
from obi_one.core.tuple import NamedTuple
from obi_one.scientific.blocks.distributions.gamma import GammaDistribution
from obi_one.scientific.blocks.neuron_sets.combined import (
    BiophysicalCombinedNeuronSet,
    SetOperation,
)
from obi_one.scientific.blocks.neuron_sets.id import (
    BiophysicalPopulationIDNeuronSet,
    VirtualPopulationIDNeuronSet,
)
from obi_one.scientific.blocks.synaptic_model_assigners.all_pairs import (
    AllPairsSynapticModelAssigner,
)
from obi_one.scientific.blocks.synaptic_model_assigners.inter_neuron_set import (
    InterNeuronSetSynapticModelAssigner,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.block import (
    ExcitatoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.synapse_parameterization.config import (
    DEFAULT_SYNAPTIC_MODEL_NAME,
    SynapseParameterizationScanConfig,
    SynapseParameterizationSingleConfig,
)
from obi_one.scientific.tasks.synapse_parameterization.task import SynapseParameterizationTask
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag

from tests.utils import CIRCUIT_DIR

# Intrinsic biophysical -> biophysical edge population of the tiny test circuit.
EDGE_POPULATION_NAME = "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical"


def _local_circuit():
    return Circuit(
        name="N_10__top_nodes_dim6",
        path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
    )


def _build_config(tmp_path, circuit=None):
    """A minimal single-config: one excitatory model applied to every synapse."""
    config = SynapseParameterizationSingleConfig.empty_config()
    config.set(
        Info(campaign_name="Test", campaign_description="Test parameterization"),
        name="info",
    )
    config.set(config.Initialize(circuit=circuit or _local_circuit()), name="initialize")

    conductance = GammaDistribution(shape=4.0, scale=0.25)
    config.add(conductance, "Excitatory conductance distribution")
    model = ExcitatoryTsodyksMarkramSynapticModel(conductance_distribution=conductance.ref)
    config.add(model, "Excitatory synaptic model")
    config.add(
        AllPairsSynapticModelAssigner(
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

    result = SynapseParameterizationTask(config=config).execute(db_client=None)

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


@pytest.mark.filterwarnings("ignore::FutureWarning")
def test_execute_keeps_a_circuit_specific_mod_file_rather_than_the_repos_generic_one(tmp_path):
    """A circuit's own ProbAMPANMDA_EMS.mod must survive, not be replaced by the generic one.

    The repo's generic copy and the fixture circuit's own copy happen to be byte-identical
    today, so asserting the output merely matches either of them would not actually prove
    which one was used. This overwrites the copied circuit's file with content that cannot
    have come from the repo, so a pass here can only mean the "leave it alone" path ran.
    """
    circuit_dir = tmp_path / "circuit_with_specific_mod"
    shutil.copytree(_local_circuit().directory, circuit_dir)
    mod_file = circuit_dir / "mod" / "ProbAMPANMDA_EMS.mod"
    mod_file.write_text("CIRCUIT SPECIFIC CONTENT, NOT THE REPO'S GENERIC ProbAMPANMDA_EMS.mod")

    circuit = Circuit(
        name="circuit_with_specific_mod", path=str(circuit_dir / "circuit_config.json")
    )
    config = _build_config(tmp_path, circuit=circuit)

    SynapseParameterizationTask(config=config).execute(db_client=None)

    output_mod_file = config.coordinate_output_root / "mod" / "ProbAMPANMDA_EMS.mod"
    assert output_mod_file.read_text() == (
        "CIRCUIT SPECIFIC CONTENT, NOT THE REPO'S GENERIC ProbAMPANMDA_EMS.mod"
    )


def test_execute_declares_and_creates_mechanisms_dir_when_the_circuit_has_none(tmp_path):
    """A circuit relying on the unstated './mod' convention gets an explicit entry and files.

    Built from a stripped-down copy of the fixture circuit: no `mechanisms_dir` entry and no
    pre-existing `mod/` folder, the shape a circuit takes when it never declared where its
    compiled mechanisms live.
    """
    stripped_dir = tmp_path / "stripped_circuit"
    shutil.copytree(_local_circuit().directory, stripped_dir)
    shutil.rmtree(stripped_dir / "mod")

    config_path = stripped_dir / "circuit_config.json"
    cfg = json.loads(config_path.read_text())
    del cfg["components"]["mechanisms_dir"]
    config_path.write_text(json.dumps(cfg))

    config = SynapseParameterizationSingleConfig.empty_config()
    config.set(Info(campaign_name="Test", campaign_description="Test defaults"), name="info")
    config.set(
        config.Initialize(circuit=Circuit(name="stripped", path=str(config_path))),
        name="initialize",
    )
    config.add(
        AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
        name="all_pairs",
    )
    config.fill_block_references_and_names()
    config.fill_none_references()
    config.scan_output_root = tmp_path / "scan"
    config.coordinate_output_root = tmp_path / "scan" / "parameterized"

    SynapseParameterizationTask(config=config).execute(db_client=None)

    output_config_path = config.coordinate_output_root / "circuit_config.json"
    output_cfg = json.loads(output_config_path.read_text())
    assert output_cfg["components"]["mechanisms_dir"] == "$BASE_DIR/mod"

    mod_dir = config.coordinate_output_root / "mod"
    assert (mod_dir / "ProbAMPANMDA_EMS.mod").exists()


def test_register_parameterized_circuit_registers_a_validated_derivation(tmp_path):
    """The output is registered as a rewiring derivation of its parent, with validation on."""
    parent = SimpleNamespace(
        id="parent-id",
        name="parent",
        build_category=types.CircuitBuildCategory.computational_model,
        brain_region=Mock(),
        subject=Mock(),
        target_simulator=None,
        experiment_date="2026-01-01",
        license=Mock(),
        root_circuit_id=None,
    )
    task = SynapseParameterizationTask(config=_build_config(tmp_path))
    task._circuit_entity = parent
    register = "obi_one.scientific.tasks.synapse_parameterization.task.circuit_registration"

    with patch(f"{register}.register_circuit") as mock_register:
        result = task._register_parameterized_circuit(db_client=Mock(), circuit_path=tmp_path)

    assert result is mock_register.return_value
    kwargs = mock_register.call_args.kwargs
    assert kwargs["name"] == "parent (synapse-parameterized)"
    assert kwargs["parent"] is parent
    assert kwargs["root"] == "parent-id"
    assert kwargs["target_simulator"] == types.TargetSimulator.NEURON
    assert kwargs["derivation_type"] == types.DerivationType.circuit_rewiring
    # Validation runs at registration (the default); it must not be skipped
    assert "skip_validation" not in kwargs


def test_register_parameterized_circuit_does_nothing_without_a_parent(tmp_path):
    """A local circuit has no parent entity, so nothing is registered."""
    task = SynapseParameterizationTask(config=_build_config(tmp_path))
    register = "obi_one.scientific.tasks.synapse_parameterization.task.circuit_registration"

    with patch(f"{register}.register_circuit") as mock_register:
        result = task._register_parameterized_circuit(db_client=Mock(), circuit_path=tmp_path)

    assert result is None
    mock_register.assert_not_called()


def test_execute_rejects_output_dir_that_already_exists(tmp_path):
    """Existing coordinate output must raise rather than silently overwrite.

    Happy-path execute coverage lives in test_execute_parameterizes_local_circuit; this only
    needs the copytree dirs_exist_ok=False guard.
    """
    config = _build_config(tmp_path)
    config.coordinate_output_root.mkdir(parents=True)

    with pytest.raises(FileExistsError):
        SynapseParameterizationTask(config=config).execute(db_client=None)


def _unset_config(tmp_path):
    """A config that names no synaptic model or distributions: everything relies on defaults.

    The assigner's synaptic_model is left unset, so nothing but the edge population and the
    circuit is specified. This is the shape a config takes when the user accepts every default.
    """
    config = SynapseParameterizationSingleConfig.empty_config()
    config.set(
        Info(campaign_name="Test", campaign_description="Test defaults"),
        name="info",
    )
    config.set(config.Initialize(circuit=_local_circuit()), name="initialize")
    config.add(
        AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
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
    config = SynapseParameterizationScanConfig.empty_config()
    config.set(
        Info(campaign_name="Test", campaign_description="Test defaults"),
        name="info",
    )
    config.set(config.Initialize(circuit=_local_circuit()), name="initialize")
    config.add(
        AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
        name="all_pairs",
    )
    config.fill_block_references_and_names()

    # The schema label for the unset field stays "Default: ...".
    schema_defaults = SynapseParameterizationScanConfig.model_config["json_schema_extra"][
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
    reloaded = SynapseParameterizationScanConfig.model_validate(config.model_dump(mode="json"))
    assigner = reloaded.synapse_model_assigners["all_pairs"]
    assert assigner.synaptic_model.block_name == "Resolved Default: Excitatory Tsodyks-Markram"
    assert isinstance(assigner.synaptic_model.block, ExcitatoryTsodyksMarkramSynapticModel)


def test_execute_rejects_a_config_with_no_assigners(tmp_path):
    """A config with no assigners parameterizes nothing and must be rejected, not run silently."""
    config = SynapseParameterizationSingleConfig.empty_config()
    config.set(
        Info(campaign_name="Test", campaign_description="Test empty"),
        name="info",
    )
    config.set(config.Initialize(circuit=_local_circuit()), name="initialize")
    config.fill_block_references_and_names()
    config.scan_output_root = tmp_path / "scan"
    config.coordinate_output_root = tmp_path / "scan" / "parameterized"

    with pytest.raises(ValueError, match="No synaptic model assigners"):
        SynapseParameterizationTask(config=config).execute(db_client=None)


@pytest.mark.filterwarnings("ignore::FutureWarning")
def test_execute_parameterizes_a_defaults_only_config(tmp_path):
    """A config naming no synaptic model parameterizes from the resolved defaults.

    Defaults are materialized by the generation step (mirrored here by calling
    fill_none_references before execute), so by the time the task runs the assigner's
    synaptic model and its distributions are in place.
    """
    config = _unset_config(tmp_path)
    config.fill_none_references()  # done by ScanGenerationTask before serialization

    SynapseParameterizationTask(config=config).execute(db_client=None)

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
    config = SynapseParameterizationScanConfig.empty_config()
    config.set(
        Info(campaign_name="Test", campaign_description="Test reload"),
        name="info",
    )
    config.set(config.Initialize(circuit=_local_circuit()), name="initialize")
    for name in assigner_names:
        config.add(
            AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
            name=name,
        )
    config.fill_block_references_and_names()
    return config


def _reload(config):
    """Round-trip a config through JSON the way a stored campaign is loaded back."""
    return SynapseParameterizationScanConfig.model_validate(config.model_dump(mode="json"))


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
        AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
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
    edited = SynapseParameterizationScanConfig.model_validate(dumped)
    edited.add(
        AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
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
    prefilled = SynapseParameterizationScanConfig.model_validate(dumped)
    prefilled.add(
        AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
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
        AllPairsSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME),
        name="all_pairs_2",
    )
    reloaded.fill_none_references()
    after_first = reloaded.model_dump(mode="json")

    reloaded.fill_none_references()

    assert reloaded.model_dump(mode="json") == after_first


def _inter_set_config_with_source(circuit, source_set, source_ref_dict):
    """A scan config with one virtual/biophysical source set and an inter-set assigner.

    ``source_ref_dict`` is injected verbatim as the assigner's ``source_neuron_set`` (mimicking
    a stored config), so the reference ``type`` carried on reload can be asserted.
    """
    config = SynapseParameterizationScanConfig.empty_config()
    config.set(Info(campaign_name="T", campaign_description="d"), name="info")
    config.set(config.Initialize(circuit=circuit), name="initialize")
    config.add(source_set, "Ext20-50")

    dumped = config.model_dump(mode="json")
    dumped["synapse_model_assigners"] = {
        "a": {
            "type": "InterNeuronSetSynapticModelAssigner",
            "edge_population_name": EDGE_POPULATION_NAME,
            "source_neuron_set": source_ref_dict,
        }
    }
    return SynapseParameterizationScanConfig.model_validate(dumped)


def test_reference_type_healed_for_virtual_source_neuron_set():
    """A source_neuron_set pointing at a virtual set resolves to VirtualNeuronSetReference.

    The frontend omits ``type`` and Pydantic stamps the first union member
    (BiophysicalNeuronSetReference); stored configs may even carry that wrong ``type``. The
    reference type must be re-derived from the referenced block's actual (virtual) variant.
    """
    circuit = _local_circuit()
    virtual = VirtualPopulationIDNeuronSet(
        population="VPM", neuron_ids=NamedTuple(name="s", elements=[0, 1, 2])
    )
    # Stored config carries the WRONG type - it must be healed on load.
    wrong_ref = {
        "block_dict_name": "neuron_sets",
        "block_name": "Ext20-50",
        "type": "BiophysicalNeuronSetReference",
    }
    config = _inter_set_config_with_source(circuit, virtual, wrong_ref)

    ref = config.synapse_model_assigners["a"].source_neuron_set
    assert ref.type == "VirtualNeuronSetReference"
    # The serialized coordinate config carries the corrected type too.
    dumped = config.model_dump(mode="json")
    assert dumped["synapse_model_assigners"]["a"]["source_neuron_set"]["type"] == (
        "VirtualNeuronSetReference"
    )


def test_reference_type_preserved_for_biophysical_source_neuron_set():
    """A source_neuron_set pointing at a biophysical set stays BiophysicalNeuronSetReference."""
    circuit = _local_circuit()
    biophysical = BiophysicalPopulationIDNeuronSet(
        population="S1nonbarrel_neurons", neuron_ids=NamedTuple(name="s", elements=[0, 1])
    )
    # Type-less reference, as the frontend sends it.
    ref_dict = {"block_dict_name": "neuron_sets", "block_name": "Ext20-50"}
    config = _inter_set_config_with_source(circuit, biophysical, ref_dict)

    assert config.synapse_model_assigners["a"].source_neuron_set.type == (
        "BiophysicalNeuronSetReference"
    )


# --- Neuron sets stored in the output circuit's node sets ---

BIOPHYSICAL_POPULATION = "S1nonbarrel_neurons"
SOURCE_NODE_SETS_FILE = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "node_sets.json"


def _id_neuron_set(name, ids, population=BIOPHYSICAL_POPULATION):
    return BiophysicalPopulationIDNeuronSet(
        population=population, neuron_ids=NamedTuple(name=name, elements=ids)
    )


def _neuron_set_config(tmp_path, *, circuit=None, extra_neuron_sets=None):
    """A config with an inter-set assigner and four neuron sets of its own.

    "Sources" and "Targets" are the two ends of the assigner. "Unused" is referenced by nothing
    and "SourcesOrTargets" is a union of the first two, which no assigner uses either.
    """
    config = SynapseParameterizationSingleConfig.empty_config()
    config.set(Info(campaign_name="Test", campaign_description="Test neuron sets"), name="info")
    config.set(config.Initialize(circuit=circuit or _local_circuit()), name="initialize")

    sources = _id_neuron_set("sources", [0, 1, 2])
    targets = _id_neuron_set("targets", [3, 4])
    config.add(sources, "Sources")
    config.add(targets, "Targets")
    config.add(_id_neuron_set("unused", [5]), "Unused")
    config.add(
        BiophysicalCombinedNeuronSet(
            base_neuron_set=sources.ref, combined_with=((targets.ref, SetOperation.UNION),)
        ),
        "SourcesOrTargets",
    )
    for name, neuron_set in (extra_neuron_sets or {}).items():
        config.add(neuron_set, name)

    conductance = GammaDistribution(shape=4.0, scale=0.25)
    config.add(conductance, "Excitatory conductance distribution")
    model = ExcitatoryTsodyksMarkramSynapticModel(conductance_distribution=conductance.ref)
    config.add(model, "Excitatory synaptic model")
    config.add(
        InterNeuronSetSynapticModelAssigner(
            edge_population_name=EDGE_POPULATION_NAME,
            synaptic_model=model.ref,
            source_neuron_set=sources.ref,
            targeted_neuron_set=targets.ref,
        ),
        name="inter",
    )
    config.fill_block_references_and_names()
    config.fill_none_references()

    config.scan_output_root = tmp_path / "scan"
    config.coordinate_output_root = tmp_path / "scan" / "parameterized"
    return config


def _output_circuit(config):
    return snap.Circuit(str(config.coordinate_output_root / "circuit_config.json"))


@pytest.mark.filterwarnings("ignore::FutureWarning")
def test_execute_stores_the_neuron_sets_next_to_the_existing_node_sets(tmp_path):
    config = _neuron_set_config(tmp_path)
    input_node_sets = SOURCE_NODE_SETS_FILE.read_bytes()

    SynapseParameterizationTask(config=config).execute(db_client=None)

    stored = _output_circuit(config).node_sets.content
    # Every neuron set of the config is stored, used by an assigner or not.
    assert {"Sources", "Targets", "Unused", "SourcesOrTargets"} <= set(stored)
    # The definitions the combined set needs are stored along with it.
    assert stored["SourcesOrTargets"] == [
        "__BiophysicalCombinedNeuronSet__Sources",
        "__BiophysicalCombinedNeuronSet__Targets",
    ]
    assert set(stored["SourcesOrTargets"]) <= set(stored)
    # The node sets the circuit already had are all still there, unchanged.
    for name, definition in json.loads(input_node_sets).items():
        assert stored[name] == definition
    # The input circuit itself is not modified.
    assert SOURCE_NODE_SETS_FILE.read_bytes() == input_node_sets


@pytest.mark.filterwarnings("ignore::FutureWarning")
def test_stored_neuron_sets_select_the_neurons_the_config_resolves_them_to(tmp_path):
    """What is written must agree with what the config's own blocks resolve to."""
    config = _neuron_set_config(tmp_path)

    SynapseParameterizationTask(config=config).execute(db_client=None)

    population = _output_circuit(config).nodes[BIOPHYSICAL_POPULATION]
    expected_ids = {
        "Sources": [0, 1, 2],
        "Targets": [3, 4],
        "Unused": [5],
        "SourcesOrTargets": [0, 1, 2, 3, 4],
    }
    for name, expected in expected_ids.items():
        assert sorted(population.ids(name).tolist()) == expected
        resolved = config.neuron_sets[name].get_neuron_ids(_local_circuit())
        assert sorted(resolved[BIOPHYSICAL_POPULATION]) == expected


@pytest.mark.filterwarnings("ignore::FutureWarning")
def test_execute_stores_the_default_neuron_sets_of_unset_assigner_ends(tmp_path):
    config = _unset_config(tmp_path)
    config.add(InterNeuronSetSynapticModelAssigner(edge_population_name=EDGE_POPULATION_NAME), "i")
    config.fill_block_references_and_names()
    config.fill_none_references()
    default_name = "Resolved Default: All Biophysical Neurons"
    assert default_name in config.neuron_sets

    SynapseParameterizationTask(config=config).execute(db_client=None)

    population = _output_circuit(config).nodes[BIOPHYSICAL_POPULATION]
    assert len(population.ids(default_name)) == population.size


@pytest.mark.filterwarnings("ignore::FutureWarning")
def test_execute_leaves_the_node_sets_file_untouched_without_neuron_sets(tmp_path):
    config = _build_config(tmp_path)
    assert not config.neuron_sets

    SynapseParameterizationTask(config=config).execute(db_client=None)

    output_node_sets = config.coordinate_output_root / "node_sets.json"
    assert output_node_sets.read_bytes() == SOURCE_NODE_SETS_FILE.read_bytes()


def test_execute_rejects_a_neuron_set_clashing_with_an_existing_node_set_before_copying(tmp_path):
    # "Excitatory" is already a node set of the circuit, with a different definition.
    config = _neuron_set_config(
        tmp_path, extra_neuron_sets={"Excitatory": _id_neuron_set("excitatory", [0])}
    )

    with pytest.raises(ValueError, match="Node set 'Excitatory' already exists"):
        SynapseParameterizationTask(config=config).execute(db_client=None)

    # Rejected while validating, so nothing was copied or modified.
    assert not config.coordinate_output_root.exists()


def test_execute_rejects_a_neuron_set_of_a_missing_population_before_copying(tmp_path):
    # Not used by any assigner, but still written to the node sets, so it has to fit the circuit.
    config = _neuron_set_config(
        tmp_path,
        extra_neuron_sets={"Elsewhere": _id_neuron_set("elsewhere", [0], population="NoSuchPop")},
    )

    with pytest.raises(ConfigValidationError, match="NoSuchPop"):
        SynapseParameterizationTask(config=config).execute(db_client=None)

    assert not config.coordinate_output_root.exists()


@pytest.mark.filterwarnings("ignore::FutureWarning")
def test_execute_declares_a_node_sets_file_for_a_circuit_without_one(tmp_path):
    circuit_dir = tmp_path / "circuit_without_node_sets"
    shutil.copytree(_local_circuit().directory, circuit_dir)
    (circuit_dir / "node_sets.json").unlink()
    config_path = circuit_dir / "circuit_config.json"
    cfg = json.loads(config_path.read_text())
    del cfg["node_sets_file"]
    config_path.write_text(json.dumps(cfg))
    circuit = Circuit(name="circuit_without_node_sets", path=str(config_path))
    config = _neuron_set_config(tmp_path, circuit=circuit)

    SynapseParameterizationTask(config=config).execute(db_client=None)

    output_cfg = json.loads((config.coordinate_output_root / "circuit_config.json").read_text())
    assert output_cfg["node_sets_file"] == "$BASE_DIR/node_sets.json"
    stored = _output_circuit(config).node_sets.content
    assert set(stored) >= {"Sources", "Targets", "Unused", "SourcesOrTargets"}
    # The circuit had no node sets of its own, so these are all there is (plus helpers).
    assert all(name.startswith("__") or name in config.neuron_sets for name in stored)
