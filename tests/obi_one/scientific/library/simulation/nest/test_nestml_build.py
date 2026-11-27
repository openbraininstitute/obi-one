"""Unit tests for the NESTML build (no compiler)."""

import subprocess  # ruff: ignore[suspicious-subprocess-import]
from pathlib import Path
from types import SimpleNamespace

import pytest

from obi_one.scientific.library.simulation.nest import nestml_build as nb

pytestmark = pytest.mark.usefixtures("nest_prefix")


@pytest.fixture
def nest_prefix(monkeypatch, tmp_path):
    (tmp_path / "prefix").mkdir()
    nest = SimpleNamespace(build_info={"prefix": str(tmp_path / "prefix")})
    monkeypatch.setattr(nb, "nest", nest)


def test_compile_returns_module_and_reuses_it(monkeypatch, tmp_path):
    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        Path(kwargs["install_path"], "nestml_x_module.so").write_bytes(b"")

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

    monkeypatch.setattr(nb, "generate_nest_target", failing_generate)
    source = tmp_path / "model.nestml"
    source.write_text("")

    with pytest.raises(nb.NestmlBuildError, match=r"failed to generate/compile 'model\.nestml'"):
        nb.compile_nestml_module(source, tmp_path / "out", "nestml_x_module")


@pytest.fixture
def wheel(nest_prefix, monkeypatch, tmp_path):  # ruff: ignore[unused-function-argument]
    """A PyPI-wheel NEST: the build prefix is gone, and its nest-config echoes its arguments."""
    env = tmp_path / "wheel env"
    (env / "bin").mkdir(parents=True)
    wheel_config = env / "bin" / "nest-config"
    wheel_config.write_text('#!/bin/sh\necho "wheel $@"\n')
    wheel_config.chmod(0o755)
    package = tmp_path / "site-packages" / "nest"
    package.mkdir(parents=True)
    nest = SimpleNamespace(
        build_info={"prefix": str(tmp_path / "gone")}, __file__=str(package / "__init__.py")
    )
    monkeypatch.setattr(nb, "nest", nest)
    monkeypatch.setattr(nb.sys, "prefix", str(env))
    monkeypatch.delenv("CXX", raising=False)
    return SimpleNamespace(package=package)


def nest_config(prefix: Path, *options: str) -> str:
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [str(prefix / "bin" / "nest-config"), *options], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def test_an_existing_prefix_is_used_as_it_is(tmp_path):
    assert nb.nest_prefix(tmp_path / "out") == tmp_path / "prefix"
    assert not (tmp_path / "out").exists()


@pytest.mark.usefixtures("wheel")
def test_a_missing_prefix_gets_a_wrapper_next_to_the_build_output(tmp_path):
    prefix = nb.nest_prefix(tmp_path / "out")

    assert prefix == tmp_path / "out" / "nest_prefix"
    assert (prefix / "bin" / "nest-config").stat().st_mode & 0o111


def test_the_wrapper_sets_the_compiler_includes_and_libs(wheel, tmp_path, monkeypatch):
    prefix = nb.nest_prefix(tmp_path / "out")

    assert nest_config(prefix, "--compiler") == "c++"
    monkeypatch.setenv("CXX", "clang++")
    assert nest_config(prefix, "--compiler") == "clang++"
    assert nest_config(prefix, "--includes") == f"-I{wheel.package / 'include' / 'nest'}"
    assert not nest_config(prefix, "--libs")


@pytest.mark.usefixtures("wheel")
def test_the_wrapper_adds_the_old_string_abi_to_the_wheel_cflags(tmp_path):
    prefix = nb.nest_prefix(tmp_path / "out")

    assert nest_config(prefix, "--cflags") == "wheel --cflags -D_GLIBCXX_USE_CXX11_ABI=0"


@pytest.mark.usefixtures("wheel")
def test_the_wrapper_passes_other_options_to_the_wheel(tmp_path):
    prefix = nb.nest_prefix(tmp_path / "out")

    assert nest_config(prefix, "--version") == "wheel --version"
    assert nest_config(prefix, "--static-libraries") == "wheel --static-libraries"


def test_the_wrapper_survives_spaces_in_paths(wheel, tmp_path):
    prefix = nb.nest_prefix(tmp_path / "out dir")

    assert nest_config(prefix, "--includes") == f"-I{wheel.package / 'include' / 'nest'}"
    assert nest_config(prefix, "--version") == "wheel --version"


@pytest.mark.usefixtures("wheel")
def test_compile_builds_against_the_wrapper_when_the_prefix_is_missing(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(nb, "generate_nest_target", lambda **kwargs: calls.append(kwargs))
    source = tmp_path / "model.nestml"
    source.write_text("")

    nb.compile_nestml_module(source, tmp_path / "out", "nestml_x_module")

    assert calls[0]["codegen_opts"] == {"nest_path": str(tmp_path / "out" / "nest_prefix")}
