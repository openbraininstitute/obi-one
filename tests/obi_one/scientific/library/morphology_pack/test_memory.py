import sys
from types import SimpleNamespace

import pytest

from obi_one.scientific.library.morphology_pack import memory
from obi_one.scientific.library.morphology_pack.memory import give_back, malloc_trim


@pytest.fixture
def found_again():
    malloc_trim.cache_clear()
    yield
    malloc_trim.cache_clear()


pytestmark = pytest.mark.usefixtures("found_again")


def test_none_off_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert malloc_trim() is None
    give_back()


def test_none_where_the_c_library_has_none(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(memory.ctypes, "CDLL", lambda _: SimpleNamespace())
    assert malloc_trim() is None
    give_back()


def test_trims_everything_freed(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(memory.ctypes, "CDLL", lambda _: SimpleNamespace(malloc_trim=calls.append))
    give_back()
    assert calls == [0]
