"""Benchmarking utilities for tracking time and memory consumption."""

import json
import logging
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar

import psutil

L = logging.getLogger(__name__)


class BenchmarkTracker:
    """Tracks benchmarks across multiple sections and outputs summary to stdout."""

    _benchmarks: ClassVar[dict] = {}
    _process = psutil.Process()

    @classmethod
    def reset(cls) -> None:
        """Reset all benchmark data."""
        cls._benchmarks = {}

    @classmethod
    @contextmanager
    def section(cls, name: str, poll_interval: float = 0.1):
        """Context manager for benchmarking a code section.

        Args:
            name: Name of the section being benchmarked
            poll_interval: How often to poll memory usage in seconds (default: 0.1)

        Example:
            with BenchmarkTracker.section("data_processing"):
                # code to benchmark
                process_data()
        """
        # Get memory info before (RSS from process)
        mem_info_before = cls._process.memory_info()
        mem_before_mb = mem_info_before.rss / 1024 / 1024

        # Start timing
        start_time = time.perf_counter()

        # Track peak memory in background thread
        peak_mem_mb = mem_before_mb
        stop_monitoring = threading.Event()

        def monitor_memory():
            nonlocal peak_mem_mb
            while not stop_monitoring.is_set():
                try:
                    current_mem = cls._process.memory_info().rss / 1024 / 1024
                    peak_mem_mb = max(peak_mem_mb, current_mem)
                except Exception:  # noqa: S110
                    pass  # Process might be in weird state, ignore
                time.sleep(poll_interval)

        monitor_thread = threading.Thread(target=monitor_memory, daemon=True)
        monitor_thread.start()

        try:
            yield
        finally:
            # Stop monitoring
            stop_monitoring.set()
            monitor_thread.join(timeout=1.0)

            # End timing
            end_time = time.perf_counter()
            duration = end_time - start_time

            # Get memory info after (RSS from process)
            mem_info_after = cls._process.memory_info()
            mem_after_mb = mem_info_after.rss / 1024 / 1024
            mem_delta_mb = mem_after_mb - mem_before_mb

            # Final check for peak (in case it's at the end)
            peak_mem_mb = max(peak_mem_mb, mem_after_mb)

            # Store benchmark data
            cls._benchmarks[name] = {
                "duration_s": round(duration, 2),
                "mem_before_mb": round(mem_before_mb, 2),
                "mem_after_mb": round(mem_after_mb, 2),
                "mem_delta_mb": round(mem_delta_mb, 2),
                "peak_mem_mb": round(peak_mem_mb, 2),
            }

            L.info(
                f"[BENCHMARK] {name}: {duration:.2f}s, "
                f"Memory: {mem_before_mb:.1f} -> {mem_after_mb:.1f} MB "
                f"(Δ {mem_delta_mb:+.1f} MB), Peak: {peak_mem_mb:.1f} MB"
            )

    @classmethod
    def print_summary(cls) -> None:
        """Print a formatted summary of all benchmarks to stdout."""
        if not cls._benchmarks:
            L.info("No benchmark data collected.")
            return

        print("\n" + "=" * 80)
        print("BENCHMARK SUMMARY")
        print("=" * 80)

        total_duration = sum(b["duration_s"] for b in cls._benchmarks.values())

        for name, data in cls._benchmarks.items():
            print(f"\n{name}:")
            print(f"  Duration:      {data['duration_s']:>10.2f} s")
            print(f"  Memory Before: {data['mem_before_mb']:>10.2f} MB")
            print(f"  Memory After:  {data['mem_after_mb']:>10.2f} MB")
            print(f"  Memory Delta:  {data['mem_delta_mb']:>10.2f} MB")
            print(f"  Peak Memory:   {data['peak_mem_mb']:>10.2f} MB")

        print(f"\n{'─' * 80}")
        print(f"Total Duration: {total_duration:.2f} s")
        print("=" * 80 + "\n")

    @classmethod
    def save_to_file(cls, output_path: Path) -> None:
        """Save benchmark results to a JSON file.

        Args:
            output_path: Path to the output JSON file
        """
        if not cls._benchmarks:
            L.warning("No benchmark data to save.")
            return

        # Create output directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Calculate total duration
        total_duration = sum(b["duration_s"] for b in cls._benchmarks.values())

        # Prepare output data
        output_data = {
            "benchmarks": cls._benchmarks,
            "total_duration_s": round(total_duration, 2),
        }

        # Write to file
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)

        L.info(f"Benchmark results saved to {output_path}")

