"""Tests for the launch-script dependency compiler.

These cover the helper logic that does not invoke ``uv pip compile`` (which needs
the network / CodeArtifact auth and is exercised by the ``check-launch-deps`` CI
job instead). ``launch_deps_compile`` is a standalone script under
``launch_scripts/tools/`` and is importable here via the ``pythonpath`` pytest setting.
"""

import re
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import time
from pathlib import Path

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

    @pytest.mark.parametrize("line", ["obi-one==2026.9.1", "obi-one @ git+https://x.org/r.git"])
    def test_rejects_non_bare_obi_one(self, tmp_path, line):
        f = tmp_path / "reqs.in"
        f.write_text(f"{line}\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="the obi-one line must be bare"):
            launch_deps_compile._build_resolve_input(f)

    def test_no_obi_one_passthrough(self, tmp_path):
        f = tmp_path / "reqs.in"
        f.write_text("# comment\nnumpy==2.0\n\n", encoding="utf-8")
        resolved, obi_one_lines = launch_deps_compile._build_resolve_input(f)
        assert obi_one_lines == []
        assert "numpy==2.0" in resolved
        assert "# comment" in resolved


class TestCurrentReleasePin:
    def _write(self, tmp_path, name, text):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_returns_common_pin(self, tmp_path):
        files = [
            self._write(tmp_path, "a.txt", "obi-one[emodel]==2026.9.15\nnumpy==2.0\n"),
            self._write(tmp_path, "b.txt", "obi-one==2026.9.15\n"),
            self._write(tmp_path, "c.txt", "numpy==2.0\n"),
        ]
        assert launch_deps_compile.current_release_pin(files) == "2026.9.15"

    def test_ignores_bare_and_other_specs(self, tmp_path):
        files = [
            self._write(tmp_path, "a.txt", "obi-one==2026.9.15\n"),
            self._write(tmp_path, "b.txt", "obi-one\n"),
            self._write(tmp_path, "c.txt", "obi-one @ git+https://x.org/r.git@abc\n"),
        ]
        assert launch_deps_compile.current_release_pin(files) == "2026.9.15"

    def test_none_when_unpinned(self, tmp_path):
        files = [self._write(tmp_path, "a.txt", "obi-one[emodel]\n")]
        assert launch_deps_compile.current_release_pin(files) is None

    def test_different_pins_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launch_deps_compile, "REPO_ROOT", tmp_path)
        files = [
            self._write(tmp_path, "a.txt", "obi-one==2026.9.15\n"),
            self._write(tmp_path, "b.txt", "obi-one==2026.9.14\n"),
        ]
        with pytest.raises(
            SystemExit, match=r"different obi-one releases(.|\n)*==2026\.9\.14: b\.txt"
        ):
            launch_deps_compile.current_release_pin(files)

    def test_repo_files_are_consistent(self):
        files = sorted(launch_deps_compile.LAUNCH_SCRIPTS_DIR.glob("*/dependencies/*.txt"))
        launch_deps_compile.current_release_pin(files)


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

        def fake_compile(in_file, **_):
            time.sleep(delays[in_file.stem])
            return f"{in_file.stem}-content" if in_file.stem != "b" else "changed"

        monkeypatch.setattr(launch_deps_compile, "compile_in_file", fake_compile)
        assert launch_deps_compile.main(["--check", "--jobs", "3", str(d)]) == 1
        captured = capsys.readouterr()
        assert [line.split()[1].split("/")[-1] for line in captured.out.splitlines()] == [
            "a.txt",
            "c.txt",
        ]
        assert "STALE: launch_x/dependencies/b.txt" in captured.err
        assert "1 frozen requirements file(s) are out of date" in captured.err

    def test_reports_time_and_index(self, tmp_path, monkeypatch, capsys):
        d = self._setup(tmp_path, monkeypatch, names=("a",))
        (d / "b.in").write_text("ultraliser\n", encoding="utf-8")
        (d / "b.txt").write_text("b-content", encoding="utf-8")
        monkeypatch.setenv("UV_INDEX_OBI_CODEARTIFACT_PASSWORD", "secret")
        monkeypatch.setattr(
            launch_deps_compile, "compile_in_file", lambda f, **_: f"{f.stem}-content"
        )
        assert launch_deps_compile.main(["--check", str(d)]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert re.fullmatch(r"ok: \S+/a\.txt \[\d+\.\ds, pypi\]", lines[0])
        assert re.fullmatch(r"ok: \S+/b\.txt \[\d+\.\ds, codeartifact\+pypi\]", lines[1])

    @pytest.mark.parametrize("pin", ["2026.9.15", None])
    def test_passes_committed_pin(self, tmp_path, monkeypatch, pin):
        d = self._setup(tmp_path, monkeypatch, names=("a",))
        other = tmp_path / "launch_y" / "dependencies" / "other.txt"
        other.parent.mkdir(parents=True)
        other.write_text(f"obi-one=={pin}\n" if pin else "obi-one\n", encoding="utf-8")
        monkeypatch.setattr(launch_deps_compile, "LAUNCH_SCRIPTS_DIR", tmp_path)
        pins = []

        def fake_compile(in_file, *, obi_one_pin, **_):
            pins.append(obi_one_pin)
            return f"{in_file.stem}-content"

        monkeypatch.setattr(launch_deps_compile, "compile_in_file", fake_compile)
        # Only launch_x is compiled, but the pin comes from all committed files.
        assert launch_deps_compile.main(["--check", str(d)]) == 0
        assert pins == [pin]

    def test_writes_files(self, tmp_path, monkeypatch):
        d = self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(launch_deps_compile, "compile_in_file", lambda f, **_: f"new-{f.stem}")
        assert launch_deps_compile.main([str(d)]) == 0
        assert (d / "b.txt").read_text(encoding="utf-8") == "new-b"

    @pytest.mark.parametrize("extra_args", [[], ["--upgrade"]])
    def test_missing_txt_created(self, tmp_path, monkeypatch, capsys, extra_args):
        d = self._setup(tmp_path, monkeypatch)
        (d / "b.txt").unlink()
        monkeypatch.setattr(launch_deps_compile, "compile_in_file", lambda f, **_: f"new-{f.stem}")
        assert launch_deps_compile.main([*extra_args, str(d)]) == 0
        assert (d / "b.txt").read_text(encoding="utf-8") == "new-b"
        assert "MISSING" not in capsys.readouterr().err

    def test_missing_txt_fails_check(self, tmp_path, monkeypatch, capsys):
        d = self._setup(tmp_path, monkeypatch)
        (d / "b.txt").unlink()
        monkeypatch.setattr(
            launch_deps_compile, "compile_in_file", lambda f, **_: f"{f.stem}-content"
        )
        assert launch_deps_compile.main(["--check", str(d)]) == 1
        assert not (d / "b.txt").exists()
        err = capsys.readouterr().err
        assert "MISSING .txt for launch_x/dependencies/b.in" in err
        assert "STALE: launch_x/dependencies/b.txt" in err

    def test_orphan_txt_fails_compile(self, tmp_path, monkeypatch, capsys):
        d = self._setup(tmp_path, monkeypatch)
        (d / "orphan.txt").write_text("x", encoding="utf-8")
        monkeypatch.setattr(launch_deps_compile, "compile_in_file", lambda f, **_: f"new-{f.stem}")
        assert launch_deps_compile.main([str(d)]) == 1
        assert "MISSING .in for launch_x/dependencies/orphan.txt" in capsys.readouterr().err

    def _failing_compile(self, in_file, **_):
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


class TestPrivateIndex:
    @pytest.mark.parametrize(
        ("in_text", "txt_text", "expected"),
        [
            ("obi-one\nultraliser==2.2.7\n", None, True),
            ("obi-one\nUltra_Liser>=2\n", None, False),  # different normalized name
            ("obi-one\nNeuroMorphoMesh\n", None, True),
            ("obi-one[meshing]\n", "obi-one[meshing]\nneuromorphomesh==1.0\n", True),  # transitive
            ("obi-one\nnumpy\n# ultraliser\n", "obi-one\nnumpy==2.0\n", False),
            ("obi-one\nultraliser-tools\n", None, False),
        ],
    )
    def test_needs_private_index(self, tmp_path, in_text, txt_text, expected):
        in_file = tmp_path / "reqs.in"
        in_file.write_text(in_text, encoding="utf-8")
        if txt_text is not None:
            in_file.with_suffix(".txt").write_text(txt_text, encoding="utf-8")
        assert launch_deps_compile.needs_private_index(in_file) is expected

    @pytest.mark.parametrize(
        ("in_text", "expect_index"), [("ultraliser\n", True), ("numpy\n", False)]
    )
    def test_extra_index_for(self, tmp_path, monkeypatch, in_text, expect_index):
        monkeypatch.setenv("UV_INDEX_OBI_CODEARTIFACT_PASSWORD", "secret")
        in_file = tmp_path / "reqs.in"
        in_file.write_text(in_text, encoding="utf-8")
        assert (launch_deps_compile.extra_index_for(in_file) is not None) is expect_index

    @pytest.mark.parametrize("extra_index", ["https://index.example/simple/", None])
    def test_index_passed_to_uv(self, tmp_path, monkeypatch, extra_index):
        in_file = tmp_path / "reqs.in"
        in_file.write_text("numpy\n", encoding="utf-8")
        commands = []

        def fake_run(cmd, **_):
            commands.append(cmd)
            Path(cmd[cmd.index("--output-file") + 1]).write_text("", encoding="utf-8")

        monkeypatch.setattr(launch_deps_compile.subprocess, "run", fake_run)
        launch_deps_compile.compile_in_file(in_file, extra_index=extra_index)
        assert ("--extra-index-url" in commands[0]) is (extra_index is not None)


class TestCompileInFile:
    @pytest.mark.parametrize(
        ("obi_one_pin", "expected_line"),
        [("2026.9.15", "obi-one[emodel]==2026.9.15"), (None, "obi-one[emodel]")],
    )
    def test_obi_one_line_written_with_pin(self, tmp_path, monkeypatch, obi_one_pin, expected_line):
        in_file = tmp_path / "reqs.in"
        in_file.write_text("obi-one[emodel]\n", encoding="utf-8")

        def fake_run(cmd, **_):
            Path(cmd[cmd.index("--output-file") + 1]).write_text("numpy==2.0\n", encoding="utf-8")

        monkeypatch.setattr(launch_deps_compile.subprocess, "run", fake_run)
        content = launch_deps_compile.compile_in_file(in_file, obi_one_pin=obi_one_pin)
        body = [line for line in content.splitlines() if not line.startswith("#")]
        assert body == [expected_line, "numpy==2.0"]
