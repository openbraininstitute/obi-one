from collections.abc import Generator

import pytest

from obi_one.config import settings
from obi_one.utils.benchmark import BenchmarkTracker
from tests.httpx_mock import HTTPXMock, mock_httpx


@pytest.fixture(autouse=True)  # ruff: ignore[pytest-fixture-autouse]
def _disable_task_benchmarking(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Keep production defaults on; tests must not pay BenchmarkTracker section overhead.

    Task modules enable the tracker at import when settings say so. Force it off for the suite
    unless a test re-enables (e.g. utils/test_benchmark.py, recording-array phase coverage).
    """
    monkeypatch.setattr(settings.circuit_extraction, "benchmarking_enabled", False)
    monkeypatch.setattr(settings.synapse_parameterization, "benchmarking_enabled", False)
    monkeypatch.setattr(settings.extracellular_recording_weights, "benchmarking_enabled", False)
    BenchmarkTracker.disable()
    yield


@pytest.fixture
def httpx_mock() -> Generator[HTTPXMock, None, None]:
    with mock_httpx() as mock:
        yield mock
