import h5py
import numpy as np
import pytest

from obi_one.scientific.tasks.em_synapse_mapping.util import merge_spiny_morphologies


def _create_spiny_h5(path, morph_name, *, with_meshes=True, spine_keys=None):
    """Create a minimal morphology-with-spines HDF5 file."""
    with h5py.File(path, "w") as f:
        f.create_dataset(f"morphology/{morph_name}/points", data=np.array([[0, 0, 0]]))
        f.create_dataset(f"edges/{morph_name}/data", data=np.array([1, 2]))
        if with_meshes:
            f.create_dataset(f"soma/meshes/{morph_name}/vertices", data=np.array([[1, 2, 3]]))
        for sk in spine_keys or []:
            f.create_dataset(f"spines/skeletons/{sk}/pts", data=np.array([[0, 1, 2]]))
            if with_meshes:
                f.create_dataset(f"spines/meshes/{sk}/verts", data=np.array([[3, 4, 5]]))


class TestMergeSpinyMorphologies:
    def test_merge_two_files(self, tmp_path):
        f1 = tmp_path / "a.h5"
        f2 = tmp_path / "b.h5"
        _create_spiny_h5(f1, "neuron_A", spine_keys=["spine_1"])
        _create_spiny_h5(f2, "neuron_B", spine_keys=["spine_2"])

        out = tmp_path / "merged.h5"
        merge_spiny_morphologies([f1, f2], out)

        with h5py.File(out, "r") as h5:
            assert "neuron_A" in h5["morphology"]
            assert "neuron_B" in h5["morphology"]
            assert "spine_1" in h5["spines/skeletons"]
            assert "spine_2" in h5["spines/skeletons"]
            assert "neuron_A" in h5["soma/meshes"]
            assert "neuron_B" in h5["soma/meshes"]

    def test_merge_without_meshes(self, tmp_path):
        f1 = tmp_path / "a.h5"
        f2 = tmp_path / "b.h5"
        _create_spiny_h5(f1, "neuron_A", spine_keys=["spine_1"])
        _create_spiny_h5(f2, "neuron_B", spine_keys=["spine_2"])

        out = tmp_path / "merged.h5"
        merge_spiny_morphologies([f1, f2], out, include_meshes=False)

        with h5py.File(out, "r") as h5:
            assert "neuron_A" in h5["morphology"]
            assert "neuron_B" in h5["morphology"]
            assert "soma" not in h5
            assert "meshes" not in h5.get("spines", {})

    def test_duplicate_morphology_key_raises(self, tmp_path):
        f1 = tmp_path / "a.h5"
        f2 = tmp_path / "b.h5"
        _create_spiny_h5(f1, "same_name")
        _create_spiny_h5(f2, "same_name")

        out = tmp_path / "merged.h5"
        with pytest.raises(ValueError, match="Duplicate morphology key"):
            merge_spiny_morphologies([f1, f2], out)

    def test_duplicate_spine_key_raises(self, tmp_path):
        f1 = tmp_path / "a.h5"
        f2 = tmp_path / "b.h5"
        _create_spiny_h5(f1, "neuron_A", spine_keys=["shared_spine"])
        _create_spiny_h5(f2, "neuron_B", spine_keys=["shared_spine"])

        out = tmp_path / "merged.h5"
        with pytest.raises(ValueError, match="Duplicate spine key"):
            merge_spiny_morphologies([f1, f2], out)

    def test_missing_morphology_group_raises(self, tmp_path):
        f1 = tmp_path / "bad.h5"
        with h5py.File(f1, "w") as f:
            f.create_dataset("other/data", data=[1])

        out = tmp_path / "merged.h5"
        with pytest.raises(ValueError, match="No /morphology group"):
            merge_spiny_morphologies([f1], out)

    def test_edges_metadata_copied(self, tmp_path):
        f1 = tmp_path / "a.h5"
        with h5py.File(f1, "w") as f:
            f.create_dataset("morphology/n1/points", data=np.array([[0, 0, 0]]))
            f.create_dataset("edges/n1/data", data=np.array([1]))
            f.create_dataset("edges/n1/metadata/info", data=np.array([42]))

        out = tmp_path / "merged.h5"
        merge_spiny_morphologies([f1], out, include_meshes=False)

        with h5py.File(out, "r") as h5:
            assert "metadata" in h5["edges/n1"]
            assert h5["edges/n1/metadata/info"][0] == 42
