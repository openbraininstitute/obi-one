import sys

import pytest

from obi_one.scientific.library.morphology_pack import parallel
from obi_one.scientific.library.morphology_pack.parallel import Processes, available_cpus


@pytest.fixture
def on_linux_with_eight_cpus(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(parallel.os, "sched_getaffinity", lambda _: set(range(8)), raising=False)
    monkeypatch.setattr(parallel, "CPU_QUOTA", tmp_path / "cpu.max")
    return tmp_path / "cpu.max"


class TestAvailableCpus:
    @pytest.mark.parametrize(
        ("quota", "cpus"),
        [("max 100000", 8), ("200000 100000", 2), ("50000 100000", 1), ("1600000 100000", 8)],
    )
    def test_within_the_container_quota(self, on_linux_with_eight_cpus, quota, cpus):
        on_linux_with_eight_cpus.write_text(f"{quota}\n")
        assert available_cpus() == cpus

    def test_every_cpu_without_a_quota(self, on_linux_with_eight_cpus):
        assert not on_linux_with_eight_cpus.exists()
        assert available_cpus() == 8


class TestProcesses:
    def test_results_come_in_the_order_of_the_work(self):
        with Processes(2) as processes:
            assert list(processes.map(abs, range(-50, 0), per_job=3)) == list(range(50, 0, -1))
