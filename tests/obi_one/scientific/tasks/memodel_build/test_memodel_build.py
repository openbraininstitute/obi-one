from types import SimpleNamespace
from unittest.mock import Mock, call
from uuid import uuid4

import pytest
from entitysdk.models import MEModel
from entitysdk.types import (
    AssetLabel,
    ContentType,
    TaskActivityType,
    TaskConfigType,
    ValidationStatus,
)

from obi_one.core.info import Info
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.emodel_from_id import EModelFromID
from obi_one.scientific.mappings_and_registry.config_task_map import (
    get_task_spec_for_scan_config,
)
from obi_one.scientific.tasks.memodel_build import registration, task as task_module
from obi_one.scientific.tasks.memodel_build.config import (
    MEModelBuildScanConfig,
    MEModelBuildSingleConfig,
)
from obi_one.scientific.tasks.memodel_build.task import MEModelBuildTask

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
def build_inputs(monkeypatch):
    """Morphology, e-model and metadata resolved once at the start of the build."""
    morphology = SimpleNamespace(
        id=uuid4(),
        assets=[SimpleNamespace(content_type=ContentType.application_asc)],
        subject=SimpleNamespace(strain=object()),
        mtypes=[SimpleNamespace(id=uuid4())],
        ion_channel_models=None,
    )
    emodel = SimpleNamespace(
        id=uuid4(),
        etypes=[SimpleNamespace(id=uuid4())],
        ion_channel_models=[SimpleNamespace(id=uuid4())],
    )
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
def steps(monkeypatch, tmp_path, build_inputs):
    """Replace every step of the task with a mock attached to one parent, to see their order."""
    parent = Mock()
    parent.register_memodel.return_value = SimpleNamespace(id=MEMODEL_ID)
    parent.stage_memodel.return_value = SimpleNamespace(
        hoc_path=tmp_path / "cell.hoc",
        mechanisms_dir=tmp_path / "mechanisms",
        morphology_paths=[tmp_path / "cell.asc", tmp_path / "cell.swc"],
    )
    parent.calibrate.return_value = CALIBRATION
    parent.validate.return_value = VALIDATION
    monkeypatch.setattr(registration, "register_memodel", parent.register_memodel)
    monkeypatch.setattr(task_module, "stage_memodel", parent.stage_memodel)
    monkeypatch.setattr(task_module, "compile_mechanisms", parent.compile)
    monkeypatch.setattr(task_module, "compute_calibration_in_subprocess", parent.calibrate)
    monkeypatch.setattr(task_module, "run_validations_in_subprocess", parent.validate)
    monkeypatch.setattr(
        task_module, "register_memodel_validation_results", parent.register_validation
    )
    monkeypatch.setattr(registration, "set_validation_status", parent.set_validation_status)
    monkeypatch.delenv("JOB_CPUS", raising=False)
    monkeypatch.setattr(
        task_module.Task, "_update_execution_activity", parent.update_execution_activity
    )
    parent.inputs = build_inputs
    return parent


class TestExecute:
    def test_stages_calibrates_registers_then_validates(self, tmp_path, steps):
        db_client = _db_client()
        task = _task(tmp_path)

        memodel_id = task.execute(db_client=db_client, execution_activity_id=ACTIVITY_ID)

        assert memodel_id == str(MEMODEL_ID)
        assert [name for name, *_ in steps.mock_calls] == [
            "stage_memodel",
            "compile",
            "calibrate",
            "register_memodel",
            "update_execution_activity",
            "validate",
            "register_validation",
            "set_validation_status",
        ]
        steps.stage_memodel.assert_called_once_with(
            db_client=db_client,
            morphology=steps.inputs.morphology,
            emodel=steps.inputs.emodel,
            output_dir=tmp_path,
        )
        assert steps.compile.call_args.kwargs == {
            "output_dir": tmp_path,
            "mechanisms_dirs": [tmp_path / "mechanisms"],
            "simulation_backend": task_module.SimulationBackend.bluecellulab,
        }
        assert steps.calibrate.call_args.kwargs == {
            "coord_root": tmp_path,
            "hoc_path": tmp_path / "cell.hoc",
            "morphology_path": tmp_path / "cell.asc",
            "holding_current": task_module.INITIAL_HOLDING_CURRENT,
            "threshold_current": task_module.INITIAL_THRESHOLD_CURRENT,
        }
        assert steps.register_memodel.call_args.kwargs == {
            "config": task.config,
            "db_client": db_client,
            "morphology": steps.inputs.morphology,
            "emodel": steps.inputs.emodel,
            "species": steps.inputs.species,
            "brain_region": steps.inputs.brain_region,
            "holding_current": CALIBRATION["holding_current"],
            "threshold_current": CALIBRATION["rheobase"],
            "rin": CALIBRATION["rin"],
            "authorized_public": False,
        }
        assert steps.update_execution_activity.call_args.kwargs["generated"] == [str(MEMODEL_ID)]
        assert steps.validate.call_args.kwargs == {
            "coord_root": tmp_path,
            "hoc_path": tmp_path / "cell.hoc",
            "morphology_path": tmp_path / "cell.asc",
            "cell_name": str(MEMODEL_ID),
            "holding_current": CALIBRATION["holding_current"],
            "threshold_current": CALIBRATION["rheobase"],
            "output_dir": tmp_path / task_module.VALIDATION_FIGURES_DIRNAME,
            "n_processes": task_module.DEFAULT_VALIDATION_PROCESSES,
        }
        steps.register_validation.assert_called_once_with(
            client=db_client,
            memodel_id=MEMODEL_ID,
            validation_dict=VALIDATION,
            authorized_public=False,
        )
        # done means validation ran, whether or not every test passed
        steps.set_validation_status.assert_called_once_with(
            db_client=db_client,
            memodel_id=MEMODEL_ID,
            validation_status=ValidationStatus.done,
        )

    def test_validates_on_the_launch_system_job_cpus(self, tmp_path, steps, monkeypatch):
        monkeypatch.setenv("JOB_CPUS", "2")

        _task(tmp_path).execute(db_client=_db_client(), execution_activity_id=ACTIVITY_ID)

        assert steps.validate.call_args.kwargs["n_processes"] == 2

    def test_follows_the_activity_visibility(self, tmp_path, steps):
        _task(tmp_path).execute(
            db_client=_db_client(authorized_public=True), execution_activity_id=ACTIVITY_ID
        )

        assert steps.register_memodel.call_args.kwargs["authorized_public"] is True
        assert steps.register_validation.call_args.kwargs["authorized_public"] is True

    @pytest.mark.parametrize(
        "failing_step",
        [
            "stage_memodel",
            "compile",
            "calibrate",
        ],
    )
    def test_failure_before_registration_leaves_nothing_to_mark(
        self, tmp_path, steps, failing_step
    ):
        getattr(steps, failing_step).side_effect = RuntimeError("NEURON crashed")

        with pytest.raises(RuntimeError, match="NEURON crashed"):
            _task(tmp_path).execute(db_client=_db_client(), execution_activity_id=ACTIVITY_ID)

        steps.register_memodel.assert_not_called()
        steps.set_validation_status.assert_not_called()
        steps.update_execution_activity.assert_not_called()

    @pytest.mark.parametrize(
        "failing_step",
        [
            "register_memodel",
            "update_execution_activity",
        ],
    )
    def test_failure_before_validation_fails_without_marking_error(
        self, tmp_path, steps, failing_step
    ):
        getattr(steps, failing_step).side_effect = RuntimeError("entitycore down")

        with pytest.raises(RuntimeError, match="entitycore down"):
            _task(tmp_path).execute(db_client=_db_client(), execution_activity_id=ACTIVITY_ID)

        steps.set_validation_status.assert_not_called()

    @pytest.mark.parametrize(
        "failing_step",
        [
            "validate",
            "register_validation",
        ],
    )
    def test_failure_during_validation_sets_error_and_raises(self, tmp_path, steps, failing_step):
        getattr(steps, failing_step).side_effect = RuntimeError("NEURON crashed")
        db_client = _db_client()

        with pytest.raises(RuntimeError, match="NEURON crashed"):
            _task(tmp_path).execute(db_client=db_client, execution_activity_id=ACTIVITY_ID)

        steps.register_memodel.assert_called_once()
        steps.set_validation_status.assert_called_once_with(
            db_client=db_client,
            memodel_id=MEMODEL_ID,
            validation_status=ValidationStatus.error,
        )

    def test_a_failed_done_status_sets_error(self, tmp_path, steps):
        steps.set_validation_status.side_effect = [ConnectionError("502"), None]
        db_client = _db_client()

        with pytest.raises(ConnectionError):
            _task(tmp_path).execute(db_client=db_client, execution_activity_id=ACTIVITY_ID)

        assert steps.set_validation_status.call_args.kwargs["validation_status"] == (
            ValidationStatus.error
        )

    def test_a_failed_validation_does_not_register_results(self, tmp_path, steps):
        steps.validate.side_effect = RuntimeError("NEURON crashed")

        with pytest.raises(RuntimeError, match="NEURON crashed"):
            _task(tmp_path).execute(db_client=_db_client(), execution_activity_id=ACTIVITY_ID)

        steps.register_validation.assert_not_called()

    def test_a_failed_error_status_keeps_the_original_exception(self, tmp_path, steps):
        steps.validate.side_effect = RuntimeError("NEURON crashed")
        steps.set_validation_status.side_effect = ConnectionError("502")

        with pytest.raises(RuntimeError, match="NEURON crashed"):
            _task(tmp_path).execute(db_client=_db_client(), execution_activity_id=ACTIVITY_ID)


@pytest.fixture
def entity_classes(monkeypatch):
    classes = Mock()
    monkeypatch.setattr(registration, "MEModel", classes.MEModel)
    monkeypatch.setattr(registration, "Contribution", classes.Contribution)
    monkeypatch.setattr(registration, "register_mtype_classification", classes.register_mtype)
    monkeypatch.setattr(registration, "register_etype_classification", classes.register_etype)
    monkeypatch.setattr(
        registration, "register_memodel_calibration_result", classes.register_calibration
    )
    return classes


class TestRegistration:
    def test_register_memodel(self, tmp_path, build_inputs, entity_classes):
        db_client = Mock()
        memodel = SimpleNamespace(id=MEMODEL_ID, created_by=SimpleNamespace(id="user-sub"))
        db_client.register_entity.return_value = memodel
        creator, creator_role = object(), object()
        db_client.search_entity.return_value.one.side_effect = [creator, creator_role]

        result = registration.register_memodel(
            config=_task(tmp_path).config,
            db_client=db_client,
            morphology=build_inputs.morphology,
            emodel=build_inputs.emodel,
            species=build_inputs.species,
            brain_region=build_inputs.brain_region,
            holding_current=-0.05,
            threshold_current=0.2,
            rin=120.0,
            authorized_public=True,
        )

        assert result is memodel
        entity_classes.MEModel.assert_called_once_with(
            name="L5 TPC",
            description="Built from a morphology",
            morphology=build_inputs.morphology,
            emodel=build_inputs.emodel,
            species=build_inputs.species,
            strain=build_inputs.morphology.subject.strain,
            brain_region=build_inputs.brain_region,
            holding_current=-0.05,
            threshold_current=0.2,
            validation_status=ValidationStatus.created,
            authorized_public=True,
        )
        entity_classes.register_mtype.assert_called_once_with(
            client=db_client, entity=memodel, mtype_class=build_inputs.morphology.mtypes[0]
        )
        entity_classes.register_etype.assert_called_once_with(
            client=db_client, entity=memodel, etype_class=build_inputs.emodel.etypes[0]
        )
        entity_classes.register_calibration.assert_called_once_with(
            client=db_client,
            calibrated_entity_id=MEMODEL_ID,
            holding_current=-0.05,
            threshold_current=0.2,
            rin=120.0,
            authorized_public=True,
        )
        assert db_client.search_entity.call_args_list[0].kwargs["query"] == {"sub_id": "user-sub"}
        assert db_client.search_entity.call_args_list[1].kwargs["query"] == {
            "name": registration.CREATOR_ROLE_NAME
        }
        entity_classes.Contribution.assert_called_once_with(
            agent=creator, role=creator_role, entity=memodel
        )

    def test_failed_calibration_registration_fails_register_memodel(
        self, tmp_path, build_inputs, entity_classes
    ):
        db_client = Mock()
        db_client.register_entity.return_value = SimpleNamespace(
            id=MEMODEL_ID, created_by=SimpleNamespace(id="user-sub")
        )
        entity_classes.register_calibration.side_effect = RuntimeError("entitycore down")

        with pytest.raises(RuntimeError, match="entitycore down"):
            registration.register_memodel(
                config=_task(tmp_path).config,
                db_client=db_client,
                morphology=build_inputs.morphology,
                emodel=build_inputs.emodel,
                species=build_inputs.species,
                brain_region=build_inputs.brain_region,
                holding_current=-0.05,
                threshold_current=0.2,
                rin=120.0,
                authorized_public=True,
            )

        entity_classes.Contribution.assert_not_called()

    def test_set_validation_status(self):
        db_client = Mock()

        registration.set_validation_status(
            db_client=db_client,
            memodel_id=MEMODEL_ID,
            validation_status=ValidationStatus.error,
        )

        assert db_client.update_entity.call_args == call(
            entity_id=MEMODEL_ID,
            entity_type=MEModel,
            attrs_or_entity={"validation_status": ValidationStatus.error},
        )


def test_stage_memodel_downloads_from_the_build_inputs(tmp_path, monkeypatch):
    morphology, emodel = object(), object()
    download = Mock()
    monkeypatch.setattr(task_module, "download_memodel", download)
    db_client = Mock()

    staged = task_module.stage_memodel(
        db_client=db_client,
        morphology=morphology,
        emodel=emodel,
        output_dir=tmp_path,
    )

    assert staged is download.return_value
    assert download.call_args.args == (db_client,)
    memodel = download.call_args.kwargs["memodel"]
    assert memodel.morphology is morphology
    assert memodel.emodel is emodel
    assert download.call_args.kwargs["output_dir"] == tmp_path
    assert download.call_args.kwargs["max_concurrent"] == task_module.DOWNLOAD_CONCURRENCY
