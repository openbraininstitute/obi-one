"""Tests for NESTML custom-model support: real host builds against the installed NEST."""

import math
from pathlib import Path
from types import SimpleNamespace

import nest
import pytest

from obi_one.scientific.library.simulation.nest import nestml_build, simulate_nest
from obi_one.scientific.library.simulation.nest.simulate_nest import NestSonataNetwork

from tests.obi_one.scientific.library.simulation.nest._circuits import (
    write_nestml_circuit as _write_nestml_circuit,
)


def _create(config_path: Path) -> dict:
    return NestSonataNetwork(config_path).Create()


def _generated_sources(cache_dir: Path) -> str:
    files = [p for p in cache_dir.rglob("*") if p.suffix in {".h", ".cpp"}]
    assert files, f"no generated C++ sources under {cache_dir}"
    return "\n".join(p.read_text() for p in files)


def test_nestml_source_resolution_and_cache_key(tmp_path):
    """The loader resolves the .nestml source without compiling."""
    config_path = _write_nestml_circuit(tmp_path, "iaf_toy_neuron")
    net = NestSonataNetwork(config_path)
    meta = net.node_populations["toy"]
    assert meta["point_neuron_models_dir"] == tmp_path / "model_templates" / "toy"
    assert net.load_template("toy", "iaf_toy_neuron")["model"] == "nestml:iaf_toy_neuron"
    source = net._nestml_source_path("iaf_toy_neuron", meta["point_neuron_models_dir"])
    assert source.name == "iaf_toy_neuron.nestml"


def test_nestml_generate_install_and_cache(tmp_path):
    """Compile, install and create a NESTML neuron; a second network reuses the module."""
    config_path = _write_nestml_circuit(tmp_path, "iaf_toy_neuron")
    toy = _create(config_path)["toy"]
    assert len(toy) == 1
    assert toy.get("model") == "iaf_toy_neuron"
    assert "iaf_toy_neuron" in nest.node_models

    built = list((tmp_path / ".nestml_cache").glob("*/nestml_*module.so"))
    assert len(built) == 1
    mtime = built[0].stat().st_mtime

    again = _create(config_path)["toy"]
    assert len(again) == 1
    assert built[0].stat().st_mtime == mtime


def test_nestml_model_without_ode_generates_no_gsl(tmp_path):
    """A model without equations builds without GSL, so its generated code never includes GSL."""
    _create(_write_nestml_circuit(tmp_path, "threshold_toy_neuron"))
    assert "<gsl/" not in _generated_sources(tmp_path / ".nestml_cache")


def test_nestml_analytic_ode_model_generates_no_gsl(tmp_path):
    """A linear ODE is solved analytically by NESTML, so it needs no GSL either."""
    _create(_write_nestml_circuit(tmp_path, "iaf_toy_neuron"))
    assert "<gsl/" not in _generated_sources(tmp_path / ".nestml_cache")


def test_nestml_numeric_ode_model_generates_gsl(tmp_path):
    """ODEs without an analytic solution are integrated with GSL, so the model needs its headers."""
    _create(_write_nestml_circuit(tmp_path, "adex_toy_neuron"))
    assert "<gsl/gsl_odeiv.h>" in _generated_sources(tmp_path / ".nestml_cache")


def test_nestml_threshold_and_reset(tmp_path):
    """The compiled linear model spikes and resets when started above threshold."""
    toy = _create(_write_nestml_circuit(tmp_path, "iaf_toy_neuron"))["toy"]
    toy.set({"V_m": -50.0, "V_th": -55.0})
    recorder = nest.Create("spike_recorder")
    nest.Connect(toy, recorder)
    nest.Simulate(5.0)
    assert recorder.get("n_events") == 1
    assert toy.get("V_m") == pytest.approx(-70.0)


def test_nestml_gsl_model_matches_reference(tmp_path):
    """A GSL-integrated AdEx model compiles and spikes once, at 14.2 ms.

    14.2 ms is the spike time of the same model compiled by NESTML against a source-built NEST 3.10.
    """
    adex = _create(_write_nestml_circuit(tmp_path, "adex_toy_neuron"))["toy"]
    recorder = nest.Create("spike_recorder")
    nest.Connect(adex, recorder)
    nest.Simulate(500.0)
    times = list(recorder.get("events")["times"])
    assert times == [pytest.approx(14.2)]
    assert math.isfinite(adex.get("V_m"))


def test_nestml_model_is_compiled_into_cache_and_installed(tmp_path, monkeypatch):
    """The loader compiles the source into a hash-keyed cache directory and installs the result."""
    calls = {}

    def fake_compile(source, output_dir, module_name):
        calls["compile"] = (source, output_dir, module_name)
        return output_dir / f"{module_name}.so"

    def fake_install(path):
        calls["install"] = path

    monkeypatch.setattr(nestml_build, "compile_nestml_module", fake_compile)
    fake_nest = SimpleNamespace(
        node_models=nest.node_models,
        synapse_models=nest.synapse_models,
        Install=fake_install,
    )
    monkeypatch.setattr(simulate_nest, "nest", fake_nest)
    config_path = _write_nestml_circuit(tmp_path, "iaf_toy_neuron")
    net = NestSonataNetwork(config_path)
    model_dir = net.node_populations["toy"]["point_neuron_models_dir"]

    name = net._ensure_nestml_model("iaf_toy_neuron", model_dir)

    source, output_dir, module_name = calls["compile"]
    assert source == model_dir / "iaf_toy_neuron.nestml"
    assert output_dir.parent == tmp_path / ".nestml_cache"
    assert module_name.startswith("nestml_")
    assert module_name.endswith("module")
    assert calls["install"] == str(output_dir / f"{module_name}.so")
    assert name == "iaf_toy_neuron"
