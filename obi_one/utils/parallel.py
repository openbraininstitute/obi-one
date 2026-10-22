"""Work spread over processes, its results in the order of the work."""

import multiprocessing
import os
import sys
import threading
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import Future, ProcessPoolExecutor
from functools import partial
from itertools import batched
from multiprocessing import forkserver
from pathlib import Path
from types import TracebackType
from typing import Self

from obi_one.utils.memory import hand_back_freed

# Jobs sent ahead for each process, so that it never waits for the next while few are held.
AHEAD = 2
CPU_QUOTA = Path("/sys/fs/cgroup/cpu.max")
CPU_QUOTA_V1 = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
CPU_PERIOD_V1 = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")


def cpu_quota() -> int | None:
    """The CPUs the container's cgroup, v2 or v1, allows this process, or None where it sets no
    limit.
    """
    if CPU_QUOTA.exists():
        quota, period = CPU_QUOTA.read_text(encoding="ascii").split()
    elif CPU_QUOTA_V1.exists():
        quota = CPU_QUOTA_V1.read_text(encoding="ascii").strip()
        period = CPU_PERIOD_V1.read_text(encoding="ascii").strip()
    else:
        return None
    if quota in {"max", "-1"}:
        return None
    return max(1, int(quota) // int(period))


def available_cpus() -> int:
    """The CPUs this process may run on, within its container's quota where it has one."""
    if sys.platform != "linux":
        return os.cpu_count() or 1
    cpus = len(os.sched_getaffinity(0))
    quota = cpu_quota()
    return cpus if quota is None else min(cpus, quota)


def each[T, R](function: Callable[[T], R], items: Iterable[T]) -> list[R]:
    """`function` of each of `items`, then what it freed handed back to the system."""
    results = [function(item) for item in items]
    hand_back_freed()
    return results


class Processes:
    """`workers` processes to map work over, or this process alone where `workers` is 1.

    Entered, the server the processes are forked from starts in the background, with the modules
    `preload` names imported, which a process with threads may do safely. Each process imports
    the main module as `__mp_main__`, so a script that uses them keeps its work under
    `if __name__ == "__main__"`.
    """

    def __init__(self, workers: int, preload: Sequence[str] = ()) -> None:
        """Processes not yet started."""
        self.workers = workers
        self.preload = list(preload)
        self.pool: ProcessPoolExecutor | None = None

    def __enter__(self) -> Self:
        """Start the processes."""
        if self.workers > 1:
            context = multiprocessing.get_context("forkserver")
            context.set_forkserver_preload(self.preload)
            self.pool = ProcessPoolExecutor(self.workers, mp_context=context)
            threading.Thread(target=forkserver.ensure_running, daemon=True).start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        """Stop the processes, and the work not yet begun."""
        if self.pool is not None:
            self.pool.shutdown(cancel_futures=True)
            self.pool = None

    def map[T, R](
        self, function: Callable[[T], R], items: Iterable[T], per_job: int = 1
    ) -> Iterator[R]:
        """`function` of each of `items`, in order, `per_job` items a job. Only `AHEAD` jobs a
        process are held at once, and each process hands back what a job freed.
        """
        if self.pool is None:
            yield from map(function, items)
            return
        job = partial(each, function)
        sent: deque[Future[list[R]]] = deque()
        try:
            for batch in batched(items, per_job):
                sent.append(self.pool.submit(job, batch))
                if len(sent) >= AHEAD * self.workers:
                    yield from sent.popleft().result()
            while sent:
                yield from sent.popleft().result()
        finally:
            for future in sent:
                future.cancel()


ALONE = Processes(1)
