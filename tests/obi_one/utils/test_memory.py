import sys
from types import SimpleNamespace

import pytest

from obi_one.utils import memory
from obi_one.utils.memory import malloc_trim, memory_left, memory_limit

MACHINE = 64 * 2**30


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


@pytest.fixture
def cgroup(tmp_path, monkeypatch):
    """No cgroup files and a machine of `MACHINE` bytes; the files to write a limit to."""
    files = SimpleNamespace(v2=tmp_path / "memory.max", v1=tmp_path / "memory.limit_in_bytes")
    monkeypatch.setattr(memory, "MEMORY_LIMIT", files.v2)
    monkeypatch.setattr(memory, "MEMORY_LIMIT_V1", files.v1)
    monkeypatch.setattr(memory.psutil, "virtual_memory", lambda: SimpleNamespace(total=MACHINE))
    return files


class TestMemoryLimit:
    @pytest.mark.usefixtures("cgroup")
    def test_the_machines_without_a_cgroup(self):
        assert memory_limit() == MACHINE

    def test_a_cgroup_v2_limit(self, cgroup):
        cgroup.v2.write_text("17179869184\n")
        assert memory_limit() == 16 * 2**30

    def test_the_machines_where_cgroup_v2_sets_none(self, cgroup):
        cgroup.v2.write_text("max\n")
        assert memory_limit() == MACHINE

    def test_a_cgroup_v1_limit(self, cgroup):
        cgroup.v1.write_text("8589934592\n")
        assert memory_limit() == 8 * 2**30

    def test_the_machines_where_cgroup_v1_sets_more(self, cgroup):
        cgroup.v1.write_text("9223372036854771712\n")
        assert memory_limit() == MACHINE

    @pytest.mark.parametrize(
        ("limit", "rss", "left"),
        [(2**30, 2**28, 2**30 - 2**28), (2**28, 2**30, 0)],
        ids=["beside what the process holds", "none past the limit"],
    )
    def test_what_is_left(self, cgroup, monkeypatch, limit, rss, left):
        cgroup.v2.write_text(str(limit))
        held = SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=rss))
        monkeypatch.setattr(memory.psutil, "Process", lambda: held)
        assert memory_left() == left
