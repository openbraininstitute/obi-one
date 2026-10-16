"""From a SONATA circuit to a pack: its populations, their morphologies, and every cell placed."""

import logging
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import libsonata
import morphio
import numpy as np
from bluepysnap.utils import euler2mat, quaternion2mat

from obi_one.scientific.library.morphology_pack.geometry import Level, Morphology, MorphologyLevels
from obi_one.scientific.library.morphology_pack.writer import PackWriter

L = logging.getLogger(__name__)

QUATERNION = ("orientation_w", "orientation_x", "orientation_y", "orientation_z")
ANGLES = ("rotation_angle_zaxis", "rotation_angle_yaxis", "rotation_angle_xaxis")

# What tells a morphology from any other, of its population or another: where it is read from,
# and its name.
type MorphologyKey = tuple[Path, str]


@dataclass(frozen=True)
class Population:
    """A population of cells with morphologies: where they are, how they are turned, their shapes.

    `morphologies` names each cell's morphology. They are read from `morphologies_path`: a
    folder of files of `morphology_format`, or a container.
    """

    name: str
    positions: np.ndarray
    rotations: np.ndarray
    morphologies: list[str]
    morphologies_path: Path
    morphology_format: str

    def morphology_keys(self) -> list[MorphologyKey]:
        """The key of each cell's morphology."""
        return [(self.morphologies_path, name) for name in self.morphologies]

    def placeable(self) -> np.ndarray:
        """Which cells have a position and a rotation of finite numbers."""
        placed = np.column_stack([self.positions, self.rotations.reshape(-1, 9)])
        return np.all(np.isfinite(placed), axis=1)


def rotation_matrices(population: libsonata.NodePopulation) -> np.ndarray:
    """A 3 by 3 matrix a cell, from quaternions or else from angles; no turn where neither."""
    everyone = population.select_all()
    attributes = population.attribute_names
    if set(QUATERNION) <= attributes:
        return np.asarray(
            quaternion2mat(*(population.get_attribute(name, everyone) for name in QUATERNION))
        )
    angles = [
        population.get_attribute(name, everyone)
        if name in attributes
        else np.zeros(population.size)
        for name in ANGLES
    ]
    return np.asarray(euler2mat(*angles))


def read_population(
    config: libsonata.CircuitConfig, name: str, morphologies_path: Path, morphology_format: str
) -> Population:
    population = config.node_population(name)
    everyone = population.select_all()
    return Population(
        name=name,
        positions=np.column_stack([population.get_attribute(axis, everyone) for axis in "xyz"]),
        rotations=rotation_matrices(population),
        morphologies=list(population.get_attribute("morphology", everyone)),
        morphologies_path=morphologies_path,
        morphology_format=morphology_format,
    )


def distinct_morphologies(
    populations: Iterable[Population],
) -> Iterator[tuple[MorphologyKey, morphio.Collection]]:
    """Each distinct morphology of the populations, once: its key and what it is read from."""
    seen = set()
    for population in populations:
        collection = morphio.Collection(
            str(population.morphologies_path), extensions=[f".{population.morphology_format}"]
        )
        for key in dict.fromkeys(population.morphology_keys()):
            if key not in seen:
                seen.add(key)
                yield key, collection


def read_morphology(key: MorphologyKey, collection: morphio.Collection) -> Morphology:
    _, name = key
    return Morphology.from_morphio(collection.load(name))


def place_cells(
    populations: Sequence[Population],
    levels: Sequence[Level],
    shapes: Mapping[MorphologyKey, MorphologyLevels],
) -> PackWriter:
    """A writer holding every cell of the populations, numbered through them in their order.

    A cell is placed as a soma alone where its morphology is not in `shapes`, or where its
    position or rotation is not a finite number.
    """
    writer = PackWriter(
        [(population.name, len(population.morphologies)) for population in populations], levels
    )
    cell = 0
    for population in populations:
        placeable = population.placeable()
        if not placeable.all():
            L.warning(
                "%d cells of population %s are somas alone: no finite position or rotation",
                np.count_nonzero(~placeable),
                population.name,
            )
        for key, rotation, position, finite in zip(
            population.morphology_keys(),
            population.rotations,
            population.positions,
            placeable,
            strict=True,
        ):
            shape = shapes.get(key) if finite else None
            if shape is None:
                writer.add_soma(cell, position)
            else:
                writer.add_cell(cell, shape, rotation, position)
            cell += 1
    return writer
