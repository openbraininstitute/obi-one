"""Tests for deriving electrical cell recording properties."""

from unittest.mock import Mock
from uuid import uuid4

import app.services.electrical_cell_recording_properties as test_module


def test_get_electrical_cell_recording_properties_fetches_each_unique_id_once():
    client = Mock()
    client.get_entity.side_effect = lambda entity_id, **_: Mock(stimuli=[], id=entity_id)
    first_id, second_id = uuid4(), uuid4()

    protocols, amplitudes = test_module.get_electrical_cell_recording_properties(
        recording_ids=[first_id, second_id, first_id],
        db_client=client,
    )

    assert protocols == {str(first_id): [], str(second_id): []}
    assert amplitudes == {}
    assert client.get_entity.call_count == 2
    client.fetch_assets.assert_not_called()
