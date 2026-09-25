"""Tests for the launch-script dependency compiler.

These cover the helper logic that does not invoke ``uv pip compile`` (which needs
the network / CodeArtifact auth and is exercised by the ``check-launch-deps`` CI
job instead). ``compile_launch_deps`` is a standalone script under
``launch_scripts/`` and is importable here via the ``pythonpath`` pytest setting.
"""

import compile_launch_deps
import pytest


class TestResolveInFiles:
    def test_default_discovers_all_launch_in_files(self):
        # No paths -> every launch-script .in under the real repo tree.
        result = compile_launch_deps.resolve_in_files([])
        assert result  # there is at least one .in file in the repo
        assert all(p.suffix == ".in" for p in result)
        assert result == sorted(result)  # sorted, de-duplicated

    def test_single_in_file(self, tmp_path):
        f = tmp_path / "reqs.in"
        f.write_text("obi-one\n", encoding="utf-8")
        assert compile_launch_deps.resolve_in_files([str(f)]) == [f.resolve()]

    def test_directory_is_searched_recursively(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "one.in").write_text("obi-one\n", encoding="utf-8")
        (tmp_path / "two.in").write_text("obi-one\n", encoding="utf-8")
        (tmp_path / "ignored.txt").write_text("x\n", encoding="utf-8")
        result = compile_launch_deps.resolve_in_files([str(tmp_path)])
        assert result == sorted(
            [(tmp_path / "a" / "one.in").resolve(), (tmp_path / "two.in").resolve()]
        )

    def test_multiple_paths_are_unioned_and_deduplicated(self, tmp_path):
        f1 = tmp_path / "one.in"
        f1.write_text("obi-one\n", encoding="utf-8")
        f2 = tmp_path / "two.in"
        f2.write_text("obi-one\n", encoding="utf-8")
        # f1 given both directly and via the directory -> de-duplicated.
        result = compile_launch_deps.resolve_in_files([str(f1), str(tmp_path)])
        assert result == sorted([f1.resolve(), f2.resolve()])

    def test_nonexistent_path_raises(self, tmp_path):
        with pytest.raises(SystemExit, match=r"Not an \.in file or directory"):
            compile_launch_deps.resolve_in_files([str(tmp_path / "missing.in")])

    def test_non_in_file_raises(self, tmp_path):
        f = tmp_path / "reqs.txt"
        f.write_text("x\n", encoding="utf-8")
        with pytest.raises(SystemExit, match=r"Not an \.in file or directory"):
            compile_launch_deps.resolve_in_files([str(f)])


class TestCheckInTxtPairing:
    def _deps_dir(self, tmp_path):
        d = tmp_path / "launch_x" / "dependencies"
        d.mkdir(parents=True)
        return d

    def test_paired_files_ok(self, tmp_path, monkeypatch):
        d = self._deps_dir(tmp_path)
        (d / "default.in").write_text("obi-one\n", encoding="utf-8")
        (d / "default.txt").write_text("obi-one\n", encoding="utf-8")
        monkeypatch.setattr(compile_launch_deps, "REPO_ROOT", tmp_path)
        assert compile_launch_deps.check_in_txt_pairing([d / "default.in"]) is False

    def test_orphan_txt_detected(self, tmp_path, monkeypatch, capsys):
        d = self._deps_dir(tmp_path)
        (d / "default.in").write_text("obi-one\n", encoding="utf-8")
        (d / "default.txt").write_text("obi-one\n", encoding="utf-8")
        (d / "orphan.txt").write_text("x\n", encoding="utf-8")  # no .in
        monkeypatch.setattr(compile_launch_deps, "REPO_ROOT", tmp_path)
        assert compile_launch_deps.check_in_txt_pairing([d / "default.in"]) is True
        assert "MISSING .in" in capsys.readouterr().err

    def test_missing_txt_detected(self, tmp_path, monkeypatch, capsys):
        d = self._deps_dir(tmp_path)
        (d / "default.in").write_text("obi-one\n", encoding="utf-8")  # no .txt
        monkeypatch.setattr(compile_launch_deps, "REPO_ROOT", tmp_path)
        assert compile_launch_deps.check_in_txt_pairing([d / "default.in"]) is True
        assert "MISSING .txt" in capsys.readouterr().err


class TestBuildResolveInput:
    def test_obi_one_line_rewritten_to_local_project(self, tmp_path):
        f = tmp_path / "reqs.in"
        f.write_text("obi-one[connectivity]\nnumpy\n", encoding="utf-8")
        resolved, obi_one_lines = compile_launch_deps._build_resolve_input(f)
        # The obi-one line is preserved verbatim for the output header...
        assert obi_one_lines == ["obi-one[connectivity]"]
        # ...and rewritten to the local project path (with extras) for resolution.
        repo = compile_launch_deps.REPO_ROOT.as_posix()
        resolved_lines = resolved.splitlines()
        assert f"{repo}[connectivity]" in resolved_lines
        assert "numpy" in resolved_lines
        # No bare "obi-one[...]" requirement line remains (the repo dir may itself
        # be named "obi-one", so compare whole lines, not substrings).
        assert "obi-one[connectivity]" not in resolved_lines

    def test_no_obi_one_passthrough(self, tmp_path):
        f = tmp_path / "reqs.in"
        f.write_text("# comment\nnumpy==2.0\n\n", encoding="utf-8")
        resolved, obi_one_lines = compile_launch_deps._build_resolve_input(f)
        assert obi_one_lines == []
        assert "numpy==2.0" in resolved
        assert "# comment" in resolved


class TestExistingPins:
    def test_missing_file_returns_empty(self, tmp_path):
        assert not compile_launch_deps._existing_pins(tmp_path / "nope.txt")

    def test_strips_header_comments_and_obi_one(self, tmp_path):
        f = tmp_path / "out.txt"
        f.write_text(
            "# autogenerated header\nobi-one[connectivity]\nnumpy==2.4.6\npandas==2.3.3\n",
            encoding="utf-8",
        )
        pins = compile_launch_deps._existing_pins(f)
        assert pins == "numpy==2.4.6\npandas==2.3.3\n"
        assert "obi-one" not in pins
        assert "#" not in pins


class TestPythonFloorVersion:
    def test_parses_requires_python_lower_bound(self):
        # Reads the real pyproject; must return a dotted version >= 3.12.
        version = compile_launch_deps._python_floor_version()
        assert version.startswith("3.12")
