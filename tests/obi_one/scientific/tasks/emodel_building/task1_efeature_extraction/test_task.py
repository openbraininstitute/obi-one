"""Tests for EModelEFeatureExtractionTask — focus on activity update.

These tests inject fake ``bluepyemodel`` modules into ``sys.modules`` so they
run regardless of whether the optional ``emodel`` extra is installed.
"""

import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from obi_one.core.info import Info
from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
    ElectricalCellRecordingFromID,
)
from obi_one.scientific.library.recording_summary import ProtocolSummary, RecordingSummary
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.initialize import (
    ExtractionInitialize,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.protocol_and_feature_selection import (  # ruff: ignore[line-too-long]
    ProtocolAndFeatureSelection,
    SelectEFeaturesByProtocol,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.settings import (
    Settings,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
    EModelEFeatureExtractionScanConfig,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.efeatures import (  # ruff: ignore[line-too-long]
    VoltageBaseFeature,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long]
    GenericStepProtocol,
    IDRestProtocol,
    IDThreshProtocol,
    IVProtocol,
    SAHPProtocol,
    SpikeRecProtocol,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
    AMPLITUDE_TOLERANCE,
    EMODEL_NAME,
    EModelEFeatureExtractionTask,
    RecordingInput,
    _build_extraction_recipes,
    _build_files_metadata,
    _build_targets,
    _check_extraction,
    _used_protocols,
)

_TASK_MODULE = "obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task"


def _fake_bluepyemodel_modules() -> dict[str, ModuleType]:
    """Create fake bluepyemodel modules for sys.modules injection."""
    mock_get_access_point = Mock(return_value=Mock())
    mock_extract = Mock()

    ap_mod = ModuleType("bluepyemodel.access_point")
    ap_mod.get_access_point = mock_get_access_point

    extract_mod = ModuleType("bluepyemodel.efeatures_extraction.efeatures_extraction")
    extract_mod.extract_save_features_protocols = mock_extract

    return {
        "bluepyemodel.access_point": ap_mod,
        "bluepyemodel.efeatures_extraction.efeatures_extraction": extract_mod,
    }


@pytest.fixture
def mock_db_client():
    return Mock()


def _make_task(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    config = Mock()
    config.coordinate_output_root = out_dir
    return EModelEFeatureExtractionTask.model_construct(config=config)


@contextmanager
def _noop_chdir(_path):
    yield


class TestEModelEFeatureExtractionTask:
    def test_download_recordings_resolves_ljp_from_entity(self, tmp_path, mock_db_client):
        task = _make_task(tmp_path)
        recording_id = "00000000-0000-0000-0000-000000000013"
        recording = ElectricalCellRecordingFromID(id_str=recording_id)
        task.config.initialize.electrical_cell_recording = (recording,)
        entity = Mock(ljp=0.05)
        dest = tmp_path / recording_id / "recording.nwb"
        dest.parent.mkdir(parents=True)
        dest.touch()
        stored = RecordingSummary(protocols={"IDrest": ProtocolSummary(amp=[0.1])})

        with (
            patch.object(
                ElectricalCellRecordingFromID,
                "download_nwb_asset",
                return_value=dest,
            ),
            patch.object(ElectricalCellRecordingFromID, "entity", return_value=entity),
            patch(f"{_TASK_MODULE}.fetch_recording_summary", return_value=stored),
            patch(f"{_TASK_MODULE}.compute_recording_summary") as compute,
        ):
            downloaded = task._download_recordings(tmp_path / "ephys", mock_db_client)

        assert downloaded == [
            RecordingInput(path=dest, ljp=0.05, summary=stored, recording_id=recording_id)
        ]
        compute.assert_not_called()

    def test_download_recordings_computes_a_missing_summary(self, tmp_path, mock_db_client):
        task = _make_task(tmp_path)
        recording = ElectricalCellRecordingFromID(id_str="00000000-0000-0000-0000-000000000013")
        task.config.initialize.electrical_cell_recording = (recording,)
        dest = tmp_path / "recording.nwb"
        computed = RecordingSummary()

        with (
            patch.object(ElectricalCellRecordingFromID, "download_nwb_asset", return_value=dest),
            patch.object(ElectricalCellRecordingFromID, "entity", return_value=Mock(ljp=0.0)),
            patch(f"{_TASK_MODULE}.fetch_recording_summary", return_value=None),
            patch(f"{_TASK_MODULE}.compute_recording_summary", return_value=computed) as compute,
        ):
            downloaded = task._download_recordings(tmp_path / "ephys", mock_db_client)

        compute.assert_called_once_with(dest)
        assert downloaded[0].summary is computed

    def test_execute_updates_activity_with_generated_entity(self, tmp_path, mock_db_client):
        """execute() must call _update_execution_activity with the TaskResult ID."""
        task = _make_task(tmp_path)
        task_result_id = uuid4()

        mock_activity = Mock()
        mock_activity.id = uuid4()

        fake_modules = _fake_bluepyemodel_modules()

        with (
            patch.dict(sys.modules, fake_modules),
            patch.object(task, "_download_recordings", return_value=[]),
            patch.object(task, "_build_targets_configuration", return_value=(Mock(), [], [])),
            patch(f"{_TASK_MODULE}._check_extraction"),
            patch(f"{_TASK_MODULE}.write_json"),
            patch(f"{_TASK_MODULE}.chdir", _noop_chdir),
            patch.object(
                task,
                "_get_execution_activity",
                return_value=mock_activity,
            ) as mock_get_activity,
            patch.object(
                task, "_register_task_result", return_value=str(task_result_id)
            ) as mock_register,
            patch.object(task, "_update_execution_activity") as mock_update_activity,
        ):
            task.execute(
                db_client=mock_db_client,
                execution_activity_id=str(mock_activity.id),
            )

        mock_get_activity.assert_called_once_with(
            db_client=mock_db_client,
            execution_activity_id=str(mock_activity.id),
        )
        mock_register.assert_called_once()
        mock_update_activity.assert_called_once_with(
            db_client=mock_db_client,
            execution_activity=mock_activity,
            generated=[str(task_result_id)],
        )

    def test_execute_does_not_update_activity_when_registration_fails(
        self, tmp_path, mock_db_client
    ):
        """If _register_task_result raises, _update_execution_activity must not be called."""
        task = _make_task(tmp_path)
        mock_activity = Mock()
        mock_activity.id = uuid4()

        fake_modules = _fake_bluepyemodel_modules()

        with (
            patch.dict(sys.modules, fake_modules),
            patch.object(task, "_download_recordings", return_value=[]),
            patch.object(task, "_build_targets_configuration", return_value=(Mock(), [], [])),
            patch(f"{_TASK_MODULE}._check_extraction"),
            patch(f"{_TASK_MODULE}.write_json"),
            patch(f"{_TASK_MODULE}.chdir", _noop_chdir),
            patch.object(task, "_get_execution_activity", return_value=mock_activity),
            patch.object(
                task,
                "_register_task_result",
                side_effect=httpx.HTTPError("network error"),
            ),
            patch.object(task, "_update_execution_activity") as mock_update_activity,
        ):
            task.execute(
                db_client=mock_db_client,
                execution_activity_id=str(mock_activity.id),
            )

        mock_update_activity.assert_not_called()

    def test_execute_skips_activity_update_when_no_db_client(self, tmp_path):
        """Without a db_client, no activity update should happen."""
        task = _make_task(tmp_path)

        fake_modules = _fake_bluepyemodel_modules()

        with (
            patch.dict(sys.modules, fake_modules),
            patch.object(task, "_download_recordings", return_value=[]),
            patch.object(task, "_build_targets_configuration", return_value=(Mock(), [], [])),
            patch(f"{_TASK_MODULE}._check_extraction"),
            patch(f"{_TASK_MODULE}.write_json"),
            patch(f"{_TASK_MODULE}.chdir", _noop_chdir),
            patch.object(task, "_update_execution_activity") as mock_update_activity,
        ):
            task.execute(db_client=None)

        mock_update_activity.assert_not_called()


def _recording(
    name: str,
    protocols: dict[str, ProtocolSummary],
    *,
    rheobase: dict[str, float | None] | None = None,
    ljp: float = 14.0,
) -> RecordingInput:
    return RecordingInput(
        path=Path(f"/data/{name}.nwb"),
        ljp=ljp,
        summary=RecordingSummary(protocols=protocols, rheobase=rheobase or {}),
        recording_id=name,
    )


class TestBuildFilesMetadata:
    def test_canonical_name_needs_no_reader_hint(self):
        recording = _recording("cell", {"IDrest": ProtocolSummary(amp=[0.1])})
        files = _build_files_metadata([recording], {"IDRestProtocol": ("IDrest", {})})
        assert files == [
            {
                "cell_name": "cell",
                "filepath": "/data/cell.nwb",
                "ecodes": {"IDrest": {"ljp": 14.0}},
            }
        ]

    def test_file_names_become_reader_hints(self):
        """bluepyefe's BBP reader finds no ``IDthresh`` sweeps in an ``IDThreshold`` group."""
        recording = _recording(
            "cell",
            {"IDThreshold": ProtocolSummary(amp=[0.1]), "GenericStep": ProtocolSummary(amp=[0.1])},
        )
        files = _build_files_metadata(
            [recording],
            {"IDThreshProtocol": ("IDthresh", {}), "GenericStepProtocol": ("Step", {})},
        )
        ecodes = files[0]["ecodes"]
        assert ecodes["IDthresh"] == {"ljp": 14.0, "protocol_name": "IDThreshold"}
        assert ecodes["Step"] == {"ljp": 14.0, "protocol_name": "GenericStep"}

    def test_each_file_gets_its_own_timing(self):
        recordings = [
            _recording("a", {"IV": ProtocolSummary(amp=[-0.1], ton=[20.25], toff=[1020.25])}),
            _recording("b", {"IV": ProtocolSummary(amp=[-0.1], ton=[100.0], toff=[600.0])}),
        ]
        files = _build_files_metadata(recordings, {"IVProtocol": ("IV", {})})
        assert [f["ecodes"]["IV"] for f in files] == [
            {"ton": 20.25, "toff": 1020.25, "ljp": 14.0},
            {"ton": 100.0, "toff": 600.0, "ljp": 14.0},
        ]

    def test_timing_set_in_the_config_wins(self):
        recording = _recording(
            "a", {"IV": ProtocolSummary(amp=[-0.1], ton=[20.25], toff=[1020.25])}
        )
        files = _build_files_metadata([recording], {"IVProtocol": ("IV", {"ton": 25.0})})
        assert files[0]["ecodes"]["IV"] == {"ton": 25.0, "toff": 1020.25, "ljp": 14.0}

    def test_mixed_timing_is_left_to_bluepyefe(self, caplog):
        recording = _recording(
            "a", {"IDRest": ProtocolSummary(amp=[0.1], ton=[520.25, 700.25], toff=[720.25])}
        )
        with caplog.at_level(logging.WARNING):
            files = _build_files_metadata([recording], {"IDRestProtocol": ("IDrest", {})})
        assert files[0]["ecodes"]["IDrest"] == {"ljp": 14.0, "protocol_name": "IDRest"}
        assert "different timings" in caplog.text

    def test_protocols_missing_from_a_file_are_left_out(self):
        recording = _recording("a", {"IDrest": ProtocolSummary(amp=[0.1])})
        files = _build_files_metadata(
            [recording], {"IDRestProtocol": ("IDrest", {}), "IVProtocol": ("IV", {})}
        )
        assert set(files[0]["ecodes"]) == {"IDrest"}


def test_relative_mode_also_reads_the_rheobase_protocols():
    selection = SelectEFeaturesByProtocol(protocols=(IVProtocol(), IDRestProtocol()))
    absolute = _used_protocols(selection, Settings(rheobase_protocols=("IDThreshProtocol",)))
    relative = _used_protocols(
        selection, Settings(amplitude_mode="relative", rheobase_protocols=("IDThreshProtocol",))
    )
    assert set(absolute) == {"IVProtocol", "IDRestProtocol"}
    assert relative["IDThreshProtocol"] == ("IDthresh", {})


def _fake_targets_configuration_module() -> tuple[dict[str, ModuleType], Mock]:
    """Fake ``bluepyemodel`` targets-configuration module with a mock class."""
    targets_configuration = Mock()
    module = ModuleType("bluepyemodel.efeatures_extraction.targets_configuration")
    module.TargetsConfiguration = targets_configuration
    return {module.__name__: module}, targets_configuration


def _relative_selection() -> SelectEFeaturesByProtocol:
    """IDthresh gives the rheobase, IV the RMP and R_in, IDrest is targeted in %."""
    return SelectEFeaturesByProtocol(
        protocols=(
            IDThreshProtocol(),
            IVProtocol(),
            IDRestProtocol(extraction_amplitudes=((150.0, False), (250.0, True))),
        )
    )


def _relative_settings(**overrides) -> Settings:
    """IV gives the RMP at 0% and R_in at -40%."""
    return Settings(amplitude_mode="relative", rin_amplitude=-40.0, **overrides)


def _relative_recordings() -> list[RecordingInput]:
    protocols = {
        "IDThreshold": ProtocolSummary(amp=[0.1, 0.2]),
        "IV": ProtocolSummary(amp=[-0.08, 0.0]),
        "IDRest": ProtocolSummary(amp=[0.3]),
    }
    return [
        _recording("a", protocols, rheobase={"IDThreshold": 0.2, "IV": None}),
        _recording("b", protocols, rheobase={"IDThreshold": None, "IV": None}),
    ]


class TestBuildTargetsConfiguration:
    def test_empty_amplitudes_raise_clear_error(self, tmp_path):
        """Empty extraction_amplitudes must fail early, not inside bluepyemodel."""
        task = _make_task(tmp_path)
        task.config.efeatures_by_protocol.selection = SelectEFeaturesByProtocol(
            protocols=(IDRestProtocol(),)
        )
        task.config.settings = Settings()

        modules, _ = _fake_targets_configuration_module()
        with (
            patch.dict(sys.modules, modules),
            pytest.raises(ValueError, match="extraction_amplitudes"),
        ):
            task._build_targets_configuration(_relative_recordings())

    def test_absolute_mode_has_no_rheobase_protocol(self, tmp_path):
        task = _make_task(tmp_path)
        task.config.efeatures_by_protocol.selection = SelectEFeaturesByProtocol(
            protocols=(IDRestProtocol(extraction_amplitudes=((0.3, False),)),)
        )
        task.config.settings = Settings()

        modules, targets_configuration = _fake_targets_configuration_module()
        with patch.dict(sys.modules, modules):
            task._build_targets_configuration(_relative_recordings())

        assert targets_configuration.call_args.kwargs["protocols_rheobase"] == []

    def test_relative_mode_names_the_rheobase_protocols(self, tmp_path):
        task = _make_task(tmp_path)
        task.config.efeatures_by_protocol.selection = _relative_selection()
        task.config.settings = _relative_settings()

        modules, targets_configuration = _fake_targets_configuration_module()
        with patch.dict(sys.modules, modules):
            task._build_targets_configuration(_relative_recordings()[:1])

        kwargs = targets_configuration.call_args.kwargs
        assert kwargs["protocols_rheobase"] == ["IDthresh"]
        assert kwargs["files"][0]["ecodes"]["IDthresh"]["protocol_name"] == "IDThreshold"

    def test_recording_without_rheobase_is_named(self, tmp_path):
        """A recording bluepyefe would silently drop fails the task instead."""
        task = _make_task(tmp_path)
        task.config.efeatures_by_protocol.selection = _relative_selection()
        task.config.settings = _relative_settings()

        modules, _ = _fake_targets_configuration_module()
        with (
            patch.dict(sys.modules, modules),
            pytest.raises(
                ValueError, match=r"IDThreshProtocol for b\.nwb: \{'IDThreshold': None\}"
            ),
        ):
            task._build_targets_configuration(_relative_recordings())

    def test_another_rheobase_protocol_can_rescue_a_recording(self, tmp_path):
        task = _make_task(tmp_path)
        task.config.efeatures_by_protocol.selection = _relative_selection()
        task.config.settings = _relative_settings(
            rheobase_protocols=("IDThreshProtocol", "IDRestProtocol")
        )
        recordings = _relative_recordings()
        recordings[1].summary.rheobase["IDRest"] = 0.3

        modules, targets_configuration = _fake_targets_configuration_module()
        with patch.dict(sys.modules, modules):
            task._build_targets_configuration(recordings)

        assert targets_configuration.call_args.kwargs["protocols_rheobase"] == [
            "IDthresh",
            "IDrest",
        ]


class TestBuildTargets:
    def test_absolute_amplitudes_match_in_na(self):
        selection = SelectEFeaturesByProtocol(
            protocols=(IDRestProtocol(extraction_amplitudes=((0.1, False), (0.3, True))),)
        )

        rows, names = _build_targets(selection, Settings())

        assert {row["amplitude"] for row in rows} == {0.1, 0.3}
        assert {row["tolerance"] for row in rows} == {AMPLITUDE_TOLERANCE}
        assert names == ["IDrest_0.3"]

    def test_relative_amplitudes_match_in_percent(self):
        rows, names = _build_targets(
            _relative_selection(), _relative_settings(relative_amplitude_tolerance=15.0)
        )

        assert {row["amplitude"] for row in rows if row["protocol"] == "IDrest"} == {150.0, 250.0}
        assert {row["tolerance"] for row in rows} == {15.0}
        assert names == ["IDrest_250.0"]

    def test_relative_mode_adds_rmp_and_rin_targets(self):
        """voltage_base at the RMP amplitude; voltage_base + R_in at the R_in amplitude."""
        rows, _ = _build_targets(_relative_selection(), _relative_settings())

        iv_targets = {
            (row["efeature"], row["amplitude"]) for row in rows if row["protocol"] == "IV"
        }
        assert iv_targets == {
            ("voltage_base", 0.0),
            ("voltage_base", -40.0),
            ("ohmic_input_resistance_vb_ssse", -40.0),
        }

    def test_role_targets_reuse_selected_feature_and_are_not_repeated(self):
        """A role feature already targeted keeps its overrides and is listed once."""
        selection = SelectEFeaturesByProtocol(
            protocols=(
                IVProtocol(
                    extraction_amplitudes=((0.0, False),),
                    features=(VoltageBaseFeature(spike_detection_threshold=-30.0),),
                ),
            )
        )

        rows, _ = _build_targets(selection, _relative_settings(spike_detection_threshold=None))

        rmp_rows = [
            row
            for row in rows
            if (row["protocol"], row["efeature"], row["amplitude"]) == ("IV", "voltage_base", 0.0)
        ]
        assert len(rmp_rows) == 1
        assert rmp_rows[0]["efel_settings"]["Threshold"] == pytest.approx(-30.0)


class TestBuildExtractionRecipes:
    def test_absolute_mode(self):
        recipes = _build_extraction_recipes(Settings(), validation_protocol_names=[])

        settings = recipes[EMODEL_NAME]["pipeline_settings"]
        assert settings["extract_absolute_amplitudes"] is True
        assert "name_rmp_protocol" not in settings
        assert "name_Rin_protocol" not in settings

    def test_relative_mode_enables_threshold_based_protocols(self):
        recipes = _build_extraction_recipes(
            _relative_settings(rheobase_strategy="majority"),
            validation_protocol_names=["IDrest_250.0"],
        )

        settings = recipes[EMODEL_NAME]["pipeline_settings"]
        assert settings["extract_absolute_amplitudes"] is False
        assert settings["name_rmp_protocol"] == "IV_0.0"
        assert settings["name_Rin_protocol"] == "IV_-40.0"
        assert settings["rheobase_strategy_extraction"] == "majority"
        assert settings["validation_protocols"] == ["IDrest_250.0"]


def _config(selection: SelectEFeaturesByProtocol, settings: Settings):
    return EModelEFeatureExtractionScanConfig(
        info=Info(campaign_name="test", campaign_description="test"),
        initialize=ExtractionInitialize(
            electrical_cell_recording=(
                ElectricalCellRecordingFromID(id_str="00000000-0000-0000-0000-000000000013"),
            )
        ),
        efeatures_by_protocol=ProtocolAndFeatureSelection(selection=selection),
        settings=settings,
    )


class TestRelativeModeValidation:
    def test_relative_config_accepted(self):
        _config(_relative_selection(), _relative_settings())

    def test_old_absolute_configs_still_load(self):
        """Configs written before the amplitude mode existed are absolute."""
        config = _config(
            SelectEFeaturesByProtocol(
                protocols=(IDRestProtocol(extraction_amplitudes=((0.3, False),)),)
            ),
            Settings.model_validate({}),
        )
        assert config.settings.amplitude_mode == "absolute"

    def test_relative_settings_are_ignored_in_absolute_mode(self):
        _config(
            SelectEFeaturesByProtocol(protocols=(IDRestProtocol(),)),
            Settings(rmp_protocol="SAHPProtocol", rheobase_protocols=("NotAProtocol",)),
        )

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"rheobase_protocols": ("NotAProtocol",)}, "unknown protocol type"),
            ({"rheobase_protocols": ("SAHPProtocol",)}, "must be a step protocol"),
            ({"rheobase_protocols": ("SpontaneousProtocol",)}, "with a current step"),
            ({"rmp_protocol": "SAHPProtocol"}, "must be a step protocol"),
            ({"rin_protocol": "APWaveformProtocol"}, "not one of the selected protocols"),
            ({"rin_amplitude": 0.0}, "distinct"),
        ],
    )
    def test_invalid_relative_settings(self, overrides, message):
        settings = _relative_settings().model_copy(update=overrides)
        with pytest.raises(ValidationError, match=message):
            _config(_relative_selection(), settings)

    def test_rheobase_protocols_need_not_be_selected(self):
        _config(_relative_selection(), _relative_settings(rheobase_protocols=("IDRestProtocol",)))

    def test_relative_amplitudes_on_non_amplitude_targeted_protocol_rejected(self):
        """SpikeRec matches a ms delta, not an amplitude — reject it early."""
        selection = SelectEFeaturesByProtocol(
            protocols=(
                *_relative_selection().protocols,
                SpikeRecProtocol(extraction_amplitudes=((150.0, False),)),
            )
        )
        with pytest.raises(ValidationError, match="not amplitude-targeted"):
            _config(selection, _relative_settings())

    def test_the_settings_field_rejects_an_empty_rheobase_list(self):
        with pytest.raises(ValidationError):
            Settings(rheobase_protocols=())


def _rec(protocol: str, amp: float, amp_rel: float | None = None):
    def in_target(target, tolerance, absolute_amplitude):
        value = amp if absolute_amplitude else amp_rel
        return value is not None and abs(target - value) < tolerance

    return SimpleNamespace(protocol_name=protocol, in_target=in_target)


def _cell(name: str, recordings: list, rheobase: float | None = None):
    return SimpleNamespace(
        name=name,
        rheobase=rheobase,
        get_recordings_by_protocol_name=lambda p: [r for r in recordings if r.protocol_name == p],
    )


def _targets(*amplitudes: tuple[str, float], tolerance: float = 0.01) -> list[dict]:
    return [
        {"protocol": protocol, "amplitude": amplitude, "tolerance": tolerance, "efeature": "x"}
        for protocol, amplitude in amplitudes
    ]


class TestCheckExtraction:
    def test_every_recording_used(self, caplog):
        recordings = [_recording("a", {}), _recording("b", {})]
        cells = [_cell("a", [_rec("IDrest", 0.3)]), _cell("b", [_rec("IDrest", 0.305)])]
        with caplog.at_level(logging.WARNING):
            _check_extraction(cells, recordings, _targets(("IDrest", 0.3)), relative=False)
        assert not caplog.text

    def test_unmatched_amplitudes_are_warned_about(self, caplog):
        recordings = [_recording("a", {})]
        cells = [_cell("a", [_rec("IDrest", 0.3)])]
        with caplog.at_level(logging.WARNING):
            _check_extraction(
                cells, recordings, _targets(("IDrest", 0.3), ("IDrest", 0.5)), relative=False
            )
        assert "IDrest target at 0.5 nA" in caplog.text

    def test_recording_without_rheobase_fails(self):
        recordings = [_recording("a", {}), _recording("b", {})]
        cells = [
            _cell("a", [_rec("IDrest", 0.3, amp_rel=150.0)], rheobase=0.2),
            _cell("b", [_rec("IDrest", 0.3)], rheobase=None),
        ]
        with pytest.raises(ValueError, match=r"b\.nwb \(no rheobase\)"):
            _check_extraction(
                cells, recordings, _targets(("IDrest", 150.0), tolerance=10.0), relative=True
            )

    def test_recording_matching_nothing_fails(self):
        recordings = [_recording("a", {}), _recording("b", {})]
        cells = [_cell("a", [_rec("IDrest", 0.3)]), _cell("b", [_rec("IDrest", 0.9)])]
        with pytest.raises(ValueError, match="no sweep at the selected amplitudes"):
            _check_extraction(cells, recordings, _targets(("IDrest", 0.3)), relative=False)

    def test_recording_bluepyefe_never_read_fails(self):
        recordings = [_recording("a", {}), _recording("b", {})]
        cells = [_cell("a", [_rec("IDrest", 0.3)])]
        with pytest.raises(ValueError, match="none of the selected protocols"):
            _check_extraction(cells, recordings, _targets(("IDrest", 0.3)), relative=False)


def test_generic_step_and_sahp_are_known_types():
    """Guard the type names used in the defaults and tests above."""
    assert GenericStepProtocol.__name__ == "GenericStepProtocol"
    assert SAHPProtocol.ecode_class == "SAHP"


class TestErrorBranches:
    def test_unknown_protocol_type(self):
        with pytest.raises(ValueError, match="Unknown protocol type 'NotAProtocol'"):
            _build_extraction_recipes(
                _relative_settings().model_copy(update={"rmp_protocol": "NotAProtocol"}),
                validation_protocol_names=[],
            )

    def test_role_protocol_must_be_selected(self):
        with pytest.raises(ValueError, match="APWaveformProtocol is not one of the selected"):
            _build_targets(
                _relative_selection(),
                _relative_settings().model_copy(update={"rin_protocol": "APWaveformProtocol"}),
            )

    def test_no_recordings(self, tmp_path):
        task = _make_task(tmp_path)
        task.config.efeatures_by_protocol.selection = _relative_selection()
        task.config.settings = _relative_settings()
        modules, _ = _fake_targets_configuration_module()
        with patch.dict(sys.modules, modules), pytest.raises(FileNotFoundError):
            task._build_targets_configuration([])

    def test_download_rejects_other_recording_types(self, tmp_path, mock_db_client):
        task = _make_task(tmp_path)
        task.config.initialize.electrical_cell_recording = (Mock(),)
        with pytest.raises(TypeError, match="Expected ElectricalCellRecordingFromID"):
            task._download_recordings(tmp_path / "ephys", mock_db_client)
