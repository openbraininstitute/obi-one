"""Tests for building and writing SONATA node files for EM synapse mapping.

Covers ``obi_one/scientific/library/map_em_synapses/write_sonata_nodes_file.py``.
The functions that reach out to the EM dataset / entitysdk ``Client`` are exercised
with a ``MagicMock`` standing in for ``neuron_info_df`` so no network access is needed;
everything else uses real ``pandas`` / ``voxcell`` / ``h5py`` objects.
"""

from unittest.mock import MagicMock

import h5py
import numpy as np
import pandas as pd
import pytest
from voxcell import CellCollection

import obi_one.scientific.library.map_em_synapses.write_sonata_nodes_file as nodes_mod
from obi_one.scientific.library.map_em_synapses.constants import MAX_COUNT_LIBRARY
from obi_one.scientific.library.map_em_synapses.write_sonata_nodes_file import (
    assemble_collection_from_specs,
    get_specified_tables,
    resolve_position_to_xyz,
    write_nodes,
    write_virtual_nodes,
)


def _position_spec(resolution=None):
    if resolution is None:
        resolution = {"x": 1.0, "y": 1.0, "z": 1.0}
    return {"table": "tbl", "column": "pt_position", "resolution": resolution}


def _make_em_dataset(table_data):
    """Return a mock EM dataset whose ``neuron_info_df`` serves ``table_data`` per table name."""
    em = MagicMock()

    def _neuron_info_df(tbl_name, _cave_version, db_client=None):  # ruff: ignore[unused-function-argument]
        return table_data[tbl_name], f"notice:{tbl_name}"

    em.neuron_info_df.side_effect = _neuron_info_df
    return em


class TestResolvePositionToXyz:
    def test_scales_each_axis_by_its_resolution(self):
        func = resolve_position_to_xyz({"x": 2.0, "y": 3.0, "z": 4.0})
        result = func([10, 20, 30])
        assert isinstance(result, pd.Series)
        assert result["x"] == pytest.approx(20.0)
        assert result["y"] == pytest.approx(60.0)
        assert result["z"] == pytest.approx(120.0)
        assert list(result.index) == ["x", "y", "z"]

    def test_non_iterable_input_yields_sentinel(self):
        # A scalar NaN (what reindex produces for a missing position) is not iterable.
        func = resolve_position_to_xyz({"x": 2.0, "y": 3.0, "z": 4.0})
        result = func(np.nan)
        assert list(result) == [-1, -1, -1]
        assert list(result.index) == ["x", "y", "z"]


class TestGetSpecifiedTables:
    def test_collects_unique_tables_and_notices(self):
        specs = {
            "a": {"table": "t1", "column": "c1", "default": 0},
            "b": {"table": "t1", "column": "c2", "default": 0},  # duplicate table
            "c": {"table": "t2", "column": "c3", "default": 0},
            "d": {"table": None, "default": "x"},  # no table -> skipped
        }
        df1 = pd.DataFrame({"c1": [1]})
        df2 = pd.DataFrame({"c3": [2]})
        em = _make_em_dataset({"t1": df1, "t2": df2})

        tables, notices = get_specified_tables(em, MagicMock(), 783, specs)

        assert set(tables) == {"t1", "t2"}
        # Each unique table is queried exactly once (t1 only once despite two refs).
        assert em.neuron_info_df.call_count == 2
        assert notices == ["notice:t1", "notice:t2"]

    def test_no_tables_returns_empty(self):
        specs = {"only_default": {"table": None, "default": 1}}
        em = _make_em_dataset({})
        tables, notices = get_specified_tables(em, MagicMock(), 1, specs)
        assert tables == {}
        assert notices == []
        em.neuron_info_df.assert_not_called()


class TestAssembleCollectionFromSpecs:
    @pytest.fixture
    def specs(self):
        return {
            "synapse_class": {
                "table": "tbl",
                "column": "classification_system",
                "default": "extrinsic",
            },
            "mtype": {"table": "tbl", "column": "cell_type", "default": "extrinsic"},
            "status_axon": {"table": "tbl", "column": "status_axon", "default": False},
            "layer": {"table": None, "default": "N/A"},
            "__position": _position_spec({"x": 2.0, "y": 3.0, "z": 4.0}),
        }

    @pytest.fixture
    def table(self):
        return pd.DataFrame(
            {
                "classification_system": ["intrinsic", "intrinsic"],
                "cell_type": ["L5", "L6"],
                "status_axon": [True, np.nan],
                "pt_position": [[1, 2, 3], [4, 5, 6]],
            },
            index=pd.Index([100, 200], name="pre_pt_root_id"),
        )

    def test_builds_cell_collection_with_expected_rows(self, specs, table):
        em = _make_em_dataset({"tbl": table})
        # 300 is not present in the table -> should fall back to defaults.
        pt_root_mapping = pd.DataFrame(index=pd.Index([100, 200, 300], name="pre_pt_root_id"))

        collection, notices = assemble_collection_from_specs(
            em, MagicMock(), 783, specs, pt_root_mapping
        )

        assert isinstance(collection, CellCollection)
        assert notices == ["notice:tbl"]
        props = collection.properties.reset_index(drop=True)
        assert len(props) == 3
        # pt_root_id column is renamed from the index.
        assert list(props["pt_root_id"]) == [100, 200, 300]
        assert list(props["synapse_class"]) == ["intrinsic", "intrinsic", "extrinsic"]
        assert list(props["mtype"]) == ["L5", "L6", "extrinsic"]
        # Constant (table=None) columns use the default everywhere.
        assert list(props["layer"]) == ["N/A", "N/A", "N/A"]

    def test_missing_values_use_defaults_and_bool_becomes_string(self, specs, table):
        em = _make_em_dataset({"tbl": table})
        pt_root_mapping = pd.DataFrame(index=pd.Index([100, 200, 300], name="pre_pt_root_id"))

        collection, _ = assemble_collection_from_specs(em, MagicMock(), 783, specs, pt_root_mapping)
        props = collection.properties.reset_index(drop=True)
        # Boolean columns are stringified so SONATA can store them.
        assert props["status_axon"].dtype == object
        # Row 100 True, row 200 NaN->default False, row 300 absent->default False.
        assert list(props["status_axon"]) == ["True", "False", "False"]

    def test_positions_scaled_by_resolution_with_sentinel_for_missing(self, specs, table):
        em = _make_em_dataset({"tbl": table})
        pt_root_mapping = pd.DataFrame(index=pd.Index([100, 200, 300], name="pre_pt_root_id"))

        collection, _ = assemble_collection_from_specs(em, MagicMock(), 783, specs, pt_root_mapping)
        positions = collection.positions
        # [1,2,3] * [2,3,4] = [2,6,12]; [4,5,6] * [2,3,4] = [8,15,24].
        np.testing.assert_allclose(positions[0], [2.0, 6.0, 12.0])
        np.testing.assert_allclose(positions[1], [8.0, 15.0, 24.0])
        # Row 300 has no position -> sentinel of -1 on every axis.
        np.testing.assert_allclose(positions[2], [-1.0, -1.0, -1.0])


class TestWriteNodes:
    def _collection(self):
        df = pd.DataFrame(
            {
                "pt_root_id": [10, 20, 30],
                "mtype": ["L5", "L5", "L6"],
                "x": [1.0, 2.0, 3.0],
                "y": [4.0, 5.0, 6.0],
                "z": [7.0, 8.0, 9.0],
            }
        )
        df.index = pd.Index(range(1, len(df) + 1))
        return CellCollection.from_dataframe(df)

    def test_writes_population_that_round_trips(self, tmp_path):
        out = tmp_path / "nodes.h5"
        write_nodes(out, "my_population", self._collection())

        assert out.exists()
        reloaded = CellCollection.load_sonata(str(out))
        assert reloaded.population_name == "my_population"
        assert list(reloaded.properties["mtype"]) == ["L5", "L5", "L6"]
        with h5py.File(out) as h5:
            assert "nodes/my_population" in h5

    def test_override_library_enables_enum_for_low_cardinality_strings(self, tmp_path):
        out = tmp_path / "nodes.h5"
        write_nodes(out, "pop", self._collection(), override_library=True)

        # With the library forced on, repeated low-cardinality string columns such as
        # ``mtype`` are stored via a @library enum group rather than inline per node.
        with h5py.File(out) as h5:
            library = h5.get("nodes/pop/0/@library")
            assert library is not None
            assert "mtype" in library

    def test_write_mode_append_adds_second_population(self, tmp_path):
        out = tmp_path / "nodes.h5"
        write_nodes(out, "first", self._collection(), write_mode="w")
        write_nodes(out, "second", self._collection(), write_mode="a")

        with h5py.File(out) as h5:
            assert "nodes/first" in h5
            assert "nodes/second" in h5

    def test_max_count_library_threshold_constant(self):
        # Guards the documented cardinality threshold used for forced libraries.
        assert MAX_COUNT_LIBRARY == 50


class TestWriteVirtualNodes:
    def test_writes_property_free_virtual_population(self, tmp_path):
        out = tmp_path / "virtual.h5"
        write_virtual_nodes(out, "virtual_pop", count=5)

        assert out.exists()
        with h5py.File(out) as h5:
            group = h5["nodes/virtual_pop"]
            assert group["node_type_id"].shape == (5,)
            np.testing.assert_array_equal(group["node_type_id"][:], -np.ones(5, dtype=np.int64))
            np.testing.assert_array_equal(group["node_group_id"][:], np.zeros(5, dtype=np.int64))
            np.testing.assert_array_equal(group["node_group_index"][:], np.arange(5))
            model_type = group["0/model_type"][:]
            decoded = [v.decode() if isinstance(v, bytes) else v for v in model_type]
            assert decoded == ["virtual"] * 5

    def test_creates_missing_parent_directories(self, tmp_path):
        out = tmp_path / "nested" / "deeper" / "virtual.h5"
        write_virtual_nodes(out, "virtual_pop", count=2)
        assert out.exists()

    @pytest.mark.parametrize("count", [0, -1, -10])
    def test_non_positive_count_raises(self, tmp_path, count):
        out = tmp_path / "virtual.h5"
        with pytest.raises(ValueError, match="count must be positive"):
            write_virtual_nodes(out, "virtual_pop", count=count)
        assert not out.exists()

    def test_accepts_string_path(self, tmp_path):
        out = tmp_path / "virtual.h5"
        write_virtual_nodes(str(out), "virtual_pop", count=3)
        with h5py.File(out) as h5:
            assert h5["nodes/virtual_pop/node_type_id"].shape == (3,)


def test_module_exposes_expected_public_callables():
    # Sanity check that the symbols under test are the ones the package re-exports.
    assert callable(nodes_mod.write_nodes)
    assert callable(nodes_mod.write_virtual_nodes)
    assert callable(nodes_mod.assemble_collection_from_specs)
