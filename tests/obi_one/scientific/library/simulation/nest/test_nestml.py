"""Tests for NESTML custom-model support: real host builds against the installed NEST."""

import math
import shutil
from pathlib import Path

import nest
import pytest

from obi_one.scientific.library.simulation.nest import simulate_nest
from obi_one.scientific.library.simulation.nest.simulate_nest import (
    NestmlBuildError,
    NestSonataNetwork,
)

from tests.obi_one.scientific.library.simulation.nest._circuits import (
    write_nestml_circuit as _write_nestml_circuit,
)

needs_toolchain = pytest.mark.skipif(
    not (shutil.which("cmake") and shutil.which("make") and shutil.which("c++")),
    reason="cmake, make and a C++ compiler are needed to compile NESTML models",
)


def _create(config_path: Path) -> dict:
    net = NestSonataNetwork(config_path)
    try:
        return net.Create()
    except NestmlBuildError as exc:
        if str(exc).startswith("Could not prepare the NESTML build environment"):
            pytest.skip(str(exc))
        raise


def test_nestml_source_resolution_and_cache_key(tmp_path):
    """The loader resolves the .nestml source without compiling."""
    config_path = _write_nestml_circuit(tmp_path, "iaf_toy_neuron")
    net = NestSonataNetwork(config_path)
    meta = net.node_populations["toy"]
    assert meta["model_template_dir"] == tmp_path / "model_templates" / "toy"
    assert net.load_template("toy", "iaf_toy_neuron")["model"] == "nestml:iaf_toy_neuron"
    source = net._nestml_source_path("iaf_toy_neuron", meta["model_template_dir"])
    assert source.name == "iaf_toy_neuron.nestml"


@needs_toolchain
def test_nestml_generate_install_and_cache(tmp_path, monkeypatch):
    """Compile, install and create a NESTML neuron; a second network reuses the module."""
    monkeypatch.setattr(simulate_nest, "BUILT_NESTML_MODULES", {})
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


@needs_toolchain
def test_nestml_threshold_and_reset(tmp_path):
    """The compiled linear model spikes and resets when started above threshold."""
    toy = _create(_write_nestml_circuit(tmp_path, "iaf_toy_neuron"))["toy"]
    toy.set({"V_m": -50.0, "V_th": -55.0})
    recorder = nest.Create("spike_recorder")
    nest.Connect(toy, recorder)
    nest.Simulate(5.0)
    assert recorder.get("n_events") == 1
    assert toy.get("V_m") == pytest.approx(-70.0)


@needs_toolchain
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
