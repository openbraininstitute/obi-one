"""Unit tests for the pure-logic helpers in the MEModel validation workflow.

These cover the parts of ``workflow.py`` that do not require a compiled NEURON
model or a live entitysdk client: calibration resolution, morphology selection,
and the mechanism compile/load error handling. The ``setup()`` body itself
(download, Cell construction, rheobase/Rin) is exercised end-to-end instead.
"""

import subprocess  # ruff: ignore[suspicious-subprocess-import]
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from entitysdk.schemas.memodel import DownloadedMEModel
from entitysdk.types import EntityLifecycleStatus

from obi_one.scientific.validations.base import InvalidValidationContextError
from obi_one.scientific.validations.memodel import workflow as workflow_module
from obi_one.scientific.validations.memodel.config import SimulatorConfig
from obi_one.scientific.validations.memodel.profiles import (
    DefaultMEModelValidationProfile,
    ThalamicMEModelValidationProfile,
)
from obi_one.scientific.validations.memodel.workflow import (
    MEModelValidationWorkflow,
    _compile_mechanisms,
    _load_compiled_mechanisms,
    _resolve_holding_current,
    _select_morphology_path,
)


class TestResolveHoldingCurrent:
    def test_missing_defaults_to_zero_when_not_required(self):
        calibration = SimpleNamespace(holding_current=None)
        result = _resolve_holding_current(calibration, DefaultMEModelValidationProfile())
        assert result == pytest.approx(0.0)

    def test_missing_raises_when_profile_requires_it(self):
        calibration = SimpleNamespace(holding_current=None)
        with pytest.raises(InvalidValidationContextError, match="holding_current"):
            _resolve_holding_current(calibration, ThalamicMEModelValidationProfile())

    def test_returns_float_value(self):
        calibration = SimpleNamespace(holding_current=-0.03)
        result = _resolve_holding_current(calibration, DefaultMEModelValidationProfile())
        assert result == pytest.approx(-0.03)

    def test_non_numeric_raises(self):
        calibration = SimpleNamespace(holding_current="not-a-number")
        with pytest.raises(InvalidValidationContextError, match="finite number"):
            _resolve_holding_current(calibration, DefaultMEModelValidationProfile())

    def test_non_finite_raises(self):
        calibration = SimpleNamespace(holding_current=float("nan"))
        with pytest.raises(InvalidValidationContextError, match="finite number"):
            _resolve_holding_current(calibration, DefaultMEModelValidationProfile())


class TestSelectMorphologyPath:
    def _downloaded(self, morphology_paths):
        return DownloadedMEModel(
            hoc_path=Path("model.hoc"),
            mechanisms_dir=Path("mechanisms"),
            mechanism_files=[],
            morphology_paths=morphology_paths,
        )

    def test_prefers_asc(self):
        downloaded = self._downloaded([Path("m.swc"), Path("m.asc"), Path("m.h5")])
        assert _select_morphology_path(downloaded, "e1") == Path("m.asc")

    def test_falls_back_to_swc(self):
        downloaded = self._downloaded([Path("m.h5"), Path("m.swc")])
        assert _select_morphology_path(downloaded, "e1") == Path("m.swc")

    def test_raises_when_none_downloaded(self):
        downloaded = self._downloaded([])
        with pytest.raises(InvalidValidationContextError, match="No morphology"):
            _select_morphology_path(downloaded, "e1")

    def test_raises_when_no_loadable_format(self):
        downloaded = self._downloaded([Path("m.h5")])
        with pytest.raises(InvalidValidationContextError, match=r"No \.asc or \.swc"):
            _select_morphology_path(downloaded, "e1")


class TestCompileMechanisms:
    def test_missing_nrnivmodl_raises(self, tmp_path):
        with (
            patch(
                "obi_one.scientific.validations.memodel.workflow.subprocess.run",
                side_effect=FileNotFoundError,
            ),
            pytest.raises(InvalidValidationContextError, match="nrnivmodl"),
        ):
            _compile_mechanisms(tmp_path, tmp_path)

    def test_compile_failure_raises_with_output(self, tmp_path):
        error = subprocess.CalledProcessError(
            returncode=1, cmd="nrnivmodl", output="out", stderr="err"
        )
        with (
            patch(
                "obi_one.scientific.validations.memodel.workflow.subprocess.run",
                side_effect=error,
            ),
            pytest.raises(InvalidValidationContextError, match="exit code 1"),
        ):
            _compile_mechanisms(tmp_path, tmp_path)


class TestLoadCompiledMechanisms:
    def test_raises_when_no_library_produced(self, tmp_path):
        # Empty output dir: nrnivmodl "succeeded" but produced nothing.
        with pytest.raises(InvalidValidationContextError, match="no libnrnmech"):
            _load_compiled_mechanisms(tmp_path)

    def test_raises_when_library_cannot_load(self, tmp_path):
        lib_dir = tmp_path / "arm64"
        lib_dir.mkdir()
        (lib_dir / "libnrnmech.dylib").write_text("stub")
        fake_neuron = MagicMock()
        fake_neuron.h.nrn_load_dll.side_effect = RuntimeError("bad library")
        with (
            patch("obi_one.scientific.validations.memodel.workflow.neuron", fake_neuron),
            pytest.raises(InvalidValidationContextError, match="Could not load"),
        ):
            _load_compiled_mechanisms(tmp_path)

    def test_returns_loaded_library(self, tmp_path):
        lib_dir = tmp_path / "arm64"
        lib_dir.mkdir()
        lib = lib_dir / "libnrnmech.dylib"
        lib.write_text("stub")
        fake_neuron = MagicMock()
        with patch("obi_one.scientific.validations.memodel.workflow.neuron", fake_neuron):
            result = _load_compiled_mechanisms(tmp_path)
        assert result == lib
        fake_neuron.h.nrn_load_dll.assert_called_once_with(str(lib))


class TestWorkflowSetup:
    """Drive MEModelValidationWorkflow.setup() with the NEURON/entitysdk calls patched.

    This covers setup()'s own orchestration (config fallback, holding/rheobase/Rin
    resolution, context assembly). The patched calls (Cell construction, rheobase and
    input-resistance on a live cell) are the compiled-NEURON boundary and are exercised
    end-to-end rather than here.
    """

    def _downloaded(self, tmp_path):
        return DownloadedMEModel(
            hoc_path=tmp_path / "model.hoc",
            mechanisms_dir=tmp_path / "mechanisms",
            mechanism_files=[],
            morphology_paths=[tmp_path / "m.asc"],
        )

    def _patches(self, tmp_path, *, sim_config, rin_value=None):
        w = workflow_module

        cell = MagicMock()
        cell.template_params = SimpleNamespace(
            template_filepath="t.hoc",
            morph_filepath="m.asc",
            template_format="v6",
            emodel_properties=SimpleNamespace(),
        )
        return [
            patch.object(w, "download_memodel", return_value=self._downloaded(tmp_path)),
            patch.object(w, "extract_simulator_config_from_hoc", return_value=sim_config),
            patch.object(w, "_compile_mechanisms"),
            patch.object(w, "_load_compiled_mechanisms", return_value=tmp_path / "lib"),
            patch.object(w, "_resolve_rheobase", return_value=0.1),
            patch.object(w, "_verify_simulator_configuration"),
            patch("bluecellulab.cell.core.Cell", return_value=cell),
            patch("bluecellulab.circuit.circuit_access.EmodelProperties"),
            patch("bluecellulab.simulation.neuron_globals.set_neuron_globals"),
            patch("bluecellulab.tools.calculate_input_resistance", return_value=rin_value or 150.0),
        ]

    def _client(self, calibration=None):
        memodel = SimpleNamespace(name="test-model", calibration_result=calibration)
        client = MagicMock()
        client.get_entity.return_value = memodel
        return client

    def test_default_profile_setup_without_rin(self, tmp_path):

        sim_config = SimulatorConfig(celsius=34.0, v_init=-70.0)
        workflow = MEModelValidationWorkflow(output_dir=tmp_path, validation_profile="default")
        calibration = SimpleNamespace(holding_current=-0.03, threshold_current=0.1, rin=None)
        client = self._client(calibration)

        with ExitStack() as stack:
            for p in self._patches(tmp_path, sim_config=sim_config):
                stack.enter_context(p)
            context = workflow.setup("12a65005-a035-4a36-afe0-605de815861d", client)

        assert context.rheobase == pytest.approx(0.1)
        # Default profile does not require Rin.
        assert context.rin is None
        assert context.simulator_config == sim_config
        client.get_entity.assert_called_once()

    def test_thalamic_profile_setup_computes_rin(self, tmp_path):

        sim_config = SimulatorConfig(celsius=34.0, v_init=-70.0)
        workflow = MEModelValidationWorkflow(output_dir=tmp_path, validation_profile="thalamic")
        # No calibrated rin -> setup falls back to calculate_input_resistance.
        calibration = SimpleNamespace(holding_current=-0.03, threshold_current=0.1, rin=None)
        client = self._client(calibration)

        with ExitStack() as stack:
            for p in self._patches(tmp_path, sim_config=sim_config, rin_value=150.0):
                stack.enter_context(p)
            context = workflow.setup("12a65005-a035-4a36-afe0-605de815861d", client)

        assert context.rin == pytest.approx(150.0)

    def test_hoc_without_config_uses_profile_fallback(self, tmp_path):

        workflow = MEModelValidationWorkflow(output_dir=tmp_path, validation_profile="thalamic")
        calibration = SimpleNamespace(holding_current=-0.03, threshold_current=0.1, rin=None)
        client = self._client(calibration)

        # extract_simulator_config_from_hoc returns None -> profile fallback is used.
        with ExitStack() as stack:
            for p in self._patches(tmp_path, sim_config=None, rin_value=150.0):
                stack.enter_context(p)
            context = workflow.setup("12a65005-a035-4a36-afe0-605de815861d", client)

        assert context.simulator_config == workflow.validation_profile.simulator_config_fallback

    def _run_with_build_failure(self, tmp_path, client):
        """Run setup() where mechanism compilation fails, i.e. the artifact can't load."""
        workflow = MEModelValidationWorkflow(output_dir=tmp_path, validation_profile="default")
        with ExitStack() as stack:
            for p in self._patches(
                tmp_path, sim_config=SimulatorConfig(celsius=34.0, v_init=-70.0)
            ):
                stack.enter_context(p)
            stack.enter_context(
                patch.object(
                    workflow_module,
                    "_compile_mechanisms",
                    side_effect=InvalidValidationContextError("nrnivmodl failed"),
                )
            )
            stack.enter_context(pytest.raises(InvalidValidationContextError, match="nrnivmodl"))
            workflow.setup("12a65005-a035-4a36-afe0-605de815861d", client)

    def test_build_failure_disqualifies_the_memodel_and_reraises(self, tmp_path):
        client = self._client(SimpleNamespace(holding_current=0.0, threshold_current=0.1, rin=None))

        self._run_with_build_failure(tmp_path, client)

        client.update_entity.assert_called_once()
        kwargs = client.update_entity.call_args.kwargs
        assert kwargs["attrs_or_entity"] == {"lifecycle_status": EntityLifecycleStatus.disqualified}

    def test_failed_lifecycle_update_does_not_mask_the_load_error(self, tmp_path):
        # e.g. the client may not edit this entity: the original load error must
        # still surface, not the lifecycle-update error.
        client = self._client(SimpleNamespace(holding_current=0.0, threshold_current=0.1, rin=None))
        client.update_entity.side_effect = PermissionError("forbidden")

        self._run_with_build_failure(tmp_path, client)

        client.update_entity.assert_called_once()

    def test_download_failure_does_not_disqualify(self, tmp_path):
        # A failed download may be transient (network, server), so the model must
        # not be marked as unusable.
        workflow = MEModelValidationWorkflow(output_dir=tmp_path, validation_profile="default")
        client = self._client(SimpleNamespace(holding_current=0.0, threshold_current=0.1, rin=None))
        download_fails = patch.object(
            workflow_module, "download_memodel", side_effect=RuntimeError("timeout")
        )
        with download_fails, pytest.raises(RuntimeError, match="timeout"):
            workflow.setup("12a65005-a035-4a36-afe0-605de815861d", client)

        client.update_entity.assert_not_called()

    def test_rin_failure_after_load_does_not_disqualify(self, tmp_path):
        # The cell loads fine; only the Rin requirement fails. That is a config
        # error, not an unloadable artifact, so the entity must NOT be disqualified.
        entity_id = "12a65005-a035-4a36-afe0-605de815861d"
        workflow = MEModelValidationWorkflow(output_dir=tmp_path, validation_profile="thalamic")
        client = self._client(
            SimpleNamespace(holding_current=-0.03, threshold_current=0.1, rin=None)
        )

        with ExitStack() as stack:
            for p in self._patches(
                tmp_path, sim_config=SimulatorConfig(celsius=34.0, v_init=-70.0)
            ):
                stack.enter_context(p)
            # Force a non-physiological Rin so the thalamic profile's Rin guard trips.
            stack.enter_context(
                patch("bluecellulab.tools.calculate_input_resistance", return_value=0.0)
            )
            with pytest.raises(InvalidValidationContextError, match="Rin"):
                workflow.setup(entity_id, client)

        client.update_entity.assert_not_called()
