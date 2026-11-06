"""Coverage for map_em_synapses.constants and light helpers that use them."""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

import obi_one.scientific.library.map_em_synapses as map_em_synapses_pkg
import obi_one.scientific.library.map_em_synapses.map_synapse_locations as msl
from obi_one.scientific.library.map_em_synapses import constants
from obi_one.scientific.library.map_em_synapses.constants import (
    C_CAVE_ID_IN,
    C_CAVE_ID_OUT,
    C_CENTER,
    C_P_LOCS,
    C_PSD_ID,
    C_SP_INDEX,
    C_SURFACE,
    DEFAULT_NODE_SPECS,
    MAX_COUNT_LIBRARY,
    PF_AFF,
    STR_POST_NODE,
    STR_PRE_NODE,
    STR_SEC_ID,
    STR_SEC_OFF,
    STR_SEG_ID,
    STR_SEG_OFF,
    SYNAPTOME_SONATA_CONFIG,
    V_COLNAME_DICT,
    V_DTYPE_DICT,
    V_FALLBACK,
    WITH_DIR,
)
from obi_one.scientific.library.map_em_synapses.map_synapse_locations import (
    edges_dataframe_for_shaft_syns,
    edges_dataframe_for_soma_syns,
    edges_dataframe_for_spine_syns,
    estimate_mesh_resolution,
    fill_defaults_for_missing_columns,
    find_nearest_mesh_points,
    map_afferents_to_spiny_morphology,
    map_points_to_segs_df,
    rename_directed_dataframe_colums,
    segment_interpolator,
    synapse_info_df,
)


class TestConstants:
    def test_synapse_location_columns(self):
        assert C_P_LOCS == ["synapse_x", "synapse_y", "synapse_z"]

    def test_with_dir_includes_locations_and_section_ids(self):
        for col in (*C_CENTER, *C_SURFACE, *C_P_LOCS, STR_SEC_ID, STR_SEG_ID, STR_SEG_OFF):
            assert col in WITH_DIR

    def test_sonata_and_node_defaults_are_populated(self):
        assert "networks" in SYNAPTOME_SONATA_CONFIG
        assert "Portion 65 of the IARPA MICrONS dataset" in DEFAULT_NODE_SPECS
        assert MAX_COUNT_LIBRARY == 50
        assert STR_PRE_NODE == "pre_node_id"
        assert STR_POST_NODE == "post_node_id"

    def test_package_init_does_not_reexport(self):
        assert not hasattr(map_em_synapses_pkg, "map_afferents_to_spiny_morphology")
        assert not hasattr(map_em_synapses_pkg, "write_edges")
        assert not hasattr(map_em_synapses_pkg, "write_nodes")
        assert not hasattr(map_em_synapses_pkg, "C_P_LOCS")

    def test_all_module_constants_are_public(self):
        private = [
            name for name in dir(constants) if name.startswith("_") and not name.startswith("__")
        ]
        assert private == []


class TestRenameAndFillDefaults:
    def test_rename_directed_dataframe_colums_prefixes_with_dir_columns(self):
        df = pd.DataFrame(
            {
                C_P_LOCS[0]: [1.0],
                C_CENTER[0]: [2.0],
                "other": [3.0],
            }
        )
        renamed = rename_directed_dataframe_colums(df, prefix=PF_AFF)
        assert PF_AFF + C_P_LOCS[0] in renamed.columns
        assert PF_AFF + C_CENTER[0] in renamed.columns
        assert "other" in renamed.columns

    def test_fill_defaults_uses_dtype_and_fallback(self):
        reference = pd.DataFrame(
            {
                "float_col": pd.Series([1.0], dtype="float64"),
                "int_col": pd.Series([1], dtype="int64"),
                "obj_col": pd.Series(["a"], dtype=object),
            }
        )
        modify = pd.DataFrame({"keep": [0]})
        fill_defaults_for_missing_columns(reference, modify)
        assert modify["float_col"].iloc[0] == V_DTYPE_DICT["float64"]
        assert modify["int_col"].iloc[0] == V_DTYPE_DICT["int64"]
        assert modify["obj_col"].iloc[0] == V_FALLBACK

    def test_fill_defaults_uses_colname_dict_when_present(self):
        V_COLNAME_DICT["named"] = "from_dict"
        try:
            reference = pd.DataFrame({"named": [1]})
            modify = pd.DataFrame({"keep": [0]})
            fill_defaults_for_missing_columns(reference, modify)
            assert modify["named"].iloc[0] == "from_dict"
        finally:
            V_COLNAME_DICT.clear()


class TestMeshAndSegmentHelpers:
    def test_find_nearest_mesh_points(self):
        mesh = pd.DataFrame(
            [[0.0, 0.0, 0.0, 7], [10.0, 0.0, 0.0, 8]],
            columns=["x", "y", "z", "spine_sharing_id"],
        )
        pts = pd.DataFrame([[0.1, 0.0, 0.0], [9.9, 0.0, 0.0]], columns=["x", "y", "z"])
        nearest = find_nearest_mesh_points(mesh, pts)
        assert list(nearest["spine_sharing_id"]) == [7, 8]
        assert (nearest["distance"] >= 0).all()

    def test_map_points_to_segs_df(self):
        segs = pd.DataFrame(
            {
                STR_SEC_ID: [1, 1],
                STR_SEG_ID: [0, 1],
                "start_x": [0.0, 1.0],
                "start_y": [0.0, 0.0],
                "start_z": [0.0, 0.0],
                "start_d": [1.0, 1.0],
                "end_x": [1.0, 2.0],
                "end_y": [0.0, 0.0],
                "end_z": [0.0, 0.0],
                "end_d": [1.0, 1.0],
            }
        )
        pts = pd.DataFrame([[0.5, 0.0, 0.0], [1.5, 0.0, 0.0]], columns=C_P_LOCS)
        mapped = map_points_to_segs_df(segs, pts)
        assert list(mapped[STR_SEC_ID]) == [1, 1]
        assert STR_SEG_OFF in mapped.columns
        assert "distance" in mapped.columns

    def test_segment_interpolator(self):
        start = np.array([0.0, 0.0, 0.0, 1.0])
        end = np.array([2.0, 0.0, 0.0, 1.0])
        center = segment_interpolator((start, end), 0.5)
        assert list(center.index) == C_CENTER
        assert center[C_CENTER[0]] == pytest.approx(0.5)


class TestSynapseInfoDf:
    def test_expands_location_columns_from_cave_query(self):
        client = MagicMock()
        client.materialize.synapse_query.return_value = pd.DataFrame(
            {
                C_CAVE_ID_IN: [11, 12],
                "ctr_pt_position": [
                    np.array([1000.0, 2000.0, 3000.0]),
                    np.array([4000.0, 5000.0, 6000.0]),
                ],
            }
        )
        syns = synapse_info_df(client, pt_root_id=42, resolutions=np.array([1.0, 1.0, 1.0]))
        assert syns[C_P_LOCS[0]].tolist() == pytest.approx([1.0, 4.0])
        assert syns[C_P_LOCS[1]].tolist() == pytest.approx([2.0, 5.0])
        assert syns[C_P_LOCS[2]].tolist() == pytest.approx([3.0, 6.0])
        assert syns.index.name == "synapse_id"
        client.materialize.synapse_query.assert_called_once_with(post_ids=[42])


class TestEdgesDataframes:
    def _syns(self):
        return pd.DataFrame(
            {
                C_CAVE_ID_IN: [101],
                C_P_LOCS[0]: [1.0],
                C_P_LOCS[1]: [2.0],
                C_P_LOCS[2]: [3.0],
            },
            index=[0],
        )

    def test_edges_dataframe_for_soma_syns(self, monkeypatch):
        monkeypatch.setattr(msl, "calc_section_offset", lambda *_a, **_k: np.array([0.0]))
        morph = MagicMock()
        morph.soma.center = [0.5, 0.5, 0.5]
        m = MagicMock()
        m.morphology = morph
        mpd = pd.DataFrame({"distance": [0.1]}, index=[0])
        out = edges_dataframe_for_soma_syns(self._syns(), m, mpd, pd.Series([True]))
        assert PF_AFF + C_P_LOCS[0] in out.columns
        assert PF_AFF + C_SURFACE[0] in out.columns
        assert out[PF_AFF + C_CENTER[0]].iloc[0] == pytest.approx(0.5)

    def test_edges_dataframe_for_shaft_syns(self, monkeypatch):
        monkeypatch.setattr(msl, "calc_section_offset", lambda *_a, **_k: np.array([0.25]))
        monkeypatch.setattr(
            msl,
            "calc_center_positions",
            lambda *_a, **_k: pd.DataFrame(
                {C_CENTER[0]: [0.0], C_CENTER[1]: [0.0], C_CENTER[2]: [0.0]}
            ),
        )
        m = MagicMock()
        mpd = pd.DataFrame(
            {
                STR_SEC_ID: [1],
                STR_SEG_ID: [0],
                STR_SEG_OFF: [0.1],
                "distance": [0.2],
            },
            index=[0],
        )
        out = edges_dataframe_for_shaft_syns(self._syns(), m, mpd, pd.Series([True]))
        assert PF_AFF + C_P_LOCS[0] in out.columns
        assert out[PF_AFF + STR_SEC_OFF].iloc[0] == pytest.approx(0.25)

    def test_edges_dataframe_for_spine_syns(self):
        spine_table = pd.DataFrame(
            {
                "spine_orientation_vector_x": [0.0],
                "spine_orientation_vector_y": [0.0],
                "spine_orientation_vector_z": [0.0],
                "spine_rotation_x": [0.0],
                "spine_rotation_y": [0.0],
                "spine_rotation_z": [0.0],
                "spine_rotation_w": [1.0],
                "keep": [9],
            },
            index=[3],
        )
        m = MagicMock()
        m.spines.spine_table = spine_table
        mpd = pd.DataFrame({C_SP_INDEX: [3], "distance": [0.05]}, index=[0])
        out = edges_dataframe_for_spine_syns(self._syns(), m, mpd, pd.Series([True]))
        assert out[PF_AFF + C_P_LOCS[0]].iloc[0] == pytest.approx(1.0)
        assert out[C_CAVE_ID_OUT].iloc[0] == 101
        assert out[C_PSD_ID].iloc[0] == 0

    def test_map_afferents_routes_by_distance_and_quality(self, monkeypatch):
        syns = self._syns()
        spine_pts = pd.DataFrame(
            {"x": [0.0], "y": [0.0], "z": [0.0], C_SP_INDEX: [1]},
        )
        mpd_nrt = pd.DataFrame(
            {STR_SEC_ID: [1], STR_SEG_ID: [0], STR_SEG_OFF: [0.0], "distance": [2.0]},
            index=syns.index,
        )
        mpd_spn = pd.DataFrame({C_SP_INDEX: [-1], "distance": [0.5]}, index=syns.index)
        empty = pd.DataFrame(index=syns.index)

        monkeypatch.setattr(msl, "morph_to_segs_df", lambda _m: pd.DataFrame())
        monkeypatch.setattr(msl, "morph_to_spine_and_soma_df", lambda _m: spine_pts)
        monkeypatch.setattr(msl, "map_points_to_segs_df", lambda _segs, pts: mpd_nrt.loc[pts.index])
        monkeypatch.setattr(
            msl, "find_nearest_mesh_points", lambda _mesh, pts: mpd_spn.loc[pts.index]
        )
        monkeypatch.setattr(msl, "edges_dataframe_for_soma_syns", lambda *_a, **_k: empty.copy())
        monkeypatch.setattr(msl, "edges_dataframe_for_shaft_syns", lambda *_a, **_k: empty.copy())
        monkeypatch.setattr(msl, "edges_dataframe_for_spine_syns", lambda *_a, **_k: empty.copy())
        monkeypatch.setattr(msl, "fill_defaults_for_missing_columns", lambda *_a, **_k: None)

        def _competing(_mesh, pts):
            return pd.Series([0.4], index=pts.index)

        monkeypatch.setattr(msl, "add_competing_mesh_distances", _competing)
        monkeypatch.setattr(msl, "estimate_mesh_resolution", lambda _mesh: 0.12)

        mapped, resolution = map_afferents_to_spiny_morphology(
            MagicMock(), syns, add_quality_info=True
        )
        assert "competing_distance" in mapped.columns
        assert resolution == pytest.approx(0.12)

        mapped_plain, resolution_plain = map_afferents_to_spiny_morphology(MagicMock(), syns)
        assert resolution_plain is None
        assert "competing_distance" not in mapped_plain.columns

    def test_estimate_mesh_resolution(self):
        mesh = pd.DataFrame(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            columns=["x", "y", "z"],
        )
        assert estimate_mesh_resolution(mesh) > 0
