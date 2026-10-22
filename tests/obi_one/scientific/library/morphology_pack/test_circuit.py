from dataclasses import replace
from pathlib import Path

import h5py
import libsonata
import morphio
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from obi_one.scientific.library.morphology_pack.circuit import (
    Population,
    distinct_morphologies,
    morphology_files,
    place_cells,
    read_morphology,
    read_population,
    rotation_matrices,
)
from obi_one.scientific.library.morphology_pack.codec import GRID_UM
from obi_one.scientific.library.morphology_pack.geometry import FINEST, simplified
from obi_one.scientific.library.morphology_pack.reader import read_pack

from tests.utils import CIRCUIT_DIR

CONTAINER_CIRCUIT = CIRCUIT_DIR / "N_10__top_nodes_dim6"
CONTAINER = CONTAINER_CIRCUIT / "morphologies/merged-morphologies.h5"
FOLDER_CIRCUIT = CIRCUIT_DIR / "nbS1-O1-E2Sst-maxNsyn-HEX0-L5"
FOLDER = FOLDER_CIRCUIT / "morphologies/swc"
POPULATION = "S1nonbarrel_neurons"


def population_of(circuit, morphologies_path, morphology_format):
    config = libsonata.CircuitConfig.from_file(str(circuit / "circuit_config.json"))
    return read_population(config, POPULATION, morphologies_path, morphology_format)


def shapes_of(*populations):
    return {
        key: simplified(read_morphology(key, collection), [FINEST])
        for key, collection in distinct_morphologies(populations)
    }


def pack_of(*populations):
    return read_pack(place_cells(populations, [FINEST], shapes_of(*populations)).pack())


def read_alone(name, morphologies_path, morphology_format):
    population = Population(
        "cells", np.zeros((1, 3)), np.eye(3)[None], [name], morphologies_path, morphology_format
    )
    ((key, collection),) = distinct_morphologies([population])
    return read_morphology(key, collection)


def attributes_of(circuit, *names):
    nodes = libsonata.NodeStorage(str(circuit / POPULATION / "nodes.h5"))
    population = nodes.open_population(POPULATION)
    return [population.get_attribute(name, population.select_all()) for name in names]


class TestPack:
    def test_a_container_of_morphologies(self):
        population = population_of(CONTAINER_CIRCUIT, CONTAINER, "h5")
        pack = pack_of(population)
        assert [(entry.name, entry.cells) for entry in pack.index.populations] == [(POPULATION, 10)]
        assert set(pack.levels[0].cells) == set(range(10))
        assert len(pack.levels[0].segments) > 10_000

    def test_a_folder_of_morphologies(self):
        population = population_of(FOLDER_CIRCUIT, FOLDER, "swc")
        pack = pack_of(population)
        assert set(pack.levels[0].cells) == set(range(len(population.morphologies)))

    def test_somas_are_where_the_nodes_are(self):
        pack = pack_of(population_of(CONTAINER_CIRCUIT, CONTAINER, "h5"))
        positions = np.column_stack(attributes_of(CONTAINER_CIRCUIT, "x", "y", "z"))
        np.testing.assert_allclose(pack.somas[:, :3], positions, atol=1e-3)
        assert (pack.somas[:, 3] > 1).all()

    def test_every_cell_is_turned_as_its_node_says(self):
        level = pack_of(population_of(CONTAINER_CIRCUIT, CONTAINER, "h5")).levels[0]
        positions = np.column_stack(attributes_of(CONTAINER_CIRCUIT, "x", "y", "z"))
        quaternions = np.column_stack(
            attributes_of(CONTAINER_CIRCUIT, *(f"orientation_{axis}" for axis in "xyzw"))
        )
        (names,) = attributes_of(CONTAINER_CIRCUIT, "morphology")
        collection = morphio.Collection(str(CONTAINER))
        for cell, name in enumerate(names):
            # the last point of a section is kept at every level
            tip = collection.load(name).sections[0].points[-1].astype(np.float64)
            placed = Rotation.from_quat(quaternions[cell]).as_matrix() @ tip + positions[cell]
            ends = level.segments[level.cells == cell, 4:7]
            assert np.abs(ends - placed).max(axis=1).min() <= GRID_UM / 2 + 1e-6

    def test_a_neurite_starts_at_its_soma(self):
        pack = pack_of(population_of(CONTAINER_CIRCUIT, CONTAINER, "h5"))
        level = pack.levels[0]
        for cell, soma in enumerate(pack.somas):
            starts = level.segments[level.cells == cell, :3]
            assert np.abs(starts - soma[:3]).max(axis=1).min() <= GRID_UM / 2 + 1e-3

    def test_cells_are_numbered_through_the_populations(self):
        first = population_of(CONTAINER_CIRCUIT, CONTAINER, "h5")
        second = replace(first, name="second", positions=first.positions + 5000.0)
        assert len(list(distinct_morphologies([first, second]))) == len(set(first.morphologies))
        pack = pack_of(first, second)
        assert [entry.name for entry in pack.index.populations] == [POPULATION, "second"]
        assert set(pack.levels[0].cells) == set(range(20))
        np.testing.assert_allclose(pack.somas[10:, :3], pack.somas[:10, :3] + 5000.0, atol=1e-3)

    def test_a_cell_without_a_shape_is_a_soma_alone(self):
        population = population_of(FOLDER_CIRCUIT, FOLDER, "swc")
        shapes = shapes_of(population)
        del shapes[population.morphology_keys()[0]]
        pack = read_pack(place_cells([population], [FINEST], shapes).pack())
        assert 0 not in set(pack.levels[0].cells)
        assert pack.somas[0, 3] == 0
        assert pack.somas[0, :3].any()
        assert pack.somas[1, 3] > 0

    def test_a_cell_with_no_finite_place_is_a_soma_alone(self):
        whole = population_of(CONTAINER_CIRCUIT, CONTAINER, "h5")
        positions, rotations = whole.positions.copy(), whole.rotations.copy()
        positions[0, 0] = np.nan
        rotations[1] = np.nan
        population = replace(whole, positions=positions, rotations=rotations)
        pack = read_pack(place_cells([population], [FINEST], shapes_of(population)).pack())
        level = pack.levels[0]
        assert set(level.cells) == set(range(2, 10))
        ends = level.segments.reshape(-1, 4)[:, :3]
        np.testing.assert_allclose(
            np.array(pack.index.bounds) * GRID_UM,
            [ends.min(axis=0), ends.max(axis=0)],
            atol=GRID_UM,
        )
        np.testing.assert_allclose(pack.somas[1, :3], whole.positions[1], atol=1e-3)
        assert pack.somas[1, 3] == 0


class TestMorphologies:
    def test_a_file_that_is_not_a_morphology_raises(self, tmp_path):
        (tmp_path / "bad.swc").write_text("not a morphology")
        with pytest.raises(morphio.MorphioError):
            read_alone("bad", tmp_path, "swc")

    def test_a_name_the_container_does_not_hold_raises(self):
        with pytest.raises(RuntimeError, match="absent"):
            read_alone("absent", CONTAINER, "h5")

    @pytest.mark.parametrize(
        ("path", "morphology_format", "files"),
        [
            ("morphologies/merged.h5", "h5", ["morphologies/merged.h5"]),
            ("morphologies/h5.v1", "h5", ["morphologies/h5.v1/a.h5", "morphologies/h5.v1/b.h5"]),
            ("morphologies.v2", "swc", ["morphologies.v2/a.swc", "morphologies.v2/b.swc"]),
        ],
    )
    def test_the_files_of_a_container_or_a_folder(self, path, morphology_format, files):
        assert morphology_files(Path(path), morphology_format, ["b", "a", "b"]) == [
            Path(file) for file in files
        ]


def population_with(tmp_path, attributes):
    with h5py.File(tmp_path / "nodes.h5", "w") as file:
        population = file.create_group("nodes/All")
        population.create_dataset("node_type_id", data=[-1, -1])
        group = population.create_group("0")
        for name, values in attributes.items():
            group.create_dataset(name, data=values)
    return libsonata.NodeStorage(str(tmp_path / "nodes.h5")).open_population("All")


class TestRotations:
    def test_quaternions(self, tmp_path):
        turns = Rotation.from_euler("xyz", [[0.3, -1.1, 2.0], [0.0, 0.0, np.pi / 2]])
        x, y, z, w = turns.as_quat().T
        population = population_with(
            tmp_path,
            {"orientation_w": w, "orientation_x": x, "orientation_y": y, "orientation_z": z},
        )
        np.testing.assert_allclose(rotation_matrices(population), turns.as_matrix(), atol=1e-12)

    def test_angles_about_the_axes(self, tmp_path):
        population = population_with(
            tmp_path,
            {"rotation_angle_yaxis": [0.4, 0.0], "rotation_angle_zaxis": [0.0, np.pi / 2]},
        )
        expected = Rotation.from_euler("y", 0.4), Rotation.from_euler("z", np.pi / 2)
        np.testing.assert_allclose(
            rotation_matrices(population), [turn.as_matrix() for turn in expected], atol=1e-12
        )

    def test_no_turn_where_the_nodes_give_none(self, tmp_path):
        population = population_with(tmp_path, {"x": [0.0, 1.0]})
        np.testing.assert_allclose(rotation_matrices(population), [np.eye(3)] * 2)
