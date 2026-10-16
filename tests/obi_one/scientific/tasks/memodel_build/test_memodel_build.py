from types import SimpleNamespace
from unittest.mock import Mock, call
from uuid import uuid4

import pytest
from entitysdk.models import MEModel
from entitysdk.types import AssetLabel, TaskActivityType, TaskConfigType, ValidationStatus

from obi_one.core.info import Info
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.emodel_from_id import EModelFromID
from obi_one.scientific.mappings_and_registry.config_task_map import (
    get_task_spec_for_scan_config,
)
from obi_one.scientific.tasks.memodel_build import (
    MEModelBuildScanConfig,
    MEModelBuildSingleConfig,
    MEModelBuildTask,
    registration,
    task as task_module,
)

MORPHOLOGY_ID = str(uuid4())
EMODEL_ID = str(uuid4())
MEMODEL_ID = uuid4()
ACTIVITY_ID = str(uuid4())
CALIBRATION = {"holding_current": -0.05, "rheobase": 0.2, "rin": 120.0}
VALIDATION = {"spiking": {"name": "Spiking", "passed": False, "figures": []}}


def _scan_config():
    return MEModelBuildScanConfig(
        info=Info(campaign_name="L5 TPC", campaign_description="Built from a morphology"),
        initialize=MEModelBuildScanConfig.Initialize(
            morphology=CellMorphologyFromID(id_str=MORPHOLOGY_ID),
            emodel=EModelFromID(id_str=EMODEL_ID),
        ),
    )


def _task(tmp_path):
    form = _scan_config().model_dump(exclude={"type"})
    return MEModelBuildTask(
        config=MEModelBuildSingleConfig.model_validate(
            form | {"idx": 0, "coordinate_output_root": tmp_path}
        )
    )


def _db_client(*, authorized_public=False):
    db_client = Mock()
    db_client.get_entity.return_value = SimpleNamespace(
        id=ACTIVITY_ID, authorized_public=authorized_public
    )
    return db_client


class TestConfig:
    def test_registered_with_the_memodel_build_entity_types(self):
        task_spec = get_task_spec_for_scan_config(MEModelBuildScanConfig)

        assert task_spec.asset_label == AssetLabel.task_config
        assert task_spec.campaign_task_config_type == TaskConfigType.memodel_build__campaign
        assert task_spec.single_task_config_type == TaskConfigType.memodel_build__config
        assert (
            task_spec.campaign_generation_task_activity_type
            == TaskActivityType.memodel_build__config_generation
        )
        assert task_spec.single_task_activity_type == TaskActivityType.memodel_build__execution

    def test_inputs_are_single_entities_not_scan_dimensions(self):
        fields = MEModelBuildScanConfig.Initialize.model_fields

        assert fields["morphology"].annotation is CellMorphologyFromID
        assert fields["emodel"].annotation is EModelFromID

    def test_input_entities_are_the_morphology_and_the_emodel(self, monkeypatch):
        morphology, emodel = object(), object()
        monkeypatch.setattr(CellMorphologyFromID, "entity", Mock(return_value=morphology))
        monkeypatch.setattr(EModelFromID, "entity", Mock(return_value=emodel))

        assert _scan_config().input_entities(db_client=Mock()) == [morphology, emodel]


@pytest.fixture
def steps(monkeypatch, tmp_path):
    """Replace every step of the task with a mock attached to one parent, to see their order."""
    parent = Mock()
    parent.register_memodel.return_value = SimpleNamespace(id=MEMODEL_ID, name="L5 TPC")
    parent.stage_memodel.return_value = (tmp_path / "cell.hoc", tmp_path / "cell.asc")
    parent.compute.return_value = {"calibration": CALIBRATION, "validation": VALIDATION}
    monkeypatch.setattr(registration, "register_memodel", parent.register_memodel)
    monkeypatch.setattr(task_module, "stage_memodel", parent.stage_memodel)
    monkeypatch.setattr(task_module, "compute_calibration_and_validation", parent.compute)
    monkeypatch.setattr(
        registration, "register_calibration_and_validation", parent.register_results
    )
    monkeypatch.setattr(registration, "set_validation_status", parent.set_validation_status)
    monkeypatch.setattr(
        task_module.Task, "_update_execution_activity", parent.update_execution_activity
    )
    return parent


class TestExecute:
    def test_registers_links_calibrates_validates_then_sets_done(self, tmp_path, steps):
        db_client = _db_client()

        memodel_id = _task(tmp_path).execute(db_client=db_client, execution_activity_id=ACTIVITY_ID)

        assert memodel_id == str(MEMODEL_ID)
        assert [name for name, *_ in steps.mock_calls] == [
            "register_memodel",
            "update_execution_activity",
            "stage_memodel",
            "compute",
            "register_results",
            "set_validation_status",
        ]
        assert steps.update_execution_activity.call_args.kwargs["generated"] == [str(MEMODEL_ID)]
        compute_kwargs = steps.compute.call_args.kwargs
        assert compute_kwargs["holding_current"] == task_module.INITIAL_HOLDING_CURRENT
        assert compute_kwargs["threshold_current"] == task_module.INITIAL_THRESHOLD_CURRENT
        assert compute_kwargs["cell_name"] == "L5 TPC"
        steps.register_results.assert_called_once_with(
            db_client,
            memodel_id=MEMODEL_ID,
            calibration=CALIBRATION,
            validation=VALIDATION,
            authorized_public=False,
        )
        # done means validation ran, whether or not every test passed
        steps.set_validation_status.assert_called_once_with(
            db_client, memodel_id=MEMODEL_ID, validation_status=ValidationStatus.done
        )

    def test_follows_the_activity_visibility(self, tmp_path, steps):
        _task(tmp_path).execute(
            db_client=_db_client(authorized_public=True), execution_activity_id=ACTIVITY_ID
        )

        assert steps.register_memodel.call_args.kwargs["authorized_public"] is True
        assert steps.register_results.call_args.kwargs["authorized_public"] is True

    @pytest.mark.parametrize("failing_step", ["stage_memodel", "compute", "register_results"])
    def test_failure_after_registration_sets_error_and_raises(self, tmp_path, steps, failing_step):
        getattr(steps, failing_step).side_effect = RuntimeError("NEURON crashed")
        db_client = _db_client()

        with pytest.raises(RuntimeError, match="NEURON crashed"):
            _task(tmp_path).execute(db_client=db_client, execution_activity_id=ACTIVITY_ID)

        steps.update_execution_activity.assert_called_once()
        steps.set_validation_status.assert_called_once_with(
            db_client, memodel_id=MEMODEL_ID, validation_status=ValidationStatus.error
        )

    def test_failed_registration_leaves_nothing_to_mark(self, tmp_path, steps):
        steps.register_memodel.side_effect = RuntimeError("entitycore down")

        with pytest.raises(RuntimeError, match="entitycore down"):
            _task(tmp_path).execute(db_client=_db_client(), execution_activity_id=ACTIVITY_ID)

        steps.update_execution_activity.assert_not_called()
        steps.set_validation_status.assert_not_called()


@pytest.fixture
def inputs(monkeypatch):
    """Morphology, e-model and their metadata, as the FromID refs resolve them."""
    morphology = SimpleNamespace(
        subject=SimpleNamespace(strain=object()), mtypes=[SimpleNamespace(id=uuid4())]
    )
    emodel = SimpleNamespace(etypes=[SimpleNamespace(id=uuid4())])
    species, brain_region = object(), object()
    monkeypatch.setattr(CellMorphologyFromID, "entity", Mock(return_value=morphology))
    monkeypatch.setattr(
        CellMorphologyFromID, "metadata_entities", Mock(return_value=(species, brain_region))
    )
    monkeypatch.setattr(EModelFromID, "entity", Mock(return_value=emodel))
    return SimpleNamespace(
        morphology=morphology, emodel=emodel, species=species, brain_region=brain_region
    )


@pytest.fixture
def entity_classes(monkeypatch):
    classes = Mock()
    monkeypatch.setattr(registration, "MEModel", classes.MEModel)
    monkeypatch.setattr(registration, "Contribution", classes.Contribution)
    monkeypatch.setattr(registration, "register_mtype_classification", classes.register_mtype)
    monkeypatch.setattr(registration, "register_etype_classification", classes.register_etype)
    return classes


class TestRegistration:
    def test_register_memodel(self, tmp_path, inputs, entity_classes):
        db_client = Mock()
        memodel = SimpleNamespace(id=MEMODEL_ID, created_by=SimpleNamespace(id="user-sub"))
        creator, creator_role = object(), object()
        db_client.register_entity.side_effect = [memodel, object()]
        db_client.search_entity.return_value.one.side_effect = [creator, creator_role]

        result = registration.register_memodel(
            _task(tmp_path).config, db_client, authorized_public=True
        )

        assert result is memodel
        entity_classes.MEModel.assert_called_once_with(
            name="L5 TPC",
            description="Built from a morphology",
            morphology=inputs.morphology,
            emodel=inputs.emodel,
            species=inputs.species,
            strain=inputs.morphology.subject.strain,
            brain_region=inputs.brain_region,
            validation_status=ValidationStatus.created,
            authorized_public=True,
        )
        assert db_client.search_entity.call_args_list[0].kwargs["query"] == {"sub_id": "user-sub"}
        assert db_client.search_entity.call_args_list[1].kwargs["query"] == {
            "name": registration.CREATOR_ROLE_NAME
        }
        entity_classes.Contribution.assert_called_once_with(
            agent=creator, role=creator_role, entity=memodel
        )
        entity_classes.register_mtype.assert_called_once_with(
            client=db_client, entity=memodel, mtype_class=inputs.morphology.mtypes[0]
        )
        entity_classes.register_etype.assert_called_once_with(
            client=db_client, entity=memodel, etype_class=inputs.emodel.etypes[0]
        )

    def test_register_calibration_and_validation(self, monkeypatch):
        register_calibration = Mock()
        register_validation = Mock()
        monkeypatch.setattr(
            registration, "register_memodel_calibration_result", register_calibration
        )
        monkeypatch.setattr(
            registration, "register_memodel_validation_results", register_validation
        )
        db_client = Mock()

        registration.register_calibration_and_validation(
            db_client,
            memodel_id=MEMODEL_ID,
            calibration=CALIBRATION,
            validation=VALIDATION,
            authorized_public=False,
        )

        register_calibration.assert_called_once_with(
            client=db_client,
            calibrated_entity_id=MEMODEL_ID,
            holding_current=-0.05,
            threshold_current=0.2,
            rin=120.0,
            authorized_public=False,
        )
        register_validation.assert_called_once_with(
            client=db_client,
            memodel_id=MEMODEL_ID,
            validation_dict=VALIDATION,
            authorized_public=False,
        )

    def test_set_validation_status(self):
        db_client = Mock()

        registration.set_validation_status(
            db_client, memodel_id=MEMODEL_ID, validation_status=ValidationStatus.error
        )

        assert db_client.update_entity.call_args == call(
            entity_id=MEMODEL_ID,
            entity_type=MEModel,
            attrs_or_entity={"validation_status": ValidationStatus.error},
        )


def test_stage_memodel_compiles_into_the_coordinate_root(tmp_path, monkeypatch):
    downloaded = SimpleNamespace(
        hoc_path=tmp_path / "hoc" / "cell.hoc",
        mechanisms_dir=tmp_path / "mechanisms",
        morphology_paths=[tmp_path / "morphology" / "asc" / "cell.asc"],
    )
    download = Mock(return_value=downloaded)
    compile_mechanisms = Mock()
    monkeypatch.setattr(task_module, "download_memodel", download)
    monkeypatch.setattr(task_module, "compile_mechanisms", compile_mechanisms)
    db_client, memodel = Mock(), Mock()

    staged = task_module.stage_memodel(db_client, memodel, tmp_path)

    assert staged == (downloaded.hoc_path, downloaded.morphology_paths[0])
    assert download.call_args.kwargs["output_dir"] == tmp_path
    assert compile_mechanisms.call_args.kwargs["output_dir"] == tmp_path
    assert compile_mechanisms.call_args.kwargs["mechanisms_dirs"] == [downloaded.mechanisms_dir]
