"""Benchmarking utilities for tracking time and memory consumption."""

import json
import logging
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar

import psutil

L = logging.getLogger(__name__)


class BenchmarkTracker:
    """Tracks benchmarks across multiple sections and outputs summary to stdout."""

    _benchmarks: ClassVar[dict] = {}
    _process = psutil.Process()
    _start_time: ClassVar[float | None] = None

    @classmethod
    def reset(cls) -> None:
        """Reset all benchmark data."""
        cls._benchmarks = {}
        cls._start_time = None

    @classmethod
    def start_tracking(cls) -> None:
        """Start tracking overall execution time."""
        cls._start_time = time.perf_counter()
        L.info("[BENCHMARK] Started tracking overall execution time")

    @classmethod
    @contextmanager
    def section(cls, name: str, poll_interval: float = 0.1) -> Generator[None, None, None]:
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

        def monitor_memory() -> None:
            nonlocal peak_mem_mb
            while not stop_monitoring.is_set():
                try:
                    current_mem = cls._process.memory_info().rss / 1024 / 1024
                    peak_mem_mb = max(peak_mem_mb, current_mem)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
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

            # Log individual benchmark as JSON
            benchmark_json = json.dumps({name: cls._benchmarks[name]})
            L.info(f"[BENCHMARK] {benchmark_json}")

    @classmethod
    def print_summary(cls, output_path: Path | None = None) -> None:
        """Print a JSON summary of all benchmarks to stdout and optionally save to file.

        Args:
            output_path: Optional path to save the benchmark results as JSON file
        """
        if not cls._benchmarks:
            L.info("No benchmark data collected.")
            return

        # Calculate total execution time if tracking was started
        if cls._start_time is not None:
            total_execution_time = time.perf_counter() - cls._start_time
        else:
            total_execution_time = None

        # Calculate sum of benchmarked sections
        benchmarked_time = sum(b["duration_s"] for b in cls._benchmarks.values())

        # Calculate unbenchmarked time
        if total_execution_time is not None:
            unbenchmarked_time = total_execution_time - benchmarked_time
        else:
            unbenchmarked_time = None

        # Prepare summary data
        summary_data = {
            "benchmarks": cls._benchmarks,
            "benchmarked_time_s": round(benchmarked_time, 2),
        }

        # Add total execution and unbenchmarked time if available
        if total_execution_time is not None:
            summary_data["total_execution_time_s"] = round(total_execution_time, 2)
            summary_data["unbenchmarked_time_s"] = round(unbenchmarked_time, 2)
            summary_data["unbenchmarked_percentage"] = round(
                (unbenchmarked_time / total_execution_time) * 100, 1
            )

        # Print as single-line JSON with same format as individual sections
        summary_json = json.dumps(summary_data)
        L.info(f"[BENCHMARK SUMMARY] {summary_json}")

        # Save to file if path provided
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2)
            L.info(f"Benchmark results saved to {output_path}")
