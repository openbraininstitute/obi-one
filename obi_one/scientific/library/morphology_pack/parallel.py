"""Work spread over processes, its results in the order of the work."""

import multiprocessing
import os
import sys
import threading
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ProcessPoolExecutor
from functools import partial
from pathlib import Path
from types import TracebackType
from typing import Self

# Jobs sent ahead for each process, so that it never waits for the next while few are held.
AHEAD = 2
CPU_QUOTA = Path("/sys/fs/cgroup/cpu.max")
PRELOAD = [
    "__main__",
    "obi_one.scientific.library.morphology_pack.geometry",
    "obi_one.scientific.library.morphology_pack.writer",
]


def available_cpus() -> int:
    """The CPUs this process may run on, within its container's quota where it has one."""
    if sys.platform != "linux":
        return os.cpu_count() or 1
    cpus = len(os.sched_getaffinity(0))
    try:
        quota, period = CPU_QUOTA.read_text(encoding="ascii").split()
        return max(1, min(cpus, int(quota) // int(period)))
    except (OSError, ValueError):
        # no quota: "max", or no cgroup v2
        return cpus


def each[T, R](function: Callable[[T], R], items: list[T]) -> list[R]:
    return [function(item) for item in items]


def started(pool: ProcessPoolExecutor) -> None:
    try:
        pool.submit(int)
    except RuntimeError:
        # shut down before it started
        return


def batches[T](items: Iterable[T], size: int) -> Iterator[list[T]]:
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


class Processes:
    """`workers` processes to map work over, or this process alone where `workers` is 1.

    Entered, the processes start at once, in the background. They are forked from a server that
    has imported the main module, as `__mp_main__`, and the pack's modules, which a process with
    threads may do safely; a script that uses them keeps its work under
    `if __name__ == "__main__"`.
    """

    def __init__(self, workers: int) -> None:
        """Processes not yet started."""
        self.workers = workers
        self.pool: ProcessPoolExecutor | None = None

    def __enter__(self) -> Self:
        """Start the processes."""
        if self.workers > 1:
            context = multiprocessing.get_context("forkserver")
            context.set_forkserver_preload(PRELOAD)
            self.pool = ProcessPoolExecutor(self.workers, mp_context=context)
            threading.Thread(target=started, args=(self.pool,), daemon=True).start()
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
        process are held at once.
        """
        if self.pool is None:
            yield from map(function, items)
            return
        job = partial(each, function)
        sent: deque[Future[list[R]]] = deque()
        try:
            for batch in batches(items, per_job):
                sent.append(self.pool.submit(job, batch))
                if len(sent) >= AHEAD * self.workers:
                    yield from sent.popleft().result()
            while sent:
                yield from sent.popleft().result()
        finally:
            for future in sent:
                future.cancel()


ALONE = Processes(1)
