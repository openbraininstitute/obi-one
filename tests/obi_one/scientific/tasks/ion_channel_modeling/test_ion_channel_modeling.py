import pickle  # ruff: ignore[suspicious-pickle-import]
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import neuron
import pytest
from entitysdk import models
from entitysdk.types import AssetLabel, Sex, TaskActivityType, TaskConfigType
from pydantic import ValidationError

from obi_one.core.exception import ConfigValidationError
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.db_sdk import db_sdk
from obi_one.scientific.mappings_and_registry.config_task_map import (
    get_task_spec_for_scan_config,
)
from obi_one.scientific.tasks import ion_channel_modeling
from obi_one.scientific.tasks.ion_channel_modeling import (
    HodgkinHuxleyIonChannelModel,
    IonChannelFittingScanConfig,
    IonChannelFittingSingleConfig,
    IonChannelFittingTask,
    neuron_safe_name,
    plot_fitted_model,
    plot_in_fresh_process,
)


def test_model_properties_default_to_the_recordings():
    initialize = IonChannelFittingScanConfig.Initialize(
        recordings=[{"id_str": "00000000-0000-0000-0000-000000000000"}]
    )

    assert initialize.model_properties.model_dump(exclude={"type"}) == {
        "ion_channel_name": None,
        "temperature": None,
        "species": None,
        "strain": None,
        "brain_region": None,
    }


def test_ion_channel_name_rejects_a_name_neuron_could_not_use():
    with pytest.raises(ValidationError):
        IonChannelFittingScanConfig.Initialize(
            recordings=[{"id_str": "00000000-0000-0000-0000-000000000000"}],
            model_properties={"ion_channel_name": "3 bad name"},
        )


def test_a_config_from_before_model_properties_keeps_its_channel_name():
    initialize = IonChannelFittingScanConfig.Initialize(
        recordings=[{"id_str": "00000000-0000-0000-0000-000000000000"}],
        ion_channel_name="Kv3_1",
    )

    assert initialize.model_properties.ion_channel_name == "Kv3_1"


@pytest.mark.parametrize(
    ("name", "suffix"), [("Kv6.2", "Kv6_2"), ("ClC-Ka", "ClC_Ka"), ("5-HT3", "_5_HT3")]
)
def test_channel_names_become_neuron_suffixes(name, suffix):
    assert neuron_safe_name(name) == suffix


def test_recordings_are_kept_together_rather_than_scanned():
    annotation = IonChannelFittingScanConfig.Initialize.model_fields["recordings"].annotation

    assert getattr(annotation, "__origin__", None) is tuple


def test_registration_uses_the_generic_ion_channel_modeling_task_entities():
    task_spec = get_task_spec_for_scan_config(IonChannelFittingScanConfig)

    assert task_spec is not None
    assert task_spec.asset_label == AssetLabel.task_config
    assert task_spec.campaign_task_config_type == TaskConfigType.ion_channel_modeling__campaign
    assert task_spec.single_task_config_type == TaskConfigType.ion_channel_modeling__config
    assert (
        task_spec.campaign_generation_task_activity_type
        == TaskActivityType.ion_channel_modeling__config_generation
    )
    assert task_spec.single_task_activity_type == TaskActivityType.ion_channel_modeling__execution


RECORDING_IDS = ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"]

RAT = SimpleNamespace(id=uuid4(), name="Rattus norvegicus")
MOUSE = SimpleNamespace(id=uuid4(), name="Mus musculus")
SPRAGUE_DAWLEY = SimpleNamespace(id=uuid4(), name="Sprague Dawley", species_id=RAT.id)
GENERIC_RAT = SimpleNamespace(
    id=uuid4(), name="Generic Rattus norvegicus", species=RAT, strain=None
)
GENERIC_MOUSE = SimpleNamespace(id=uuid4(), name="Generic Mus musculus", species=MOUSE, strain=None)
ROOT = SimpleNamespace(id=uuid4(), name="root", parent_structure_id=None)
GREY = SimpleNamespace(
    id=uuid4(), name="Basic cell groups and regions", parent_structure_id=ROOT.id
)
ISOCORTEX = SimpleNamespace(id=uuid4(), name="Isocortex", parent_structure_id=GREY.id)
THALAMUS = SimpleNamespace(id=uuid4(), name="Thalamus", parent_structure_id=GREY.id)
KV62 = SimpleNamespace(id=uuid4(), name="Kv6.2")
KV11 = SimpleNamespace(id=uuid4(), name="Kv1.1")


def _recording(id_, **overrides):
    return SimpleNamespace(
        id=id_,
        ljp=-float(id_[-1]),
        name=f"Recording {id_[-1]}",
        **{
            "temperature": 25.0,
            "subject": GENERIC_RAT,
            "brain_region": ISOCORTEX,
            "ion_channel": KV62,
            **overrides,
        },
    )


def _db_client(*overrides):
    """A client serving the two recordings, each with its overrides, and the taxonomy above."""
    recordings = {
        id_: _recording(id_, **override)
        for id_, override in zip(RECORDING_IDS, overrides or ({}, {}), strict=True)
    }
    by_id = {
        str(item.id): item for item in (RAT, MOUSE, SPRAGUE_DAWLEY, ROOT, GREY, ISOCORTEX, THALAMUS)
    }
    db_client = Mock()
    db_client.get_entity.side_effect = lambda entity_id, entity_type: (
        by_id[str(entity_id)]
        if entity_type is not models.IonChannelRecording
        else recordings[entity_id]
    )
    db_client.search_entity.return_value = []
    db_client.download_assets.side_effect = lambda _entity, output_path, **_: Mock(
        one=Mock(return_value=Mock(path=output_path / "trace.nwb"))
    )
    return db_client


def _scan_config(model_properties=None, **model_type):
    return IonChannelFittingScanConfig.model_validate(
        {
            "info": {"campaign_name": "Kv3.1 fit", "campaign_description": "From traces."},
            "initialize": {
                "recordings": [{"id_str": id_} for id_ in RECORDING_IDS],
                "model_properties": model_properties or {},
            },
            "model_type": {"type": "HodgkinHuxleyIonChannelModel", **model_type},
        }
    )


def _resolve(db_client, **model_properties):
    config = _scan_config(model_properties)
    return config.resolve_model_properties(
        config.input_entities(db_client=db_client), db_client=db_client
    )


def test_every_recording_is_an_input_of_the_task_config():
    recordings = _scan_config().input_entities(db_client=_db_client())

    assert [recording.id for recording in recordings] == RECORDING_IDS


def test_exponents_can_be_swept():
    model = HodgkinHuxleyIonChannelModel(m_power=[1, 2], h_power=[0, 4])

    assert model.m_power == [1, 2]
    assert model.h_power == [0, 4]


@pytest.mark.parametrize(
    "exponents",
    [{"m_power": 0}, {"m_power": [1, 5]}, {"h_power": -1}, {"h_power": [0, 5]}],
)
def test_exponents_out_of_range_are_rejected(exponents):
    with pytest.raises(ValidationError):
        HodgkinHuxleyIonChannelModel(**exponents)


def test_generate_registers_a_campaign_and_one_config_per_exponent(tmp_path, monkeypatch):
    task_configs = []
    activities = []

    def register_task_config_with_asset(**kwargs):
        task_configs.append(kwargs)
        return Mock(id=f"task config {len(task_configs)}"), Mock()

    monkeypatch.setattr(db_sdk, "register_task_config_with_asset", register_task_config_with_asset)
    monkeypatch.setattr(
        db_sdk, "create_generic_activity", lambda **kwargs: activities.append(kwargs)
    )
    GridScanGenerationTask(
        form=_scan_config(m_power=[1, 2]),
        output_root=tmp_path,
        coordinate_directory_option="ZERO_INDEX",
    ).execute(db_client=_db_client())

    campaign, *configs = task_configs
    assert campaign["task_config_type"] == TaskConfigType.ion_channel_modeling__campaign
    assert [r.id for r in campaign["input_entities"]] == RECORDING_IDS
    assert [c["task_config_type"] for c in configs] == [
        TaskConfigType.ion_channel_modeling__config
    ] * 2
    assert all([r.id for r in c["input_entities"]] == RECORDING_IDS for c in configs)
    assert all(c["task_config_generator_id"] == "task config 1" for c in configs)
    (generation,) = activities
    assert generation["activity_type"] == TaskActivityType.ion_channel_modeling__config_generation
    assert [c.id for c in generation["generated"]] == ["task config 2", "task config 3"]


def test_properties_the_recordings_share_go_to_the_model():
    properties = _resolve(_db_client())

    assert properties.ion_channel_name == "Kv6_2"
    assert properties.temperature == pytest.approx(25.0)
    assert properties.species is RAT
    assert properties.strain is None
    assert properties.brain_region is ISOCORTEX
    assert properties.subject is GENERIC_RAT


def test_a_set_property_wins_over_the_recordings():
    properties = _resolve(
        _db_client(),
        ion_channel_name="kv62_fast",
        temperature=34.0,
        brain_region={"id_str": str(GREY.id)},
    )

    assert properties.ion_channel_name == "kv62_fast"
    assert properties.temperature == pytest.approx(34.0)
    assert properties.brain_region is GREY


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"temperature": None}, r"differ in temperature \(25.0 °C, none\)"),
        ({"ion_channel": KV11}, r"differ in ion channel \(Kv1.1, Kv6.2\)"),
        ({"subject": GENERIC_MOUSE}, r"differ in species \(Mus musculus, Rattus norvegicus\)"),
    ],
)
def test_a_property_the_recordings_differ_in_has_to_be_set(overrides, message):
    with pytest.raises(ConfigValidationError, match=message):
        _resolve(_db_client({}, overrides))


def test_recordings_of_different_species_take_the_species_that_is_set():
    properties = _resolve(
        _db_client({}, {"subject": GENERIC_MOUSE}), species={"id_str": str(MOUSE.id)}
    )

    assert properties.species is MOUSE
    assert properties.subject is None


def test_the_strain_comes_from_the_recordings_of_the_models_species():
    sprague_dawley_rat = SimpleNamespace(
        id=uuid4(), name="Rat 1", species=RAT, strain=SPRAGUE_DAWLEY
    )
    properties = _resolve(
        _db_client({"subject": sprague_dawley_rat}, {"subject": GENERIC_MOUSE}),
        species={"id_str": str(RAT.id)},
    )

    assert properties.strain is SPRAGUE_DAWLEY
    assert properties.subject is None


def test_a_strain_of_another_species_is_rejected():
    with pytest.raises(ConfigValidationError, match="not a strain of Mus musculus"):
        _resolve(
            _db_client(),
            species={"id_str": str(MOUSE.id)},
            strain={"id_str": str(SPRAGUE_DAWLEY.id)},
        )


def test_recordings_in_different_regions_give_their_common_parent():
    properties = _resolve(_db_client({}, {"brain_region": THALAMUS}))

    assert properties.brain_region is GREY


def test_generate_rejects_an_unresolved_property_before_registering_anything(tmp_path, monkeypatch):
    register = Mock()
    monkeypatch.setattr(db_sdk, "register_task_config_with_asset", register)

    with pytest.raises(ConfigValidationError):
        GridScanGenerationTask(
            form=_scan_config(),
            output_root=tmp_path,
            coordinate_directory_option="ZERO_INDEX",
        ).execute(db_client=_db_client({}, {"temperature": 34.0}))

    register.assert_not_called()


def _task(tmp_path, model_properties=None):
    form = _scan_config(model_properties).model_dump(exclude={"type"})
    return IonChannelFittingTask(
        config=IonChannelFittingSingleConfig.model_validate(
            form | {"idx": 0, "coordinate_output_root": tmp_path}
        )
    )


def test_each_recording_is_downloaded_to_its_own_folder(tmp_path):
    trace_paths, trace_ljps = _task(tmp_path).download_input(db_client=_db_client())

    assert trace_paths == [tmp_path / "recordings" / id_ / "trace.nwb" for id_ in RECORDING_IDS]
    assert trace_ljps == [-1.0, -2.0]


def _species(name, taxonomy_id):
    return models.Species(id=uuid4(), name=name, taxonomy_id=taxonomy_id)


def _region():
    return models.BrainRegion(
        id=uuid4(),
        name="Isocortex",
        annotation_value=1,
        acronym="Isocortex",
        parent_structure_id=None,
        hierarchy_id=uuid4(),
        color_hex_triplet="red",
    )


def _save(tmp_path, db_client, *, subject, species):
    task = _task(tmp_path)
    properties = ion_channel_modeling.ResolvedModelProperties(
        ion_channel_name="Kv6_2",
        temperature=25.0,
        species=species,
        strain=None,
        brain_region=_region(),
        subject=subject,
    )
    task.save(
        mod_filepath=tmp_path / "Kv6_2.mod",
        figure_filepaths={},
        db_client=db_client,
        range_vars=[],
        properties=properties,
    )
    return [call.args[0] for call in db_client.register_entity.call_args_list]


def test_the_registered_model_takes_the_resolved_properties(tmp_path):
    db_client = _db_client()
    db_client.register_entity.side_effect = lambda entity: entity
    mouse = _species("Mus musculus", "NCBITaxon:10090")
    subject = models.Subject(id=uuid4(), name="Mouse 1", sex=Sex.male, species=mouse)

    (model,) = _save(tmp_path, db_client, subject=subject, species=mouse)

    assert "made using recordings: Recording 1, Recording 2 " in model.description
    assert model.nmodl_suffix == "Kv6_2"
    assert model.conductance_name == "gKv6_2bar"
    assert model.temperature_celsius == pytest.approx(25.0)
    assert model.subject is subject


def test_a_model_of_several_subjects_gets_the_generic_subject_of_its_species(tmp_path):
    db_client = _db_client()
    db_client.register_entity.side_effect = lambda entity: entity
    mouse = _species("Mus musculus", "NCBITaxon:10090")
    rat = _species("Rattus norvegicus", "NCBITaxon:10116")
    generic_mouse = models.Subject(
        id=uuid4(), name="Generic Mus musculus", sex=Sex.unknown, species=mouse
    )
    db_client.search_entity.return_value = [
        models.Subject(id=uuid4(), name="Generic Mus musculus", sex=Sex.unknown, species=rat),
        generic_mouse,
    ]

    (model,) = _save(tmp_path, db_client, subject=None, species=mouse)

    assert db_client.search_entity.call_args.kwargs["query"] == {"name": "Generic Mus musculus"}
    assert model.subject is generic_mouse


def test_a_missing_generic_subject_is_registered(tmp_path):
    db_client = _db_client()
    db_client.register_entity.side_effect = lambda entity: entity
    mouse = _species("Mus musculus", "NCBITaxon:10090")

    subject, model = _save(tmp_path, db_client, subject=None, species=mouse)

    assert (subject.name, subject.sex, subject.species) == (
        "Generic Mus musculus",
        "unknown",
        mouse,
    )
    assert model.subject is subject


def test_plotting_reports_the_fresh_process_error(tmp_path):
    with pytest.raises(RuntimeError, match="No compiled mechanisms found"):
        plot_in_fresh_process(tmp_path)


def test_the_plotting_process_returns_the_figures_through_its_file(tmp_path, monkeypatch):
    monkeypatch.setattr(neuron, "load_mechanisms", lambda _path: True)
    monkeypatch.setattr(
        ion_channel_modeling,
        "run_ion_channel_model",
        lambda **kwargs: {"traces": tmp_path / f"{kwargs['mech_suffix']}.pdf"},
    )
    io_path = tmp_path / "plot_fitted_model.pkl"
    io_path.write_bytes(pickle.dumps((tmp_path, {"mech_suffix": "kt"})))

    plot_fitted_model(str(io_path))

    assert pickle.loads(io_path.read_bytes()) == {"traces": tmp_path / "kt.pdf"}  # ruff: ignore[suspicious-pickle-usage]
