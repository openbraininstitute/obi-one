"""Entry points needing connectivity packages raise ImportError naming the extra."""

import sys

import pytest

from obi_one.scientific.library import circuit as circuit_module
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.find_afferent_synapses import (
    morphology_and_pathdistance_calculator,
)
from obi_one.scientific.library.map_em_synapses.map_synapse_locations import calc_section_offset
from obi_one.scientific.library.morphology_locations import (
    load_optimized_morphology_path_distance_calculator,
)
from obi_one.utils.circuit import run_basic_connectivity_plots

CONNECTIVITY_MODULES = (
    "conntility",
    "conntility.connectivity",
    "conntility.subcellular",
)
HINT = r"requires 'conntility'.*pip install 'obi-one\[connectivity\]'"


@pytest.fixture
def without_connectivity(monkeypatch):
    # A None entry in sys.modules makes `import` raise ImportError.
    for name in CONNECTIVITY_MODULES:
        monkeypatch.setitem(sys.modules, name, None)


@pytest.mark.usefixtures("without_connectivity")
class TestConnectivityInstallHint:
    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(
                lambda: load_optimized_morphology_path_distance_calculator(None),
                id="morphology_locations",
            ),
            pytest.param(
                lambda: morphology_and_pathdistance_calculator(None, "pop", 0),
                id="find_afferent_synapses",
            ),
            pytest.param(lambda: calc_section_offset(None, None), id="map_synapse_locations"),
            pytest.param(
                lambda: run_basic_connectivity_plots(None, "edges", None), id="utils_circuit"
            ),
            pytest.param(
                lambda: (
                    Circuit.model_construct(
                        name="c", path="circuit_config.json", matrix_path="matrix.h5"
                    ).connectivity_matrix
                ),
                id="circuit_connectivity_matrix",
            ),
        ],
    )
    def test_raises_install_hint(self, call):
        with pytest.raises(ImportError, match=HINT):
            call()

    def test_circuit_init_with_matrix_path(self, monkeypatch):
        monkeypatch.setattr(circuit_module.snap, "Circuit", lambda _path: None)
        with pytest.raises(ImportError, match=HINT):
            Circuit(name="c", path="circuit_config.json", matrix_path="matrix.h5")
