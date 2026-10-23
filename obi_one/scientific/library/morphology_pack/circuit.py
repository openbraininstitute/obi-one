"""From a SONATA circuit to a pack: its populations, their morphologies, and every cell placed."""

import logging
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Literal

import libsonata
import morphio
import numpy as np
from bluepysnap.utils import euler2mat, quaternion2mat

from obi_one.scientific.library.circuit import ALTERNATE_MORPHOLOGY_FORMATS
from obi_one.scientific.library.circuit_metrics import (
    TYPES_OF_BIOPHYS_NODES,
    get_names_of_typed_node_populations,
)
from obi_one.scientific.library.morphology_pack.geometry import (
    Level,
    Morphology,
    MorphologyLevels,
    simplified,
)
from obi_one.scientific.library.morphology_pack.writer import PackWriter
from obi_one.utils.parallel import Processes

L = logging.getLogger(__name__)

MORPHOLOGIES_A_JOB = 4
# What the processes that simplify and encode for a pack import before they are forked.
PRELOAD = (simplified.__module__, PackWriter.__module__)
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


def biophysical_populations(config: libsonata.CircuitConfig) -> list[str]:
    return sorted(get_names_of_typed_node_populations(config, TYPES_OF_BIOPHYS_NODES))


def morphologies_source(
    config: libsonata.CircuitConfig, name: str
) -> tuple[Path, Literal["swc", "asc", "h5"]]:
    """Where a population's morphologies are read from and their format: the first declared of
    'swc', then 'asc', then 'h5'.
    """
    properties = config.node_population_properties(name)
    if properties.morphologies_dir:
        return Path(properties.morphologies_dir), "swc"
    alternates = properties.alternate_morphology_formats
    for key, morphology_format in ALTERNATE_MORPHOLOGY_FORMATS.items():
        if key in alternates:
            return Path(alternates[key]), morphology_format
    msg = "No morphologies found"
    raise ValueError(msg)


def morphology_files(path: Path, morphology_format: str, names: Iterable[str]) -> list[Path]:
    """The container at `path`, or else the file in the folder at `path` of each of `names`."""
    if morphology_format == "h5" and path.suffix == ".h5":
        return [path]
    return [path / f"{name}.{morphology_format}" for name in sorted(set(names))]


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


def simplified_all(
    morphologies: dict[MorphologyKey, Morphology],
    levels: tuple[Level, ...],
    processes: Processes,
) -> Iterator[tuple[MorphologyKey, MorphologyLevels]]:
    """Every morphology simplified to `levels`, over `processes`, in order, as each is done.
    Each is taken out of `morphologies` as it is sent to be simplified.
    """
    keys = list(morphologies)
    each = processes.map(
        partial(simplified, levels=levels),
        (morphologies.pop(key) for key in keys),
        per_job=MORPHOLOGIES_A_JOB,
    )
    return zip(keys, each, strict=True)


def place_cells(
    populations: Sequence[Population],
    levels: Sequence[Level],
    shapes: dict[MorphologyKey, MorphologyLevels],
) -> PackWriter:
    """A writer holding every cell of the populations, numbered through them in their order.

    The cells are placed a morphology at a time, and each morphology is taken out of `shapes`
    once its cells are placed. A cell is placed as a soma alone where its morphology is not in
    `shapes`, or where its position or rotation is not a finite number.
    """
    writer = PackWriter(
        [(population.name, len(population.morphologies)) for population in populations], levels
    )
    waiting: dict[MorphologyKey, list[tuple[int, Population, int]]] = {}
    cell = 0
    for population in populations:
        placeable = population.placeable()
        if not placeable.all():
            L.warning(
                "%d cells of population %s are somas alone: no finite position or rotation",
                np.count_nonzero(~placeable),
                population.name,
            )
        for row, (key, finite) in enumerate(
            zip(population.morphology_keys(), placeable, strict=True)
        ):
            if finite and key in shapes:
                waiting.setdefault(key, []).append((cell, population, row))
            else:
                writer.add_soma(cell, population.positions[row])
            cell += 1
    for key, cells in waiting.items():
        shape = shapes.pop(key)
        for cell, population, row in cells:
            writer.add_cell(cell, shape, population.rotations[row], population.positions[row])
    return writer
