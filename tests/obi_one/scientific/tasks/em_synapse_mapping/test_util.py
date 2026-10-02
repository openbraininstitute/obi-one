import h5py
import numpy as np
import pytest

from obi_one.scientific.tasks.em_synapse_mapping.util import merge_spiny_morphologies


def _create_spiny_h5(path, morph_name, *, with_meshes=True, spine_keys=None):
    """Create a fully valid morphology-with-spines HDF5 file.

    Produces a file that passes the morph-spines validator (structural checks):
    - /morphology/{name} with points (N,4) float32 and structure (M,3) int32
    - /edges/{name} with all mandatory columns + metadata group with version=(1,0)
    - /spines/skeletons/{key} with points and structure
    - optionally /soma/meshes/{name} and /spines/meshes/{key} (with offsets)
    """
    spine_keys = spine_keys or [morph_name]
    n_spines = 2

    with h5py.File(path, "w") as f:
        # --- /morphology/{name} ---
        morph_grp = f.create_group(f"morphology/{morph_name}")
        morph_grp.create_dataset(
            "points",
            data=np.array(
                [[0.0, 0.0, 0.0, 0.5], [1.0, 0.0, 0.0, 0.4], [2.0, 0.0, 0.0, 0.3]],
                dtype=np.float32,
            ),
        )
        morph_grp.create_dataset("structure", data=np.array([[0, 2, -1]], dtype=np.int32))

        # --- /edges/{name} with all mandatory columns ---
        edges_grp = f.create_group(f"edges/{morph_name}")
        meta = edges_grp.create_group("metadata")
        meta.attrs["version"] = np.array([1, 0], dtype=np.uint32)

        dt_str = h5py.string_dtype(encoding="utf-8")
        edges_grp.create_dataset(
            "spine_morphology",
            data=np.array([spine_keys[0]] * n_spines, dtype=object),
            dtype=dt_str,
        )
        edges_grp.create_dataset("spine_id", data=np.arange(n_spines, dtype=np.uint32))
        edges_grp.create_dataset("spine_length", data=np.ones(n_spines, dtype=np.float64))
        edges_grp.create_dataset(
            "spine_orientation_vector_x", data=np.zeros(n_spines, dtype=np.float64)
        )
        edges_grp.create_dataset(
            "spine_orientation_vector_y", data=np.zeros(n_spines, dtype=np.float64)
        )
        edges_grp.create_dataset(
            "spine_orientation_vector_z", data=np.ones(n_spines, dtype=np.float64)
        )
        edges_grp.create_dataset("spine_rotation_x", data=np.zeros(n_spines, dtype=np.float64))
        edges_grp.create_dataset("spine_rotation_y", data=np.zeros(n_spines, dtype=np.float64))
        edges_grp.create_dataset("spine_rotation_z", data=np.zeros(n_spines, dtype=np.float64))
        edges_grp.create_dataset("spine_rotation_w", data=np.ones(n_spines, dtype=np.float64))
        edges_grp.create_dataset("afferent_surface_x", data=np.zeros(n_spines, dtype=np.float64))
        edges_grp.create_dataset("afferent_surface_y", data=np.zeros(n_spines, dtype=np.float64))
        edges_grp.create_dataset("afferent_surface_z", data=np.zeros(n_spines, dtype=np.float64))
        edges_grp.create_dataset("afferent_center_x", data=np.zeros(n_spines, dtype=np.float64))
        edges_grp.create_dataset("afferent_center_y", data=np.zeros(n_spines, dtype=np.float64))
        edges_grp.create_dataset("afferent_center_z", data=np.zeros(n_spines, dtype=np.float64))
        edges_grp.create_dataset("afferent_section_id", data=np.ones(n_spines, dtype=np.uint32))
        edges_grp.create_dataset("afferent_segment_id", data=np.zeros(n_spines, dtype=np.int32))
        edges_grp.create_dataset(
            "afferent_segment_offset", data=np.zeros(n_spines, dtype=np.float64)
        )
        edges_grp.create_dataset("afferent_section_pos", data=np.zeros(n_spines, dtype=np.float64))

        # --- /spines/skeletons/{key} ---
        for sk in spine_keys:
            sk_grp = f.create_group(f"spines/skeletons/{sk}")
            sk_grp.create_dataset(
                "points",
                data=np.array([[0.0, 0.0, 0.0, 0.3], [1.0, 0.0, 0.0, 0.2]], dtype=np.float32),
            )
            sk_grp.create_dataset("structure", data=np.array([[0, 2, -1]], dtype=np.int32))

        # --- /soma/meshes/{name} (optional) ---
        if with_meshes:
            soma_grp = f.create_group(f"soma/meshes/{morph_name}")
            soma_grp.create_dataset(
                "vertices",
                data=np.array(
                    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32
                ),
            )
            soma_grp.create_dataset("triangles", data=np.array([[0, 1, 2]], dtype=np.int32))

        # --- /spines/meshes/{key} (optional, with offsets) ---
        if with_meshes:
            for sk in spine_keys:
                sm_grp = f.create_group(f"spines/meshes/{sk}")
                # 2 spines, 3 vertices each, 1 triangle each
                sm_grp.create_dataset(
                    "vertices",
                    data=np.array(
                        [
                            [0.0, 0.0, 0.0],
                            [1.0, 0.0, 0.0],
                            [0.0, 1.0, 0.0],
                            [2.0, 0.0, 0.0],
                            [3.0, 0.0, 0.0],
                            [2.0, 1.0, 0.0],
                        ],
                        dtype=np.float32,
                    ),
                )
                sm_grp.create_dataset(
                    "triangles", data=np.array([[0, 1, 2], [0, 1, 2]], dtype=np.int32)
                )
                # offsets: (n_spines+1, 2) -> vertex_offset, triangle_offset
                sm_grp.create_dataset(
                    "offsets", data=np.array([[0, 0], [3, 1], [6, 2]], dtype=np.int32)
                )


class TestMergeSpinyMorphologies:
    def test_merge_two_files(self, tmp_path):
        f1 = tmp_path / "a.h5"
        f2 = tmp_path / "b.h5"
        n1 = "1234"
        n2 = "5678"
        _create_spiny_h5(f1, "neuron_A", spine_keys=["spine_1"])
        _create_spiny_h5(f2, "neuron_B", spine_keys=["spine_2"])

        out = tmp_path / "merged.h5"
        merge_spiny_morphologies([(f1, n1), (f2, n2)], out)

        with h5py.File(out, "r") as h5:
            assert n1 in h5["morphology"]
            assert n2 in h5["morphology"]
            assert "spine_1" in h5["spines/skeletons"]
            assert "spine_2" in h5["spines/skeletons"]
            assert n1 in h5["soma/meshes"]
            assert n2 in h5["soma/meshes"]

    def test_merge_without_meshes(self, tmp_path):
        f1 = tmp_path / "a.h5"
        f2 = tmp_path / "b.h5"
        n1 = "1234"
        n2 = "5678"
        _create_spiny_h5(f1, "neuron_A", spine_keys=["spine_1"])
        _create_spiny_h5(f2, "neuron_B", spine_keys=["spine_2"])

        out = tmp_path / "merged.h5"
        merge_spiny_morphologies([(f1, n1), (f2, n2)], out, include_meshes=False)

        with h5py.File(out, "r") as h5:
            assert n1 in h5["morphology"]
            assert n2 in h5["morphology"]
            assert "soma" not in h5
            assert "meshes" not in h5.get("spines", {})

    def test_duplicate_morphology_destination_raises(self, tmp_path):
        f1 = tmp_path / "a.h5"
        f2 = tmp_path / "b.h5"
        _create_spiny_h5(f1, "neuron_A")
        _create_spiny_h5(f2, "neuron_B")

        out = tmp_path / "merged.h5"
        with pytest.raises(ValueError, match="Duplicate morphology destination name"):
            merge_spiny_morphologies([(f1, "same"), (f2, "same")], out)

    def test_duplicate_spine_key_raises(self, tmp_path):
        f1 = tmp_path / "a.h5"
        f2 = tmp_path / "b.h5"
        n1 = "1234"
        n2 = "5678"
        _create_spiny_h5(f1, "neuron_A", spine_keys=["shared_spine"])
        _create_spiny_h5(f2, "neuron_B", spine_keys=["shared_spine"])

        out = tmp_path / "merged.h5"
        with pytest.raises(ValueError, match="Duplicate spines library destination name"):
            merge_spiny_morphologies([(f1, n1), (f2, n2)], out)

    def test_missing_morphology_group_raises(self, tmp_path):
        f1 = tmp_path / "bad.h5"
        with h5py.File(f1, "w") as f:
            f.create_dataset("other/data", data=[1])

        out = tmp_path / "merged.h5"
        with pytest.raises(ValueError, match="No /morphology group"):
            merge_spiny_morphologies([(f1, "n1")], out)

    def test_edges_metadata_copied(self, tmp_path):
        f1 = tmp_path / "a.h5"
        _create_spiny_h5(f1, "orig", with_meshes=False)

        out = tmp_path / "merged.h5"
        merge_spiny_morphologies([(f1, "n1")], out, include_meshes=False)

        with h5py.File(out, "r") as h5:
            assert "metadata" in h5["edges/n1"]
            assert list(h5["edges/n1/metadata"].attrs["version"]) == [1, 0]

    def test_multi_morph_file_raises(self, tmp_path):
        """A file with more than one morphology is rejected."""
        f1 = tmp_path / "multi.h5"
        # Create file with two morphologies (invalid for this wrapper)
        _create_spiny_h5(f1, "first")
        with h5py.File(f1, "a") as f:
            # Add a second morphology group
            morph_grp = f.create_group("morphology/second")
            morph_grp.create_dataset(
                "points", data=np.array([[0.0, 0.0, 0.0, 0.5]], dtype=np.float32)
            )
            morph_grp.create_dataset("structure", data=np.array([[0, 2, -1]], dtype=np.int32))

        out = tmp_path / "merged.h5"
        with pytest.raises(ValueError, match="Expected exactly 1 morphology"):
            merge_spiny_morphologies([(f1, "n1")], out)
