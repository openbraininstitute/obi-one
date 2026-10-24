import sys
from types import SimpleNamespace

import pytest

from obi_one.utils import memory
from obi_one.utils.memory import malloc_trim


@pytest.fixture
def found_again():
    malloc_trim.cache_clear()
    yield
    malloc_trim.cache_clear()


pytestmark = pytest.mark.usefixtures("found_again")


def test_none_off_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert malloc_trim() is None


def test_none_where_the_c_library_has_none(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(memory.ctypes, "CDLL", lambda _: SimpleNamespace())
    assert malloc_trim() is None


def test_glibcs_on_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(memory.ctypes, "CDLL", lambda _: SimpleNamespace(malloc_trim=print))
    assert malloc_trim() is print
