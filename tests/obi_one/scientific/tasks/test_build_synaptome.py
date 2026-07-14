import json
from pathlib import Path
from types import SimpleNamespace

import bluepysnap
import h5py
import morphio
import numpy as np
import pytest

from obi_one.core.info import Info
from obi_one.scientific.blocks.distributions.constant import FloatConstantDistribution
from obi_one.scientific.blocks.distributions.normal import NormalDistribution
from obi_one.scientific.blocks.morphology_locations.path_distance import (
    PathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.random import RandomMorphologyLocations
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.build_synaptome import BuildSynaptomeError
from obi_one.scientific.tasks.build_synaptome import (
    BuildSynaptomeScanConfig,
    BuildSynaptomeSingleConfig,
    SynapseGroup,
    build_synaptome,
)
from obi_one.scientific.unions.unions_distributions import AllDistributionsReference
from obi_one.scientific.unions.unions_synaptic_models import SynapticModelReference

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
) -> Path:
    path.mkdir()
    (path / "hoc").mkdir()
    (path / "morphologies").mkdir()
    if include_morphology:
        (path / "morphologies" / "cell.swc").write_text(_SWC_MORPHOLOGY)
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
        failure: Exception | None = None,
    ):
        def load_morphology(_self, db_client):  # noqa: ARG001
            if not include_morphology:
                msg = "missing morphology asset"
                raise ValueError(msg)
            return morphio.Morphology(_SWC_MORPHOLOGY, "swc")

        def stage(_self, *, db_client, dest_dir, entity_cache=False):  # noqa: ARG001
            if failure is not None:
                raise failure
            config_path = _write_staged_memodel(
                dest_dir,
                include_morphology=include_morphology,
            )
            return SimpleNamespace(path=str(config_path))

        monkeypatch.setattr(MEModelFromID, "morphio_morphology", load_morphology)
        monkeypatch.setattr(MEModelFromID, "stage_circuit", stage)

    return configure


def _reference(name: str) -> SynapticModelReference:
    return SynapticModelReference(block_dict_name="synaptic_models", block_name=name)


def _config(
    *,
    groups: dict[str, SynapseGroup] | None = None,
    distributed: bool = False,
) -> BuildSynaptomeSingleConfig:
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
    if groups is None:
        groups = {
            "basal": SynapseGroup(
                synaptic_model=_reference("exc"),
                placement_strategy=RandomMorphologyLocations(
                    number_of_locations=4, section_types=(3,), random_seed=11
                ),
            )
        }
    return BuildSynaptomeSingleConfig(
        info=Info(campaign_name="test", campaign_description="test synaptome"),
        initialize=BuildSynaptomeScanConfig.Initialize(
            me_model=MEModelFromID(id_str="test-me-model")
        ),
        distributions=distributions,
        synaptic_models=models,
        synapse_groups=groups,
    )


def _edge_frame(result, edge_name: str):
    circuit = bluepysnap.Circuit(result.circuit_config_path)
    edge = circuit.edges[edge_name]
    return edge.get(edge.ids(), properties=sorted(edge.property_names))


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


def test_multiple_groups_use_independent_placement_and_physiology(tmp_path, stage_memodel):
    stage_memodel()
    groups = {
        "basal": SynapseGroup(
            synaptic_model=_reference("exc"),
            placement_strategy=RandomMorphologyLocations(
                number_of_locations=3, section_types=(3,), random_seed=1
            ),
        ),
        "apical": SynapseGroup(
            synaptic_model=_reference("inh"),
            placement_strategy=PathDistanceMorphologyLocations(
                number_of_locations=2,
                section_types=(4,),
                path_dist_mean=20.0,
                path_dist_tolerance=30.0,
                random_seed=9,
            ),
        ),
    }
    result = build_synaptome(_config(groups=groups), tmp_path / "artifact", db_client=object())
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
    groups = {
        "basal": SynapseGroup(
            synaptic_model=_reference("exc"),
            placement_strategy=RandomMorphologyLocations(
                number_of_locations=4, section_types=(3,), random_seed=12
            ),
        )
    }
    second = build_synaptome(_config(groups=groups), tmp_path / "second", db_client=object())
    edge_name = "synaptome_basal__target__chemical"
    columns = ["afferent_section_id", "afferent_segment_id", "afferent_segment_offset"]

    assert not _edge_frame(first, edge_name)[columns].equals(
        _edge_frame(second, edge_name)[columns]
    )


def test_placement_does_not_mutate_global_numpy_rng(tmp_path, stage_memodel):
    stage_memodel()
    np.random.seed(123)  # noqa: NPY002 - verifies isolation from the legacy placer RNG
    expected = np.random.random(3)  # noqa: NPY002
    np.random.seed(123)  # noqa: NPY002
    build_synaptome(_config(), tmp_path / "artifact", db_client=object())

    np.testing.assert_array_equal(np.random.random(3), expected)  # noqa: NPY002


def test_impossible_section_constraint_identifies_group(tmp_path, stage_memodel):
    stage_memodel()
    groups = {
        "axon-only": SynapseGroup(
            synaptic_model=_reference("exc"),
            placement_strategy=RandomMorphologyLocations(
                number_of_locations=2, section_types=(2,), random_seed=1
            ),
        )
    }

    with pytest.raises(BuildSynaptomeError, match=r"axon-only.*could not generate locations"):
        build_synaptome(_config(groups=groups), tmp_path / "artifact", db_client=object())


def test_missing_morphology_is_reported(tmp_path, stage_memodel):
    stage_memodel(include_morphology=False)

    with pytest.raises(BuildSynaptomeError, match="Unable to load morphology for ME-model"):
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
