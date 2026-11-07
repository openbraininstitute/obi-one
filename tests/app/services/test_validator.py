"""Tests for the write-intercepting validation client."""

from unittest.mock import MagicMock
from uuid import UUID

from entitysdk.models import Simulation

from app.services.validator import _WriteInterceptingClient


def test_register_entity_returns_simulation_mock_for_simulation():
    client = _WriteInterceptingClient(MagicMock())

    result = client.register_entity(MagicMock(spec=Simulation))

    assert isinstance(result.id, UUID)
    assert client.register_call_count == 1


def test_register_entity_returns_plain_mock_for_other_entities():
    client = _WriteInterceptingClient(MagicMock())

    result = client.register_entity(object())

    assert isinstance(result.id, UUID)
    assert client.register_call_count == 1
