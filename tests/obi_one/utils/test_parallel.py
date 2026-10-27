import pickle  # ruff: ignore[suspicious-pickle-import]
import sys
import threading

import pytest

from obi_one.utils import memory, parallel
from obi_one.utils.parallel import Processes, available_cpus, each


@pytest.fixture
def cgroup(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(parallel.os, "sched_getaffinity", lambda _: set(range(8)), raising=False)
    monkeypatch.setattr(parallel, "CPU_QUOTA", tmp_path / "cpu.max")
    monkeypatch.setattr(parallel, "CPU_QUOTA_V1", tmp_path / "cpu.cfs_quota_us")
    monkeypatch.setattr(parallel, "CPU_PERIOD_V1", tmp_path / "cpu.cfs_period_us")
    return tmp_path


class TestAvailableCpus:
    @pytest.mark.parametrize(
        ("quota", "cpus"),
        [("max 100000", 8), ("200000 100000", 2), ("50000 100000", 1), ("1600000 100000", 8)],
    )
    def test_within_the_container_quota(self, cgroup, quota, cpus):
        (cgroup / "cpu.max").write_text(f"{quota}\n")
        assert available_cpus() == cpus

    @pytest.mark.parametrize(("quota", "cpus"), [("-1", 8), ("300000", 3), ("50000", 1)])
    def test_within_a_cgroup_v1_quota(self, cgroup, quota, cpus):
        (cgroup / "cpu.cfs_quota_us").write_text(f"{quota}\n")
        (cgroup / "cpu.cfs_period_us").write_text("100000\n")
        assert available_cpus() == cpus

    def test_every_cpu_without_a_quota(self, cgroup):
        assert not any(cgroup.iterdir())
        assert available_cpus() == 8

    def test_every_cpu_off_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(parallel.os, "cpu_count", lambda: 6)
        assert available_cpus() == 6


UNPICKLED_IN: list[int] = []


def note_the_thread() -> None:
    UNPICKLED_IN.append(threading.get_ident())


class NotesItsThread:
    """Notes the thread it is unpickled in."""

    def __reduce__(self):
        return note_the_thread, ()


def notes_its_thread(_) -> NotesItsThread:
    return NotesItsThread()


class TestProcesses:
    def test_results_come_in_the_order_of_the_work(self):
        with Processes(2) as processes:
            assert list(processes.map(abs, range(-50, 0), per_job=3)) == list(range(50, 0, -1))

    def test_the_processes_serve_on_after_results_are_left_unread(self):
        with Processes(2) as processes:
            results = processes.map(abs, range(-50, 0))
            assert next(results) == 50
            results.close()
            assert list(processes.map(abs, [-1, -2])) == [1, 2]

    def test_results_are_unpickled_in_the_callers_thread(self):
        UNPICKLED_IN.clear()
        with Processes(2) as processes:
            list(processes.map(notes_its_thread, range(4)))
        assert [threading.get_ident()] * 4 == UNPICKLED_IN

    def test_a_job_hands_back_what_it_freed(self, monkeypatch):
        calls = []
        monkeypatch.setattr(memory, "malloc_trim", lambda: calls.append)
        assert pickle.loads(each(abs, [-1, -2])) == [1, 2]  # ruff: ignore[suspicious-pickle-usage]
        assert calls == [0]
