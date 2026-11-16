"""Unit tests for electrophysiology metrics config and task."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from obi_one.core.exception import OBIONEError
from obi_one.scientific.library.ephys_extraction import (
    AmplitudeInput,
    ElectrophysiologyMetricsOutput,
)
from obi_one.scientific.tasks.ephys_extraction.config import (
    ElectrophysiologyMetricsScanConfig,
    ElectrophysiologyMetricsSingleConfig,
)
from obi_one.scientific.tasks.ephys_extraction.task import ElectrophysiologyMetricsTask

_TASK_MODULE = "obi_one.scientific.tasks.ephys_extraction.task"


class TestElectrophysiologyMetricsConfig:
    def test_scan_and_single_config_defaults(self):
        initialize = ElectrophysiologyMetricsScanConfig.Initialize(trace_id="trace-1")
        scan_config = ElectrophysiologyMetricsScanConfig(initialize=initialize)
        single_config = ElectrophysiologyMetricsSingleConfig(initialize=initialize)

        assert scan_config.initialize.trace_id == "trace-1"
        assert scan_config.initialize.protocols is None
        assert scan_config.initialize.requested_metrics is None
        assert scan_config.initialize.amplitude is None
        assert single_config.initialize.trace_id == "trace-1"

    def test_scan_config_with_optional_fields(self):
        amplitude = AmplitudeInput(min_value=0.1, max_value=0.5)
        initialize = ElectrophysiologyMetricsScanConfig.Initialize(
            trace_id="trace-2",
            protocols=["step"],
            requested_metrics=["spike_count", "mean_frequency"],
            amplitude=amplitude,
        )
        scan_config = ElectrophysiologyMetricsScanConfig(initialize=initialize)

        assert scan_config.initialize.protocols == ["step"]
        assert scan_config.initialize.requested_metrics == ["spike_count", "mean_frequency"]
        assert scan_config.initialize.amplitude == amplitude


class TestElectrophysiologyMetricsTask:
    def test_execute_returns_metrics(self):
        expected = ElectrophysiologyMetricsOutput(
            feature_dict={"step_0": {"spike_count": {"avg": 1}}}
        )
        initialize = SimpleNamespace(
            trace_id="trace-id",
            requested_metrics=["spike_count"],
            amplitude=None,
            protocols=["step"],
        )
        task = ElectrophysiologyMetricsTask.model_construct(
            config=SimpleNamespace(initialize=initialize)
        )
        db_client = MagicMock()

        with patch(
            f"{_TASK_MODULE}.get_electrophysiology_metrics",
            return_value=expected,
        ) as mock_get:
            result = task.execute(db_client=db_client)

        assert result is expected
        mock_get.assert_called_once_with(
            trace_id="trace-id",
            entity_client=db_client,
            calculated_feature=["spike_count"],
            amplitude=None,
            stimuli_types=["step"],
        )

    def test_execute_wraps_failures_in_obi_one_error(self):
        initialize = SimpleNamespace(
            trace_id="trace-id",
            requested_metrics=None,
            amplitude=None,
            protocols=None,
        )
        task = ElectrophysiologyMetricsTask.model_construct(
            config=SimpleNamespace(initialize=initialize)
        )

        with (
            patch(
                f"{_TASK_MODULE}.get_electrophysiology_metrics",
                side_effect=RuntimeError("boom"),
            ),
            pytest.raises(OBIONEError, match="Internal Server Error: boom"),
        ):
            task.execute(db_client=MagicMock())
