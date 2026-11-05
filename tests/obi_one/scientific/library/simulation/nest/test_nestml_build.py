"""Unit tests for the NESTML build toolchain (no network, no compiler)."""

import subprocess  # ruff: ignore[suspicious-subprocess-import]  (runs the generated shim)
from pathlib import Path

import pytest

from obi_one.scientific.library.simulation.nest import nestml_build as nb


def _fake_package_dir(tmp_path: Path) -> Path:
    package_dir = tmp_path / "nest"
    (package_dir / "include" / "nest").mkdir(parents=True)
    return package_dir


def test_shim_options_for_wheel(tmp_path):
    package_dir = _fake_package_dir(tmp_path)
    install = nb.NestInstall(package_dir=package_dir, prefix=None, nest_config=None)
    options = nb.build_shim_options(install)
    assert not options["--libs"]
    assert options["--includes"] == f"-I{package_dir / 'include' / 'nest'}"
    assert options["--cflags"] == "-O2 -std=c++20"
    assert options["--static-libraries"] == "OFF"


def test_shim_script_answers_and_rejects(tmp_path):
    prefix = nb.write_nest_config_shim(
        tmp_path / "shim", {"--libs": "", "--includes": "-I/a -I/b c", "--version": "3.10.0"}
    )
    script = prefix / "bin" / "nest-config"

    def run(*args):
        return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [str(script), *args], capture_output=True, text=True, check=False
        )

    assert run("--prefix").stdout.strip() == str(prefix)
    assert run("--includes").stdout.strip() == "-I/a -I/b c"
    assert not run("--libs").stdout.strip()
    assert run("--version").stdout.strip() == "3.10.0"
    assert run("--bogus").returncode != 0


def test_cache_root_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OBI_NESTML_CACHE", str(tmp_path / "c"))
    assert nb.cache_root() == tmp_path / "c"


def test_resolve_prefers_working_nest_config(monkeypatch, tmp_path):
    install = nb.NestInstall(
        package_dir=tmp_path, prefix=tmp_path / "prefix", nest_config=tmp_path / "nc"
    )
    monkeypatch.setattr(nb, "find_nest_install", lambda: install)
    assert nb.resolve_nest_path() == tmp_path / "prefix"


def test_compile_returns_module_and_reuses_it(monkeypatch, tmp_path):
    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        Path(kwargs["install_path"], "nestml_x_module.so").write_bytes(b"")

    monkeypatch.setattr(nb, "resolve_nest_path", lambda: tmp_path / "prefix")
    monkeypatch.setattr(nb, "generate_nest_target", fake_generate)
    source = tmp_path / "model.nestml"
    source.write_text("")

    library = nb.compile_nestml_module(source, tmp_path / "out", "nestml_x_module")
    again = nb.compile_nestml_module(source, tmp_path / "out", "nestml_x_module")

    assert library == tmp_path / "out" / "nestml_x_module.so"
    assert again == library
    assert len(calls) == 1
    assert calls[0]["codegen_opts"] == {"nest_path": str(tmp_path / "prefix")}


def test_compile_wraps_generator_failure(monkeypatch, tmp_path):
    def failing_generate(**_kwargs):
        msg = "cmake failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(nb, "resolve_nest_path", lambda: tmp_path / "prefix")
    monkeypatch.setattr(nb, "generate_nest_target", failing_generate)
    source = tmp_path / "model.nestml"
    source.write_text("")

    with pytest.raises(nb.NestmlBuildError, match=r"failed to generate/compile 'model\.nestml'"):
        nb.compile_nestml_module(source, tmp_path / "out", "nestml_x_module")


def test_compile_wraps_toolchain_failure(monkeypatch, tmp_path):
    def no_toolchain():
        msg = "nest-config missing"
        raise nb.NestmlToolchainError(msg)

    monkeypatch.setattr(nb, "resolve_nest_path", no_toolchain)
    source = tmp_path / "model.nestml"
    source.write_text("")

    with pytest.raises(nb.NestmlBuildError, match="Could not prepare the NESTML build environment"):
        nb.compile_nestml_module(source, tmp_path / "out", "nestml_x_module")
