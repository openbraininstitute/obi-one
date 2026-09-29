"""Tests for the launch-script dependency compiler.

These cover the helper logic that does not invoke ``uv pip compile`` (which needs
the network / CodeArtifact auth and is exercised by the ``check-launch-deps`` CI
job instead). ``launch_deps_compile`` is a standalone script under
``launch_scripts/tools/`` and is importable here via the ``pythonpath`` pytest setting.
"""

import subprocess  # ruff: ignore[suspicious-subprocess-import]
import time

import launch_deps_compile
import pytest


class TestResolveInFiles:
    def test_default_discovers_all_launch_in_files(self):
        # No paths -> every launch-script .in under the real repo tree.
        result = launch_deps_compile.resolve_in_files([])
        assert result  # there is at least one .in file in the repo
        assert all(p.suffix == ".in" for p in result)
        assert result == sorted(result)  # sorted, de-duplicated

    def test_single_in_file(self, tmp_path):
        f = tmp_path / "reqs.in"
        f.write_text("obi-one\n", encoding="utf-8")
        assert launch_deps_compile.resolve_in_files([str(f)]) == [f.resolve()]

    def test_directory_is_searched_recursively(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "one.in").write_text("obi-one\n", encoding="utf-8")
        (tmp_path / "two.in").write_text("obi-one\n", encoding="utf-8")
        (tmp_path / "ignored.txt").write_text("x\n", encoding="utf-8")
        result = launch_deps_compile.resolve_in_files([str(tmp_path)])
        assert result == sorted(
            [(tmp_path / "a" / "one.in").resolve(), (tmp_path / "two.in").resolve()]
        )

    def test_multiple_paths_are_unioned_and_deduplicated(self, tmp_path):
        f1 = tmp_path / "one.in"
        f1.write_text("obi-one\n", encoding="utf-8")
        f2 = tmp_path / "two.in"
        f2.write_text("obi-one\n", encoding="utf-8")
        # f1 given both directly and via the directory -> de-duplicated.
        result = launch_deps_compile.resolve_in_files([str(f1), str(tmp_path)])
        assert result == sorted([f1.resolve(), f2.resolve()])

    def test_nonexistent_path_raises(self, tmp_path):
        with pytest.raises(SystemExit, match=r"Not an \.in file or directory"):
            launch_deps_compile.resolve_in_files([str(tmp_path / "missing.in")])

    def test_non_in_file_raises(self, tmp_path):
        f = tmp_path / "reqs.txt"
        f.write_text("x\n", encoding="utf-8")
        with pytest.raises(SystemExit, match=r"Not an \.in file or directory"):
            launch_deps_compile.resolve_in_files([str(f)])


class TestCheckInTxtPairing:
    def _deps_dir(self, tmp_path):
        d = tmp_path / "launch_x" / "dependencies"
        d.mkdir(parents=True)
        return d

    def test_paired_files_ok(self, tmp_path, monkeypatch):
        d = self._deps_dir(tmp_path)
        (d / "default.in").write_text("obi-one\n", encoding="utf-8")
        (d / "default.txt").write_text("obi-one\n", encoding="utf-8")
        monkeypatch.setattr(launch_deps_compile, "REPO_ROOT", tmp_path)
        assert launch_deps_compile.check_in_txt_pairing([d / "default.in"]) is False

    def test_orphan_txt_detected(self, tmp_path, monkeypatch, capsys):
        d = self._deps_dir(tmp_path)
        (d / "default.in").write_text("obi-one\n", encoding="utf-8")
        (d / "default.txt").write_text("obi-one\n", encoding="utf-8")
        (d / "orphan.txt").write_text("x\n", encoding="utf-8")  # no .in
        monkeypatch.setattr(launch_deps_compile, "REPO_ROOT", tmp_path)
        assert launch_deps_compile.check_in_txt_pairing([d / "default.in"]) is True
        assert "MISSING .in" in capsys.readouterr().err

    def test_missing_txt_detected(self, tmp_path, monkeypatch, capsys):
        d = self._deps_dir(tmp_path)
        (d / "default.in").write_text("obi-one\n", encoding="utf-8")  # no .txt
        monkeypatch.setattr(launch_deps_compile, "REPO_ROOT", tmp_path)
        assert launch_deps_compile.check_in_txt_pairing([d / "default.in"]) is True
        assert "MISSING .txt" in capsys.readouterr().err


class TestBuildResolveInput:
    def test_obi_one_line_rewritten_to_local_project(self, tmp_path):
        f = tmp_path / "reqs.in"
        f.write_text("obi-one[connectivity]\nnumpy\n", encoding="utf-8")
        resolved, obi_one_lines = launch_deps_compile._build_resolve_input(f)
        # The obi-one line is preserved verbatim for the output header...
        assert obi_one_lines == ["obi-one[connectivity]"]
        # ...and rewritten to the local project path (with extras) for resolution.
        repo = launch_deps_compile.REPO_ROOT.as_posix()
        resolved_lines = resolved.splitlines()
        assert f"{repo}[connectivity]" in resolved_lines
        assert "numpy" in resolved_lines
        # No bare "obi-one[...]" requirement line remains (the repo dir may itself
        # be named "obi-one", so compare whole lines, not substrings).
        assert "obi-one[connectivity]" not in resolved_lines

    def test_no_obi_one_passthrough(self, tmp_path):
        f = tmp_path / "reqs.in"
        f.write_text("# comment\nnumpy==2.0\n\n", encoding="utf-8")
        resolved, obi_one_lines = launch_deps_compile._build_resolve_input(f)
        assert obi_one_lines == []
        assert "numpy==2.0" in resolved
        assert "# comment" in resolved


class TestExistingPins:
    def test_missing_file_returns_empty(self, tmp_path):
        assert not launch_deps_compile._existing_pins(tmp_path / "nope.txt")

    def test_strips_header_comments_and_obi_one(self, tmp_path):
        f = tmp_path / "out.txt"
        f.write_text(
            "# autogenerated header\nobi-one[connectivity]\nnumpy==2.4.6\npandas==2.3.3\n",
            encoding="utf-8",
        )
        pins = launch_deps_compile._existing_pins(f)
        assert pins == "numpy==2.4.6\npandas==2.3.3\n"
        assert "obi-one" not in pins
        assert "#" not in pins


class TestPythonFloorVersion:
    def test_parses_requires_python_lower_bound(self):
        # Reads the real pyproject; must return a dotted version >= 3.12.
        version = launch_deps_compile._python_floor_version()
        assert version.startswith("3.12")


class TestMain:
    """``main`` with ``compile_in_file`` replaced, so no uv resolution runs."""

    def _setup(self, tmp_path, monkeypatch, names=("a", "b", "c")):
        d = tmp_path / "launch_x" / "dependencies"
        d.mkdir(parents=True)
        for name in names:
            (d / f"{name}.in").write_text("numpy\n", encoding="utf-8")
            (d / f"{name}.txt").write_text(f"{name}-content", encoding="utf-8")
        monkeypatch.setattr(launch_deps_compile, "REPO_ROOT", tmp_path)
        return d

    def test_parallel_results_reported_in_file_order(self, tmp_path, monkeypatch, capsys):
        d = self._setup(tmp_path, monkeypatch)
        delays = {"a": 0.2, "b": 0.1, "c": 0.0}  # finish in reverse order

        def fake_compile(in_file, *, upgrade=False):  # ruff: ignore[unused-function-argument]
            time.sleep(delays[in_file.stem])
            return f"{in_file.stem}-content" if in_file.stem != "b" else "changed"

        monkeypatch.setattr(launch_deps_compile, "compile_in_file", fake_compile)
        assert launch_deps_compile.main(["--check", "--jobs", "3", str(d)]) == 1
        captured = capsys.readouterr()
        assert [line.split("/")[-1] for line in captured.out.splitlines()] == ["a.txt", "c.txt"]
        assert "STALE: launch_x/dependencies/b.txt" in captured.err
        assert "1 frozen requirements file(s) are out of date" in captured.err

    def test_writes_files(self, tmp_path, monkeypatch):
        d = self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(launch_deps_compile, "compile_in_file", lambda f, **_: f"new-{f.stem}")
        assert launch_deps_compile.main([str(d)]) == 0
        assert (d / "b.txt").read_text(encoding="utf-8") == "new-b"

    def _failing_compile(self, in_file, *, upgrade=False):  # ruff: ignore[unused-method-argument]
        if in_file.stem == "b":
            raise subprocess.CalledProcessError(1, ["uv"], stderr="uv: no solution\n")
        return f"{in_file.stem}-content"

    def test_failure_prints_uv_stderr_and_raises(self, tmp_path, monkeypatch, capsys):
        d = self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(launch_deps_compile, "compile_in_file", self._failing_compile)
        with pytest.raises(subprocess.CalledProcessError):
            launch_deps_compile.main(["--check", str(d)])
        assert "uv: no solution" in capsys.readouterr().err

    def test_failure_skipped(self, tmp_path, monkeypatch, capsys):
        d = self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(launch_deps_compile, "compile_in_file", self._failing_compile)
        assert launch_deps_compile.main(["--check", "--skip-unresolvable", str(d)]) == 0
        err = capsys.readouterr().err
        assert "uv: no solution" in err
        assert "SKIP (unresolvable): launch_x/dependencies/b.in" in err

    @pytest.mark.parametrize("jobs", ["0", "-1", "x"])
    def test_invalid_jobs(self, jobs):
        with pytest.raises(SystemExit):
            launch_deps_compile.parse_args(["--jobs", jobs])
