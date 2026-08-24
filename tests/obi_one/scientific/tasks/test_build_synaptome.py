import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import bluepysnap
import h5py
import morphio
import numpy as np
import pandas as pd
import pytest
from entitysdk.types import (
    CircuitBuildCategory,
    TargetSimulator,
    TaskActivityType,
    TaskConfigType,
)

from obi_one.core.info import Info
from obi_one.scientific.blocks.distributions.constant import FloatConstantDistribution
from obi_one.scientific.blocks.distributions.normal import NormalDistribution
from obi_one.scientific.blocks.morphology_locations.base import MorphologyLocationsBlock
from obi_one.scientific.blocks.morphology_locations.path_distance import (
    PathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.random import RandomMorphologyLocations
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.build_synaptome import (
    BuildSynaptomeError,
    BuildSynaptomeResult,
    _generate_locations,
    _location_edge_properties,
    _sample_physiology,
    _target_population,
)
from obi_one.scientific.library.map_em_synapses.write_sonata_nodes_file import (
    write_virtual_nodes,
)
from obi_one.scientific.library.memodel_circuit import MEModelCircuit
from obi_one.scientific.library.morphology_locations import _PRE_IDX
from obi_one.scientific.tasks.build_synaptome import (
    MEModelSynapticModelPlacementScanConfig,
    MEModelSynapticModelPlacementSingleConfig,
    MEModelSynapticModelPlacementTask,
    SynapticModelPlacer,
    build_synaptome,
)
from obi_one.scientific.unions_and_references.distributions import AllDistributionsReference
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationsReference,
)
from obi_one.scientific.unions_and_references.synaptic_models import SynapticModelReference

_SWC_MORPHOLOGY = (
    "1 1 0 0 0 5 -1\n"
    "2 3 0 10 0 1 1\n"
    "3 3 0 30 0 1 2\n"
    "4 3 10 50 0 1 3\n"
    "5 4 -10 10 0 1 1\n"
    "6 4 -20 30 0 1 5\n"
)


def _write_staged_memodel(
    path: Path,
    *,
    include_morphology: bool = True,
    morphology_text: str = _SWC_MORPHOLOGY,
) -> Path:
    path.mkdir()
    (path / "hoc").mkdir()
    (path / "morphologies").mkdir()
    if include_morphology:
        (path / "morphologies" / "cell.swc").write_text(morphology_text)
    with h5py.File(path / "nodes.h5", "w") as h5:
        population = h5.create_group("nodes/target")
        population.create_dataset("node_type_id", data=[-1])
        population.create_dataset("node_group_id", data=[0])
        population.create_dataset("node_group_index", data=[0])
        group = population.create_group("0")
        string_dtype = h5py.string_dtype()
        group.create_dataset("morphology", data=["cell"], dtype=string_dtype)
        group.create_dataset("model_type", data=["biophysical"], dtype=string_dtype)
        group.create_dataset("model_template", data=["hoc:Cell"], dtype=string_dtype)
    config = {
        "manifest": {"$BASE_DIR": "./"},
        "networks": {
            "nodes": [
                {
                    "nodes_file": "$BASE_DIR/nodes.h5",
                    "populations": {
                        "target": {
                            "type": "biophysical",
                            "morphologies_dir": "$BASE_DIR/morphologies",
                            "biophysical_neuron_models_dir": "$BASE_DIR/hoc",
                        }
                    },
                }
            ],
            "edges": [],
        },
    }
    config_path = path / "circuit_config.json"
    config_path.write_text(json.dumps(config))
    return config_path


@pytest.fixture
def stage_memodel(monkeypatch):
    def configure(
        *,
        include_morphology: bool = True,
        morphology_text: str = _SWC_MORPHOLOGY,
        failure: Exception | None = None,
    ):
        def stage(_self, *, db_client, dest_dir, entity_cache=False):  # ruff: ignore[unused-function-argument]
            if failure is not None:
                raise failure
            config_path = _write_staged_memodel(
                dest_dir,
                include_morphology=include_morphology,
                morphology_text=morphology_text,
            )
            return MEModelCircuit(name="single_cell", path=str(config_path))

        monkeypatch.setattr(MEModelFromID, "stage_circuit", stage)

    return configure


def _reference(name: str) -> SynapticModelReference:
    return SynapticModelReference(block_dict_name="synaptic_models", block_name=name)


def _placement_reference(name: str) -> MorphologyLocationsReference:
    return MorphologyLocationsReference(block_dict_name="morphology_locations", block_name=name)


def _config(
    *,
    groups: dict[str, SynapticModelPlacer] | None = None,
    morphology_locations: dict[str, MorphologyLocationsBlock] | None = None,
    distributed: bool = False,
) -> MEModelSynapticModelPlacementSingleConfig:
    distributions = {
        "exc_conductance": FloatConstantDistribution(value=0.4),
        "exc_delay": (
            NormalDistribution(
                mean=1.5,
                standard_deviation=0.2,
                min=0.1,
                random_seed=71,
            )
            if distributed
            else FloatConstantDistribution(value=1.5)
        ),
        "inh_conductance": FloatConstantDistribution(value=0.8),
    }
    models = {
        "exc": ExcitatoryTsodyksMarkramSynapticModel(
            conductance_distribution=AllDistributionsReference(
                block_dict_name="distributions", block_name="exc_conductance"
            ),
            delay_distribution=AllDistributionsReference(
                block_dict_name="distributions", block_name="exc_delay"
            ),
        ),
        "inh": InhibitoryTsodyksMarkramSynapticModel(
            conductance_distribution=AllDistributionsReference(
                block_dict_name="distributions", block_name="inh_conductance"
            )
        ),
    }
    if morphology_locations is None:
        morphology_locations = {
            "basal": RandomMorphologyLocations(
                number_of_locations=4, section_types=(3,), random_seed=11
            )
        }
    if groups is None:
        groups = {
            "basal": SynapticModelPlacer(
                synaptic_model=_reference("exc"),
                placement_strategy=_placement_reference("basal"),
            )
        }
    return MEModelSynapticModelPlacementSingleConfig(
        info=Info(campaign_name="test", campaign_description="test synaptome"),
        initialize=MEModelSynapticModelPlacementScanConfig.Initialize(
            me_model=MEModelFromID(id_str="test-me-model")
        ),
        distributions=distributions,
        synaptic_models=models,
        morphology_locations=morphology_locations,
        synapse_groups=groups,
    )


def _edge_frame(result, edge_name: str):
    circuit = bluepysnap.Circuit(result.circuit_config_path)
    edge = circuit.edges[edge_name]
    return edge.get(edge.ids(), properties=sorted(edge.property_names))


def test_location_edge_properties_rejects_soma_section_id():
    locations = pd.DataFrame({"section_id": [0]})

    with pytest.raises(
        BuildSynaptomeError,
        match=r"Invalid morphology location section=0; soma locations are not supported",
    ):
        _location_edge_properties(Mock(), locations)


def test_default_placement_seed_is_unique_per_synapse_group():
    morphology = morphio.Morphology(_SWC_MORPHOLOGY, "swc")
    placement = RandomMorphologyLocations(number_of_locations=4, section_types=(3,))

    first_group = _generate_locations(
        morphology,
        placement,
        group_name="excitatory",
        group_index=0,
    )
    second_group = _generate_locations(
        morphology,
        placement,
        group_name="inhibitory",
        group_index=1,
    )
    repeated_second_group = _generate_locations(
        morphology,
        placement,
        group_name="inhibitory",
        group_index=1,
    )

    assert not first_group.equals(second_group)
    pd.testing.assert_frame_equal(second_group, repeated_second_group)


def test_build_synaptome_config_provenance(monkeypatch):
    me_model = Mock()
    monkeypatch.setattr(MEModelFromID, "entity", Mock(return_value=me_model))
    config = _config()

    assert config.campaign_task_config_type is TaskConfigType.circuit_single_build__campaign
    assert (
        config.campaign_generation_task_activity_type
        is TaskActivityType.circuit_single_build__config_generation
    )
    assert config.single_task_config_type is TaskConfigType.circuit_single_build__config
    assert config.input_entities(db_client=Mock()) == [me_model]


def test_build_synaptome_task_registers_circuit_and_updates_activity(tmp_path, monkeypatch):
    config = _config()
    config.coordinate_output_root = tmp_path
    subject = Mock()
    brain_region = Mock()
    license_entity = Mock()
    morphology = SimpleNamespace(
        subject=subject,
        experiment_date="2026-08-05",
        license=None,
    )
    me_model = SimpleNamespace(
        id="me-model-id",
        morphology=morphology,
        brain_region=brain_region,
        license=license_entity,
    )
    monkeypatch.setattr(MEModelFromID, "entity", Mock(return_value=me_model))

    result = BuildSynaptomeResult(
        circuit_config_path=tmp_path / "SONATA" / "circuit_config.json",
        output_directory=tmp_path / "SONATA",
        generated_files=(),
    )
    build = Mock(return_value=result)
    register = Mock(return_value=SimpleNamespace(id="circuit-id"))
    execution_activity = SimpleNamespace(id="activity-id")
    get_activity = Mock(return_value=execution_activity)
    update_activity = Mock()
    monkeypatch.setattr(
        "obi_one.scientific.tasks.build_synaptome.build_synaptome_artifact",
        build,
    )
    monkeypatch.setattr(
        "obi_one.scientific.tasks.build_synaptome.circuit_registration.register_circuit",
        register,
    )
    monkeypatch.setattr(MEModelSynapticModelPlacementTask, "_get_execution_activity", get_activity)
    monkeypatch.setattr(
        MEModelSynapticModelPlacementTask, "_update_execution_activity", update_activity
    )

    db_client = Mock()
    circuit_id = MEModelSynapticModelPlacementTask(config=config).execute(
        db_client=db_client,
        execution_activity_id="activity-id",
    )

    assert circuit_id == "circuit-id"
    build.assert_called_once_with(config, tmp_path / "SONATA", db_client=db_client)
    register.assert_called_once_with(
        client=db_client,
        circuit_path=result.circuit_config_path,
        name="test",
        description="test synaptome",
        build_category=CircuitBuildCategory.computational_model,
        brain_region=brain_region,
        subject=subject,
        target_simulator=TargetSimulator.NEURON,
        experiment_date="2026-08-05",
        license=license_entity,
        skip_validation=True,
    )
    update_activity.assert_called_once_with(
        db_client=db_client,
        execution_activity=execution_activity,
        generated=["circuit-id"],
    )


def test_build_minimal_synaptome_loads_with_bluepysnap(tmp_path, stage_memodel):
    stage_memodel()
    result = build_synaptome(_config(), tmp_path / "artifact", db_client=object())
    circuit = bluepysnap.Circuit(result.circuit_config_path)

    assert circuit.nodes["target"].size == 1
    assert circuit.nodes["synaptome_basal_sources"].size == 1
    edge = circuit.edges["synaptome_basal__target__chemical"]
    assert edge.size == 4
    refs = edge.get(edge.ids(), properties=["@source_node", "@target_node"])
    np.testing.assert_array_equal(refs["@source_node"], np.zeros(4))
    np.testing.assert_array_equal(refs["@target_node"], np.zeros(4))
    assert {
        "afferent_section_id",
        "afferent_segment_id",
        "afferent_segment_offset",
        "afferent_section_pos",
        "conductance",
        "delay",
        "syn_type_id",
    }.issubset(edge.property_names)
    assert result.circuit_config_path in result.generated_files


def test_build_loads_morphology_from_staged_circuit(tmp_path, stage_memodel, monkeypatch):
    stage_memodel()
    direct_loader = Mock(side_effect=AssertionError("direct morphology loading is not allowed"))
    monkeypatch.setattr(MEModelFromID, "morphio_morphology", direct_loader)

    build_synaptome(_config(), tmp_path / "artifact", db_client=object())

    direct_loader.assert_not_called()


def test_build_densifies_sparse_source_ids(tmp_path, stage_memodel, monkeypatch):
    stage_memodel()
    sparse_locations = pd.DataFrame(
        {
            "section_id": [1, 1],
            "segment_id": [0, 0],
            "segment_offset": [1.0, 2.0],
            "normalized_section_offset": [0.05, 0.1],
            "section_type": [3, 3],
            _PRE_IDX: [0, 2],
        }
    )
    monkeypatch.setattr(
        "obi_one.scientific.library.build_synaptome._generate_locations",
        Mock(return_value=sparse_locations),
    )

    result = build_synaptome(_config(), tmp_path / "artifact", db_client=object())
    circuit = bluepysnap.Circuit(result.circuit_config_path)
    edge = circuit.edges["synaptome_basal__target__chemical"]
    refs = edge.get(edge.ids(), properties=["@source_node"])

    assert edge.source.size == 2
    np.testing.assert_array_equal(np.sort(refs["@source_node"]), np.array([0, 1]))


def test_multiple_groups_use_independent_placement_and_physiology(tmp_path, stage_memodel):
    stage_memodel()
    morphology_locations = {
        "basal": RandomMorphologyLocations(
            number_of_locations=3, section_types=(3,), random_seed=1
        ),
        "apical": PathDistanceMorphologyLocations(
            number_of_locations=2,
            section_types=(4,),
            path_dist_mean=20.0,
            path_dist_tolerance=30.0,
            random_seed=9,
        ),
    }
    groups = {
        "basal": SynapticModelPlacer(
            synaptic_model=_reference("exc"),
            placement_strategy=_placement_reference("basal"),
        ),
        "apical": SynapticModelPlacer(
            synaptic_model=_reference("inh"),
            placement_strategy=_placement_reference("apical"),
        ),
    }
    result = build_synaptome(
        _config(groups=groups, morphology_locations=morphology_locations),
        tmp_path / "artifact",
        db_client=object(),
    )
    circuit = bluepysnap.Circuit(result.circuit_config_path)
    basal = circuit.edges["synaptome_basal__target__chemical"]
    apical = circuit.edges["synaptome_apical__target__chemical"]

    assert basal.size == 3
    assert apical.size == 2
    assert basal.source.size == 1
    assert apical.source.size == 2
    assert set(basal.get(basal.ids(), properties="afferent_section_type")) == {3}
    assert set(apical.get(apical.ids(), properties="afferent_section_type")) == {4}
    assert set(basal.get(basal.ids(), properties="syn_type_id")) == {113}
    assert set(apical.get(apical.ids(), properties="syn_type_id")) == {7}
    assert set(basal.get(basal.ids(), properties="conductance")) == {0.4}
    assert set(apical.get(apical.ids(), properties="conductance")) == {0.8}


def test_build_is_deterministic_for_equal_seeds(tmp_path, stage_memodel):
    stage_memodel()
    first = build_synaptome(_config(distributed=True), tmp_path / "first", db_client=object())
    second = build_synaptome(_config(distributed=True), tmp_path / "second", db_client=object())
    edge_name = "synaptome_basal__target__chemical"

    assert _edge_frame(first, edge_name).equals(_edge_frame(second, edge_name))


def test_different_placement_seed_changes_locations(tmp_path, stage_memodel):
    stage_memodel()
    first = build_synaptome(_config(), tmp_path / "first", db_client=object())
    morphology_locations = {
        "basal": RandomMorphologyLocations(
            number_of_locations=4, section_types=(3,), random_seed=12
        )
    }
    groups = {
        "basal": SynapticModelPlacer(
            synaptic_model=_reference("exc"),
            placement_strategy=_placement_reference("basal"),
        )
    }
    second = build_synaptome(
        _config(groups=groups, morphology_locations=morphology_locations),
        tmp_path / "second",
        db_client=object(),
    )
    edge_name = "synaptome_basal__target__chemical"
    columns = ["afferent_section_id", "afferent_segment_id", "afferent_segment_offset"]

    assert not _edge_frame(first, edge_name)[columns].equals(
        _edge_frame(second, edge_name)[columns]
    )


def test_placement_does_not_mutate_global_numpy_rng(tmp_path, stage_memodel):
    stage_memodel()
    np.random.seed(123)  # ruff: ignore[numpy-legacy-random] - verifies isolation from the legacy placer RNG
    expected = np.random.random(3)  # ruff: ignore[numpy-legacy-random]
    np.random.seed(123)  # ruff: ignore[numpy-legacy-random]
    build_synaptome(_config(), tmp_path / "artifact", db_client=object())

    np.testing.assert_array_equal(np.random.random(3), expected)  # ruff: ignore[numpy-legacy-random]


def test_impossible_section_constraint_identifies_group(tmp_path, stage_memodel):
    # Use a morphology with only basal dendrites (type 3), then request apical (type 4)
    basal_only_swc = "1 1 0 0 0 5 -1\n2 3 0 10 0 1 1\n3 3 0 30 0 1 2\n"
    stage_memodel(morphology_text=basal_only_swc)
    morphology_locations = {
        "apical-only": RandomMorphologyLocations(
            number_of_locations=2, section_types=(4,), random_seed=1
        )
    }
    groups = {
        "apical-only": SynapticModelPlacer(
            synaptic_model=_reference("exc"),
            placement_strategy=_placement_reference("apical-only"),
        )
    }

    with pytest.raises(BuildSynaptomeError, match=r"apical-only.*could not generate locations"):
        build_synaptome(
            _config(groups=groups, morphology_locations=morphology_locations),
            tmp_path / "artifact",
            db_client=object(),
        )


def test_unresolved_placement_strategy_identifies_group(tmp_path, stage_memodel):
    stage_memodel()
    config = _config()
    config.synapse_groups["basal"].placement_strategy._block = None

    with pytest.raises(BuildSynaptomeError, match=r"basal.*unresolved placement strategy"):
        build_synaptome(config, tmp_path / "artifact", db_client=object())


def test_unsupported_placement_strategy_identifies_group(tmp_path, stage_memodel):
    stage_memodel()
    config = _config()
    config.synapse_groups["basal"].placement_strategy.block = object()

    with pytest.raises(BuildSynaptomeError, match=r"basal.*unsupported placement strategy"):
        build_synaptome(config, tmp_path / "artifact", db_client=object())


def test_missing_morphology_is_reported(tmp_path, stage_memodel):
    stage_memodel(include_morphology=False)

    with pytest.raises(BuildSynaptomeError, match="Unable to load morphology from staged ME-model"):
        build_synaptome(_config(), tmp_path / "artifact", db_client=object())


def test_unresolved_memodel_is_reported(tmp_path, stage_memodel):
    stage_memodel(failure=LookupError("not found"))

    with pytest.raises(
        BuildSynaptomeError, match=r"Unable to resolve or stage ME-model.*not found"
    ):
        build_synaptome(_config(), tmp_path / "artifact", db_client=object())


def test_requires_db_client(tmp_path):
    with pytest.raises(BuildSynaptomeError, match="requires a db_client"):
        build_synaptome(_config(), tmp_path / "artifact", db_client=None)


def test_output_directory_must_not_exist(tmp_path):
    output = tmp_path / "artifact"
    output.mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        build_synaptome(_config(), output, db_client=object())


@pytest.mark.parametrize(
    ("population_names", "population", "message"),
    [
        (["virtual"], SimpleNamespace(type="virtual"), "exactly one biophysical"),
        (
            ["target-a", "target-b"],
            SimpleNamespace(type="biophysical", size=1),
            "exactly one biophysical",
        ),
        (["target"], SimpleNamespace(type="biophysical", size=2), "exactly one target neuron"),
    ],
)
def test_target_population_rejects_invalid_circuits(population_names, population, message):
    nodes = MagicMock()
    nodes.population_names = population_names
    nodes.__getitem__.return_value = population

    with pytest.raises(BuildSynaptomeError, match=message):
        _target_population(SimpleNamespace(nodes=nodes))


@pytest.mark.parametrize("count", [0, -1])
def test_generate_locations_rejects_invalid_count(count):
    placement = SimpleNamespace(number_of_locations=count)

    with pytest.raises(BuildSynaptomeError, match=r"basal.*invalid location count"):
        _generate_locations(object(), placement, group_name="basal")


def test_generate_locations_rejects_wrong_result_size():
    placement = SimpleNamespace(
        number_of_locations=2,
        points_on=Mock(return_value=pd.DataFrame({"location": [1]})),
    )

    with pytest.raises(BuildSynaptomeError, match=r"basal.*generated 1 locations"):
        _generate_locations(object(), placement, group_name="basal")


def test_sample_physiology_wraps_sampling_error():
    model = SimpleNamespace(sample=Mock(side_effect=ValueError("bad distribution")))

    with pytest.raises(BuildSynaptomeError, match=r"basal.*could not sample physiology"):
        _sample_physiology(model, pd.DataFrame(index=[0]), group_name="basal")


def test_sample_physiology_rejects_invalid_result():
    model = SimpleNamespace(
        sample=Mock(return_value=pd.DataFrame({"delay": [1.0]})),
        parameter_names=Mock(return_value=["delay", "conductance"]),
    )

    with pytest.raises(BuildSynaptomeError, match=r"basal.*invalid physiology data"):
        _sample_physiology(model, pd.DataFrame(index=[0]), group_name="basal")


def test_sample_physiology_rejects_wrong_row_count():
    model = SimpleNamespace(
        sample=Mock(return_value=pd.DataFrame({"delay": [1.0, 1.5], "conductance": [0.4, 0.5]})),
        parameter_names=Mock(return_value=["delay", "conductance"]),
    )

    with pytest.raises(BuildSynaptomeError, match=r"basal.*invalid physiology data"):
        _sample_physiology(model, pd.DataFrame(index=[0]), group_name="basal")


def test_write_virtual_nodes_rejects_non_positive_count(tmp_path):
    with pytest.raises(ValueError, match="must be positive"):
        write_virtual_nodes(tmp_path / "nodes.h5", "sources", 0)


def test_build_wraps_virtual_node_writer_failure(tmp_path, stage_memodel, monkeypatch):
    stage_memodel()

    def reject_virtual_nodes(*_args, **_kwargs):
        write_virtual_nodes(tmp_path / "invalid-nodes.h5", "sources", 0)

    monkeypatch.setattr(
        "obi_one.scientific.library.build_synaptome.write_virtual_nodes",
        reject_virtual_nodes,
    )

    with pytest.raises(BuildSynaptomeError, match="Failed to write a valid SONATA artifact") as exc:
        build_synaptome(_config(), tmp_path / "artifact", db_client=object())

    assert isinstance(exc.value.__cause__, ValueError)
