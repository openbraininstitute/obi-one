"""Unit tests for the NESTML build toolchain (no network, no compiler)."""

import subprocess  # ruff: ignore[suspicious-subprocess-import]  (runs the generated shim)
from pathlib import Path

import pytest

from obi_one.scientific.library.simulation.nest import nestml_build as nb


def _fake_kernel(tmp_path: Path, symbol: bytes) -> Path:
    package_dir = tmp_path / "nest"
    (package_dir / "include" / "nest").mkdir(parents=True)
    (package_dir / "nestkernel_api.so").write_bytes(b"\x7fELF...." + symbol + b"\x00")
    return package_dir


def test_detects_old_cxx_abi(tmp_path):
    package_dir = _fake_kernel(tmp_path, nb.OLD_ABI_SYMBOL)
    assert nb.uses_old_cxx_abi(package_dir / "nestkernel_api.so")


def test_detects_new_cxx_abi(tmp_path):
    package_dir = _fake_kernel(tmp_path, nb.NEW_ABI_SYMBOL + b"1112basic_string")
    assert not nb.uses_old_cxx_abi(package_dir / "nestkernel_api.so")


def test_missing_kernel_is_not_old_abi(tmp_path):
    assert not nb.uses_old_cxx_abi(tmp_path / "missing.so")


def test_shim_options_for_wheel(tmp_path):
    package_dir = _fake_kernel(tmp_path, nb.OLD_ABI_SYMBOL)
    install = nb.NestInstall(package_dir=package_dir, prefix=None, nest_config=None)
    extra = tmp_path / "boost"
    options = nb.build_shim_options(install, [extra])
    assert not options["--libs"]
    assert f"-I{package_dir / 'include' / 'nest'}" in options["--includes"]
    assert f"-I{extra}" in options["--includes"]
    assert options["--cflags"].endswith(nb.OLD_ABI_FLAG)
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


def test_boost_include_from_env(monkeypatch, tmp_path):
    (tmp_path / "boost").mkdir()
    (tmp_path / "boost" / "type_index.hpp").write_text("")
    monkeypatch.setenv("NESTML_BOOST_INCLUDE", str(tmp_path))
    assert nb.boost_include_dir() == tmp_path


def test_invalid_env_include_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("NESTML_GSL_INCLUDE", str(tmp_path))
    with pytest.raises(nb.NestmlToolchainError, match=r"gsl_errno\.h"):
        nb.gsl_include_dir()


def test_resolve_prefers_working_nest_config(monkeypatch, tmp_path):
    install = nb.NestInstall(
        package_dir=tmp_path, prefix=tmp_path / "prefix", nest_config=tmp_path / "nc"
    )
    monkeypatch.setattr(nb, "find_nest_install", lambda: install)
    assert nb.resolve_nest_path() == tmp_path / "prefix"
