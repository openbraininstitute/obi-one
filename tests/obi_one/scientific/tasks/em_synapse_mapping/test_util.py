import h5py
import numpy as np
import pytest

from obi_one.scientific.tasks.em_synapse_mapping.util import merge_spiny_morphologies


def _create_spiny_h5(path, morph_name, *, with_meshes=True, spine_keys=None):
    """Create a minimal but valid morphology-with-spines HDF5 file.

    Creates a file that passes merge_morphologies_with_spines validation:
    - /morphology/{name} with points and structure
    - /edges/{name} with spine_morphology column + metadata
    - /spines/skeletons/{key} for each spine key
    - optionally /soma/meshes/{name} and /spines/meshes/{key}
    """
    spine_keys = spine_keys or [morph_name]
    with h5py.File(path, "w") as f:
        # Morphology skeleton
        f.create_dataset(
            f"morphology/{morph_name}/points",
            data=np.array([[0.0, 0.0, 0.0, 0.5]], dtype=np.float64),
        )
        f.create_dataset(
            f"morphology/{morph_name}/structure",
            data=np.array([[0, 2, -1]], dtype=np.int32),
        )

        # Edges (spine table) - spine_morphology references first spine key
        edges_grp = f.create_group(f"edges/{morph_name}")
        dt = h5py.string_dtype(encoding="utf-8")
        edges_grp.create_dataset(
            "spine_morphology", data=np.array([spine_keys[0]], dtype=object), dtype=dt
        )
        edges_grp.create_dataset("spine_id", data=np.array([0], dtype=np.uint32))
        meta_grp = edges_grp.create_group("metadata")
        meta_grp.attrs["version"] = np.array([1, 0], dtype=np.uint32)

        # Spine skeletons
        for sk in spine_keys:
            f.create_dataset(
                f"spines/skeletons/{sk}/points",
                data=np.array([[0.0, 1.0, 2.0, 0.3]], dtype=np.float64),
            )
            f.create_dataset(
                f"spines/skeletons/{sk}/structure",
                data=np.array([[0, 2, -1]], dtype=np.int32),
            )

        # Meshes (optional)
        if with_meshes:
            f.create_dataset(
                f"soma/meshes/{morph_name}/vertices",
                data=np.array([[1.0, 2.0, 3.0]], dtype=np.float32),
            )
            f.create_dataset(
                f"soma/meshes/{morph_name}/triangles",
                data=np.array([[0, 0, 0]], dtype=np.int32),
            )
            for sk in spine_keys:
                f.create_dataset(
                    f"spines/meshes/{sk}/vertices",
                    data=np.array([[3.0, 4.0, 5.0]], dtype=np.float32),
                )
                f.create_dataset(
                    f"spines/meshes/{sk}/triangles",
                    data=np.array([[0, 0, 0]], dtype=np.int32),
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
        with h5py.File(f1, "w") as f:
            f.create_dataset("morphology/a/points", data=np.array([[0.0, 0.0, 0.0, 0.5]]))
            f.create_dataset("morphology/b/points", data=np.array([[0.0, 0.0, 0.0, 0.5]]))

        out = tmp_path / "merged.h5"
        with pytest.raises(ValueError, match="Expected exactly 1 morphology"):
            merge_spiny_morphologies([(f1, "n1")], out)
