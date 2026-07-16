"""Integration test for ensure_mechanisms_compiled (requires nrnivmodl + neurodamus)."""

import json
import os
import shutil
from pathlib import Path

import pytest

from obi_one.utils.circuit import ensure_mechanisms_compiled

# Find the real nrnivmodl (not the venv shim which may be broken)
_nrnivmodl_path = os.environ.get("NRNIVMODL_PATH") or shutil.which("nrnivmodl")


def _nrnivmodl_works() -> bool:
    """Check if nrnivmodl is actually functional (not just a broken shim)."""
    if not _nrnivmodl_path:
        return False
    import subprocess  # noqa: PLC0415, S404

    try:
        result = subprocess.run(  # noqa: S603
            [_nrnivmodl_path, "--help"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    else:
        return result.returncode == 0


pytestmark = pytest.mark.skipif(
    not _nrnivmodl_works(),
    reason="Requires a functional nrnivmodl (set NRNIVMODL_PATH if needed)",
)

# A trivial .mod file that compiles without external dependencies.
_TRIVIAL_MOD = """\
NEURON {
    SUFFIX trivial_test_mech
    RANGE x
}

PARAMETER {
    x = 0
}
"""


@pytest.fixture
def mock_circuit_config(tmp_path):
    """Create a minimal circuit config with a trivial .mod file."""
    mods_dir = tmp_path / "mechanisms"
    mods_dir.mkdir()
    (mods_dir / "trivial.mod").write_text(_TRIVIAL_MOD)

    morphologies_dir = tmp_path / "morphologies"
    morphologies_dir.mkdir()

    nodes_file = tmp_path / "nodes.h5"
    nodes_file.touch()

    config = {
        "networks": {
            "nodes": [
                {
                    "nodes_file": str(nodes_file),
                    "populations": {
                        "test_pop": {
                            "type": "biophysical",
                            "mechanisms_dir": str(mods_dir),
                            "morphologies_dir": str(morphologies_dir),
                            "biophysical_neuron_models_dir": str(tmp_path / "hoc"),
                        }
                    },
                }
            ],
            "edges": [],
        }
    }

    config_path = tmp_path / "circuit_config.json"
    config_path.write_text(json.dumps(config))
    return config_path


def test_compiles_and_produces_library(mock_circuit_config, tmp_path):
    """Compile a trivial mod file and verify the library file exists."""
    cache_dir = tmp_path / "compiled_mods"

    result = ensure_mechanisms_compiled(
        mock_circuit_config, cache_dir, nrnivmodl_path=_nrnivmodl_path
    )

    assert result == os.environ["NRNMECH_LIB_PATH"]
    assert Path(result).exists()
    assert Path(result).suffix in {".dylib", ".so"}


def test_second_call_uses_cache(mock_circuit_config, tmp_path):
    """Second call with same mods should hit cache (no recompilation)."""
    cache_dir = tmp_path / "compiled_mods"

    result1 = ensure_mechanisms_compiled(
        mock_circuit_config, cache_dir, nrnivmodl_path=_nrnivmodl_path
    )
    result2 = ensure_mechanisms_compiled(
        mock_circuit_config, cache_dir, nrnivmodl_path=_nrnivmodl_path
    )

    assert result1 == result2
