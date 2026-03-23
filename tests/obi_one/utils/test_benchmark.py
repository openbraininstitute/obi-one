import json
import time

import pytest

from obi_one.utils.benchmark import BenchmarkTracker


@pytest.fixture(autouse=True)
def _reset_tracker():
    """Reset and enable BenchmarkTracker before each test."""
    BenchmarkTracker.reset()
    BenchmarkTracker.enable()
    yield
    BenchmarkTracker.reset()
    BenchmarkTracker.enable()


def test_enable_disable():
    assert BenchmarkTracker.is_enabled() is True
    BenchmarkTracker.disable()
    assert BenchmarkTracker.is_enabled() is False
    BenchmarkTracker.enable()
    assert BenchmarkTracker.is_enabled() is True


def test_reset():
    with BenchmarkTracker.section("test_section"):
        pass
    BenchmarkTracker.reset()
    assert BenchmarkTracker._benchmarks == {}
    assert BenchmarkTracker._start_time is None


def test_section_records_benchmark():
    with BenchmarkTracker.section("my_section"):
        time.sleep(0.05)

    assert "my_section" in BenchmarkTracker._benchmarks
    data = BenchmarkTracker._benchmarks["my_section"]
    assert data["duration_s"] >= 0.04
    assert "mem_before_mb" in data
    assert "mem_after_mb" in data
    assert "mem_delta_mb" in data
    assert "peak_mem_mb" in data


def test_section_disabled_is_noop():
    BenchmarkTracker.disable()
    with BenchmarkTracker.section("noop_section"):
        pass
    assert BenchmarkTracker._benchmarks == {}


def test_multiple_sections():
    with BenchmarkTracker.section("section_a"):
        time.sleep(0.02)
    with BenchmarkTracker.section("section_b"):
        time.sleep(0.02)

    assert "section_a" in BenchmarkTracker._benchmarks
    assert "section_b" in BenchmarkTracker._benchmarks


def test_start_tracking():
    BenchmarkTracker.start_tracking()
    assert BenchmarkTracker._start_time is not None


def test_start_tracking_disabled():
    BenchmarkTracker.disable()
    BenchmarkTracker.start_tracking()
    assert BenchmarkTracker._start_time is None


def test_print_summary_logs_json(caplog):
    BenchmarkTracker.start_tracking()
    with BenchmarkTracker.section("summarized"):
        time.sleep(0.02)

    with caplog.at_level("INFO", logger="obi_one.utils.benchmark"):
        BenchmarkTracker.print_summary()

    summary_lines = [r.message for r in caplog.records if "[BENCHMARK SUMMARY]" in r.message]
    assert len(summary_lines) == 1
    json_str = summary_lines[0].replace("[BENCHMARK SUMMARY] ", "")
    summary = json.loads(json_str)
    assert "benchmarks" in summary
    assert "summarized" in summary["benchmarks"]
    assert "total_execution_time_s" in summary
    assert "unbenchmarked_time_s" in summary
    assert "unbenchmarked_percentage" in summary


def test_print_summary_disabled(caplog):
    BenchmarkTracker.disable()
    with caplog.at_level("INFO", logger="obi_one.utils.benchmark"):
        BenchmarkTracker.print_summary()
    assert not any("[BENCHMARK SUMMARY]" in r.message for r in caplog.records)


def test_print_summary_no_data(caplog):
    with caplog.at_level("INFO", logger="obi_one.utils.benchmark"):
        BenchmarkTracker.print_summary()
    assert any("No benchmark data" in r.message for r in caplog.records)


def test_print_summary_to_file(tmp_path):
    BenchmarkTracker.start_tracking()
    with BenchmarkTracker.section("file_test"):
        pass

    output_file = tmp_path / "results.json"
    BenchmarkTracker.print_summary(output_path=output_file)

    assert output_file.exists()
    data = json.loads(output_file.read_text())
    assert "benchmarks" in data
    assert "file_test" in data["benchmarks"]


def test_section_exception_still_records():
    msg = "boom"
    with pytest.raises(ValueError, match=msg), BenchmarkTracker.section("failing"):
        raise ValueError(msg)

    assert "failing" in BenchmarkTracker._benchmarks
    assert BenchmarkTracker._benchmarks["failing"]["duration_s"] >= 0
