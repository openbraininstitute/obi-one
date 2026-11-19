"""Tests for electrophysiology metric extraction helpers."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from obi_one.core.exception import ProtocolNotFoundError
from obi_one.scientific.library.ephys_extraction import get_electrophysiology_metrics


def test_get_electrophysiology_metrics_rejects_missing_protocol():
    """Requested stimuli are checked against the recording's stimulus list."""
    stimulus = MagicMock()
    stimulus.name = "IDRest"
    recording = MagicMock()
    recording.stimuli = [stimulus]

    client = MagicMock()
    client.get_entity.return_value = recording

    with pytest.raises(ProtocolNotFoundError, match="None of the requested protocols"):
        get_electrophysiology_metrics(
            trace_id=str(uuid4()),
            entity_client=client,
            calculated_feature=["AP_amplitude"],
            stimuli_types=["nonexistent"],
        )
