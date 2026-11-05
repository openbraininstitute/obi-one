"""Unit tests for the NESTML build (no compiler)."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from obi_one.scientific.library.simulation.nest import nestml_build as nb

pytestmark = pytest.mark.usefixtures("nest_prefix")


@pytest.fixture
def nest_prefix(monkeypatch, tmp_path):
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
