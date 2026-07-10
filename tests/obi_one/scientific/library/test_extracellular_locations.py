import json

import matplotlib.pyplot as plt
import pytest

import obi_one as obi
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.extracellular_locations import (
    extracellular_locations_block_dictionary_summary,
    extracellular_locations_block_summary,
    plot_extracellular_arrays,
)

from tests.utils import CIRCUIT_DIR

_PLACED = {
    "origin_x": 3900.0,
    "origin_y": -1600.0,
    "origin_z": -2400.0,
    "rotation_x": 15.0,
    "rotation_z": 30.0,
}


class TestBlockSummary:
    def test_keys_are_locations_plus_all_properties(self):
        block = obi.LinearExtracellularLocations(n_electrodes=4, spacing=20.0, **_PLACED)
        summary = extracellular_locations_block_summary(block)
        assert set(summary) == {"locations", *block.model_dump()}
        assert summary["type"] == "LinearExtracellularLocations"
        assert summary["n_electrodes"] == 4
        assert summary["spacing"] == pytest.approx(20.0)

    def test_locations_are_world_coordinates(self):
        block = obi.LinearExtracellularLocations(n_electrodes=4, spacing=20.0, **_PLACED)
        summary = extracellular_locations_block_summary(block)
        assert summary["locations"] == [
            list(xyz) for xyz in block.get_global_electrode_xyz_locations()
        ]
        assert len(summary["locations"]) == 4
        assert all(len(position) == 3 for position in summary["locations"])

    def test_json_serialisable(self):
        block = obi.Neuropixels1ExtracellularLocations(n_electrodes=96, **_PLACED)
        # Round-trips through JSON without error (used as an entitycore asset / endpoint body).
        json.loads(json.dumps(extracellular_locations_block_summary(block)))

    def test_properties_vary_by_block_type(self):
        linear = extracellular_locations_block_summary(obi.LinearExtracellularLocations())
        neuropixels = extracellular_locations_block_summary(
            obi.Neuropixels1ExtracellularLocations()
        )
        grid = extracellular_locations_block_summary(obi.GridExtracellularLocations())
        assert "spacing" in linear
        assert "grid_rows" not in linear
        assert "n_electrodes" in neuropixels
        assert "spacing" not in neuropixels
        # a 1-D line aims via rotation_x/z; only planar arrays add the roll (rotation_y).
        assert {"rotation_x", "rotation_z"} <= set(linear)
        assert "rotation_y" not in linear
        assert {"rotation_x", "rotation_y", "rotation_z"} <= set(neuropixels)
        assert {"grid_rows", "grid_columns", "x_offset", "y_offset"} <= set(grid)


class TestBlockDictionarySummary:
    def test_keys_match_input_and_values_are_block_summaries(self):
        blocks = {
            "Lin": obi.LinearExtracellularLocations(n_electrodes=3, spacing=10.0, **_PLACED),
            "Grid": obi.GridExtracellularLocations(grid_rows=2, grid_columns=2, **_PLACED),
        }
        summary = extracellular_locations_block_dictionary_summary(blocks)
        assert list(summary) == ["Lin", "Grid"]
        for name, block in blocks.items():
            assert summary[name] == extracellular_locations_block_summary(block)

    def test_empty_dict(self):
        assert extracellular_locations_block_dictionary_summary({}) == {}


class TestPlotExtracellularArrays:
    @pytest.fixture
    def sonata_circuit(self):
        return Circuit(
            name="tiny",
            path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
        ).sonata_circuit

    def test_returns_figure_with_a_panel_per_array(self, sonata_circuit):
        blocks = {
            "Lin": obi.LinearExtracellularLocations(n_electrodes=4, spacing=50.0, **_PLACED),
            "Grid": obi.GridExtracellularLocations(grid_rows=3, grid_columns=3, **_PLACED),
        }
        figure = plot_extracellular_arrays(sonata_circuit, blocks)
        # three axis-plane projections + one 3D view + one local panel per array.
        assert len(figure.axes) == 3 + 1 + len(blocks)
        plt.close(figure)
