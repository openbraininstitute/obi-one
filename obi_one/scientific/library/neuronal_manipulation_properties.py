"""Which mechanism variables a neuronal manipulation can change in a circuit.

1. Find the ``model_template`` values of the selected neurons in ``nodes.h5``.
2. Read each template's hoc file and the mod files of its mechanisms, fetched in parallel.
3. Fill units the mod files leave undeclared, and each channel's entity_id, from the ion
   channel model entities.
4. A template whose files cannot be read uses its emodel_circuit derivation instead.
5. Return the channels, variables and section lists common to all templates.

See ``docs/neuronal-manipulation-properties.md``.
"""

import logging
import tempfile
from collections import defaultdict
from collections.abc import Callable, Container, Hashable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import UUID

import entitysdk.client
import h5py
import numpy as np
from bluepysnap import Circuit as SnapCircuit
from bluepysnap.exceptions import BluepySnapError
from entitysdk.exception import EntitySDKError
from entitysdk.models import Derivation as DerivationModel, IonChannelModel
from entitysdk.models.asset import Asset
from entitysdk.models.circuit import Circuit
from entitysdk.types import FetchFileStrategy
from libsonata import NodeStorage, SonataError

from obi_one.db_sdk.assets import asset_range_file, is_not_found
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
from obi_one.scientific.library.circuit import CIRCUIT_MOD_DIR, Circuit as ObiCircuit
from obi_one.scientific.library.circuit_constants import TYPES_OF_BIOPHYS_NODES
from obi_one.scientific.library.emodel_circuit_files import (
    HocBiophysics,
    HocTemplateError,
    ModMechanism,
    mechanism_variables,
    read_hoc_biophysics,
    read_mod_mechanism,
)
from obi_one.scientific.library.emodel_parameters import get_mechanism_variables_for_emodel
from obi_one.scientific.library.entity_property_types import CircuitMappedProperties
from obi_one.scientific.library.memodel_circuit import (
    IonChannelVariables,
    MechanismVariableDetail,
    _build_mechanism_variables_by_ion_channel_response,
)
from obi_one.utils.http_range_file import read_contiguous_dataset

L = logging.getLogger(__name__)

# One pool per process, shared by every request: bounds threads and open connections
# however many requests arrive. 16 fetches a template's mod files in one round.
FETCH_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="circuit-file-fetch")
# Bulkhead: whole nodes.h5 downloads (hundreds of MB) get their own pool, so they cannot
# hold every FETCH_POOL thread while other requests' small fetches wait. 4 fill the link.
NODES_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="circuit-nodes-fetch")
# hoc and mod files are tens of KB at most; anything far larger is not a cell model.
MAX_MODEL_FILE_BYTES = 1_000_000
# Where mod files live when the config declares no mechanisms_dir: OBI circuits use
# ``mod``, entitysdk's MEModel staging writes ``mechanisms``. First with a .mod file wins.
UNDECLARED_MOD_DIRS = (CIRCUIT_MOD_DIR, "mechanisms")
# Warnings name a few files or templates, not hundreds (a large circuit has ~1000 templates).
MAX_NAMES_IN_WARNING = 5

# Errors that mean the circuit's files cannot be used, so its derivations are: no
# sonata_circuit asset or a file entitycore cannot serve (ValueError, EntitySDKError), a
# file h5py cannot read (OSError), or a config libsonata cannot parse (it raises
# RuntimeError for bad JSON, SonataError for a bad structure). Anything else is a bug and
# propagates. A failed listing raises CircuitListingError, which is none of these.
CIRCUIT_FILES_ERRORS = (
    ValueError,
    OSError,
    EntitySDKError,
    BluepySnapError,
    SonataError,
    RuntimeError,
)

# Where the response's variables come from: every template's circuit files, every
# template's derivation, or some of each (a template falls back on its own).
VariablesSource = Literal["circuit_files", "derivations", "mixed"]

# (population, node_id) -> model_template (or EModel ID after ``_match_templates_to_emodels``).
TemplateNodes = dict[tuple[str, int], str]


class CircuitListingError(Exception):
    """The files of the circuit asset could not be listed.

    Usually transient (entitycore answers 503). It is raised rather than answered with the
    derivations, so the client can retry and get the circuit-file answer.
    """


@dataclass
class PopulationModelDirs:
    """Where a population's hoc and mod files live inside the circuit asset.

    Attributes:
        population_type: SONATA population type, e.g. ``biophysical`` or ``virtual``.
        hoc_dir: ``biophysical_neuron_models_dir`` as an asset path; None when unset or
            outside the asset.
        mod_dirs: ``mechanisms_dir`` as an asset path, or ``UNDECLARED_MOD_DIRS``.
    """

    population_type: str
    hoc_dir: str | None
    mod_dirs: tuple[str, ...]


@dataclass
class TemplateModel:
    """One cell template read from the circuit's files.

    Attributes:
        biophysics: The parsed hoc file.
        mechanisms: Parsed mod files by suffix, NEURON built-ins excluded.
    """

    biophysics: HocBiophysics
    mechanisms: dict[str, ModMechanism]


def _get_circuit_asset(
    db_client: entitysdk.client.Client,
    circuit_id: str,
) -> tuple[Circuit, Asset]:
    """Get the circuit entity and its ``sonata_circuit`` directory asset.

    The asset object is passed to ``fetch_file``: given only its id, entitysdk fetches the
    asset's metadata again before every file.
    """
    circuit_entity = db_client.get_entity(
        entity_id=UUID(circuit_id),
        entity_type=Circuit,
    )

    directory_assets = [
        a for a in circuit_entity.assets if a.is_directory and a.label.value == "sonata_circuit"
    ]
    if len(directory_assets) != 1:
        msg = f"Circuit {circuit_id} must have exactly one sonata_circuit directory asset."
        raise ValueError(msg)

    asset = directory_assets[0]
    if asset.id is None:
        msg = f"Circuit {circuit_id} sonata_circuit asset has no ID."
        raise ValueError(msg)

    return circuit_entity, asset


def _stage_file(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    asset: Asset,
    temp_dir: Path,
    asset_path: str,
    strategy: FetchFileStrategy = FetchFileStrategy.link_or_download,
) -> Path:
    """Stage one file of the circuit asset into ``temp_dir``; an already staged file is reused.

    Raises:
        ValueError: ``asset_path`` is absolute or holds ``..``. Paths come from circuit
            content, so they are untrusted.
    """
    relative = Path(asset_path)
    if relative.is_absolute() or ".." in relative.parts:
        msg = f"Refusing asset path outside the circuit: {asset_path!r}"
        raise ValueError(msg)
    output_path = temp_dir / relative
    if output_path.exists():
        return output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    db_client.fetch_file(
        entity_id=UUID(circuit_id),
        entity_type=Circuit,
        asset_id=asset,
        output_path=output_path,
        asset_path=relative,
        strategy=strategy,
    )
    return output_path


def _read_model_file(path: Path) -> str:
    """Read a staged hoc or mod file, refusing files too large to be a cell model."""
    size = path.stat().st_size
    if size > MAX_MODEL_FILE_BYTES:
        msg = f"{path.name} is {size} bytes, above the {MAX_MODEL_FILE_BYTES} byte limit"
        raise HocTemplateError(msg)
    # Comments may hold non-UTF-8 author names.
    return path.read_text(encoding="utf-8", errors="replace")


def _relative_dir(config_value: str | None, temp_dir_path: Path) -> str | None:
    """A ``*_dir`` config entry as an asset path, or None when unset or not in the asset."""
    if not config_value:
        return None
    resolved = Path(config_value).resolve()
    if not resolved.is_relative_to(temp_dir_path) or resolved == temp_dir_path:
        return None
    return str(resolved.relative_to(temp_dir_path))


def _stage_circuit_for_neuron_set(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    asset: Asset,
    temp_dir_path: Path,
    population_types: Container[str] | None = None,
    *,
    stage_nodes: bool = True,
) -> tuple[Path, dict[str, str], dict[str, PopulationModelDirs]]:
    """Stage ``circuit_config.json``, the node sets file and the selected ``nodes.h5`` files.

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        asset: The circuit's ``sonata_circuit`` asset.
        temp_dir_path: Resolved directory the files are staged into.
        population_types: Population types whose nodes.h5 to select; None selects all.
        stage_nodes: False returns the nodes.h5 paths without fetching them or the node
            sets file.

    Returns:
        The config path, population -> nodes.h5 asset path for the selected populations,
        and population -> model directories for every population.

    ``EntitySDKError`` propagates when the config or a nodes.h5 cannot be fetched.
    """
    # A real copy, not a symlink, so $BASE_DIR resolves to temp_dir.
    config_path = _stage_file(
        db_client,
        circuit_id,
        asset,
        temp_dir_path,
        "circuit_config.json",
        strategy=FetchFileStrategy.copy_or_download,
    )

    # Reads only the config; node sets and nodes are read later.
    snap_circuit = SnapCircuit(str(config_path))

    pop_to_model_dirs: dict[str, PopulationModelDirs] = {}
    for population in snap_circuit.nodes.population_names:
        pop_config = snap_circuit.nodes[population].config
        mod_dir = _relative_dir(pop_config.get("mechanisms_dir"), temp_dir_path)
        pop_to_model_dirs[population] = PopulationModelDirs(
            population_type=pop_config.get("type", ""),
            hoc_dir=_relative_dir(pop_config.get("biophysical_neuron_models_dir"), temp_dir_path),
            mod_dirs=(mod_dir,) if mod_dir else UNDECLARED_MOD_DIRS,
        )

    pop_to_nodes_path = {
        population: str(
            Path(snap_circuit.nodes[population].h5_filepath).resolve().relative_to(temp_dir_path)
        )
        for population, dirs in pop_to_model_dirs.items()
        if population_types is None or dirs.population_type in population_types
    }

    # The node sets file is optional in SONATA: none declared, or one outside the asset,
    # is skipped.
    node_sets_path = snap_circuit.to_libsonata.node_sets_path
    node_sets_file = Path(node_sets_path).resolve() if node_sets_path else None
    node_sets_asset_path = (
        str(node_sets_file.relative_to(temp_dir_path))
        if node_sets_file and node_sets_file.is_relative_to(temp_dir_path)
        else None
    )
    if node_sets_file and node_sets_asset_path is None:
        L.debug("Node sets file %s is outside the circuit asset, not staged", node_sets_file)

    def stage(asset_path: str) -> Path:
        return _stage_file(db_client, circuit_id, asset, temp_dir_path, asset_path)

    def stage_node_sets(asset_path: str) -> None:
        # Declared but missing is tolerated, as with no node sets file at all. Any other
        # failure (outage, refused token) raises: skipping it would hide the cause of the
        # "unknown node set" error that follows.
        try:
            stage(asset_path)
        except EntitySDKError as err:
            if not is_not_found(err):
                raise
            L.info("%s is not in the circuit asset, continuing without it", asset_path)

    if stage_nodes:
        # A failed nodes.h5 re-raises from result().
        futures: list[Future[Path | None]] = [
            NODES_POOL.submit(stage, path) for path in pop_to_nodes_path.values()
        ]
        if node_sets_asset_path:
            futures.append(FETCH_POOL.submit(stage_node_sets, node_sets_asset_path))
        for future in futures:
            future.result()

    return config_path, pop_to_nodes_path, pop_to_model_dirs


def _public_reason(err: object) -> str:
    """Why a template could not be read, safe for the API response.

    Only ``HocTemplateError`` is quoted; other errors may carry signed URLs, so only their
    type is given.
    """
    return (
        str(err)
        if isinstance(err, HocTemplateError)
        else f"files not readable ({type(err).__name__})"
    )


def _named_list(names: Iterable[str]) -> str:
    """Up to ``MAX_NAMES_IN_WARNING`` names, comma separated, then ``…`` when there are more."""
    names = list(names)
    shown = ", ".join(names[:MAX_NAMES_IN_WARNING])
    return f"{shown}, …" if len(names) > MAX_NAMES_IN_WARNING else shown


def _counted(count: int, noun: str) -> str:
    """``1 template``, ``2 templates``."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _fetch_and_parse[K: Hashable, T](
    keys: Iterable[K],
    parse: Callable[[K, str], T],
    stage: Callable[[K], Path],
) -> dict[K, T | Exception]:
    """Stage and parse one file per key concurrently on ``FETCH_POOL``.

    Returns:
        Key -> parsed result, or the exception that stopped it, so one bad file does not
        fail the other templates. Duplicate keys are fetched once.
    """

    def one(key: K) -> T | Exception:
        try:
            return parse(key, _read_model_file(stage(key)))
        except Exception as err:  # ruff: ignore[blind-except]
            L.warning("Could not read circuit file %s", key, exc_info=True)
            return err

    unique = list(dict.fromkeys(keys))
    return dict(zip(unique, FETCH_POOL.map(one, unique), strict=True))


def _parse_model_file(path: str, text: str) -> HocBiophysics | ModMechanism:
    """Parse a hoc or mod file, chosen by the file extension."""
    return read_hoc_biophysics(text) if path.endswith(".hoc") else read_mod_mechanism(text)


def _asset_files(
    db_client: entitysdk.client.Client, circuit_id: str, asset: Asset
) -> dict[str, int]:
    """Return asset path -> size for every file of the circuit.

    One listing serves two readers: the ``nodes.h5`` sizes for the byte-range read, and
    the paths of the mod files.

    Raises:
        CircuitListingError: entitycore did not list the asset.
    """
    try:
        listing = db_client.list_directory(
            entity_id=UUID(circuit_id), entity_type=Circuit, asset_id=asset.id
        )
    except EntitySDKError as err:
        msg = f"Could not list the files of circuit {circuit_id}, please try again."
        raise CircuitListingError(msg) from err
    return {path.as_posix(): file.size for path, file in listing.files.items()}


def _mod_files_by_dir(asset_paths: Iterable[str]) -> dict[str, list[str]]:
    """Group the asset paths of the ``.mod`` files by their directory."""
    by_dir: dict[str, list[str]] = {}
    for path in map(PurePosixPath, asset_paths):
        if path.suffix == ".mod":
            by_dir.setdefault(str(path.parent), []).append(str(path))
    return by_dir


@dataclass
class ModIndex:
    """The mod files of one directory, indexed by the ``SUFFIX`` each declares.

    NEURON names a mechanism by its ``SUFFIX``, not its file name (rCA1's ``kdrbca1.mod``
    defines ``kdrb``), so every file of the directory is read.

    Attributes:
        mechanisms: SUFFIX -> parsed mod file, or the error when two files define it.
        unread: Errors of files that could not be read; a missing mechanism may be in one.
        unparsed: Names of the files the mod reader rejects; a missing mechanism may be
            in one.
    """

    mechanisms: dict[str, ModMechanism | Exception]
    unread: list[Exception]
    unparsed: list[str]

    def lookup(self, channel: str) -> ModMechanism | str:
        """The mechanism's parsed mod file, or the reason there is none."""
        mod = self.mechanisms.get(channel)
        if isinstance(mod, ModMechanism):
            return mod
        if mod is not None:
            return _public_reason(mod)
        if self.unread:
            return _public_reason(self.unread[0])
        reason = f"no mod file in the circuit defines mechanism '{channel}'"
        if self.unparsed:
            reason += (
                f" ({_counted(len(self.unparsed), 'mod file')} could not be parsed:"
                f" {_named_list(self.unparsed)})"
            )
        return reason


def _mod_index(
    mod_paths: Iterable[str], files: dict[str, HocBiophysics | ModMechanism | Exception]
) -> ModIndex:
    """Index the parsed mod files of one directory by ``SUFFIX``.

    A file that could not be read goes to ``unread``, one the reader rejects (no
    ``SUFFIX``, unbalanced braces, ...) to ``unparsed``.
    """
    index = ModIndex(mechanisms={}, unread=[], unparsed=[])
    for path in mod_paths:
        parsed = files[path]
        if isinstance(parsed, ModMechanism):
            if parsed.suffix in index.mechanisms:
                msg = f"mechanism '{parsed.suffix}' is defined by more than one mod file"
                index.mechanisms[parsed.suffix] = HocTemplateError(msg)
            else:
                index.mechanisms[parsed.suffix] = parsed
        elif isinstance(parsed, HocTemplateError):
            index.unparsed.append(PurePosixPath(path).name)
        elif isinstance(parsed, Exception):
            index.unread.append(parsed)
    return index


def _template_hoc_paths(
    templates_per_population: dict[str, set[str]],
    pop_to_model_dirs: dict[str, PopulationModelDirs],
) -> tuple[dict[str, str], dict[str, PopulationModelDirs], dict[str, str], list[str]]:
    """Find each template's hoc file and model directories.

    The first population that lists a template decides its directories; a template whose
    populations declare different directories is named in a warning.

    Returns:
        Template -> hoc asset path, template -> directories, template -> why it has no
        hoc path, and the warnings.
    """
    hoc_paths: dict[str, str] = {}
    template_dirs: dict[str, PopulationModelDirs] = {}
    reasons: dict[str, str] = {}
    first_population: dict[str, str] = {}
    conflicts: dict[tuple[str, str], list[str]] = defaultdict(list)
    for population, templates in templates_per_population.items():
        dirs = pop_to_model_dirs[population]
        for template in sorted(templates):
            if template in template_dirs:
                used = template_dirs[template]
                if (used.hoc_dir, used.mod_dirs) != (dirs.hoc_dir, dirs.mod_dirs):
                    conflicts[first_population[template], population].append(template)
                continue
            template_dirs[template] = dirs
            first_population[template] = population
            if dirs.hoc_dir is None:
                reasons[template] = "population has no biophysical_neuron_models_dir"
            else:
                name = template.rsplit(":", maxsplit=1)[-1]
                hoc_paths[template] = f"{dirs.hoc_dir}/{name}.hoc"
    warnings = [
        f"Populations '{used}' and '{other}' declare different model directories for"
        f" {_counted(len(names), 'template')} ({_named_list(names)}); the files of '{used}'"
        " are used."
        for (used, other), names in conflicts.items()
    ]
    return hoc_paths, template_dirs, reasons, warnings


def _mod_paths_per_dirs(
    candidates: Iterable[tuple[str, ...]], mod_files_by_dir: dict[str, list[str]]
) -> dict[tuple[str, ...], list[str]]:
    """For each candidate list, the mod files of the first directory that has any."""
    return {
        mod_dirs: next((sorted(mod_files_by_dir[d]) for d in mod_dirs if d in mod_files_by_dir), [])
        for mod_dirs in dict.fromkeys(candidates)
    }


def _read_template_models(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    asset: Asset,
    temp_dir_path: Path,
    templates_per_population: dict[str, set[str]],
    pop_to_model_dirs: dict[str, PopulationModelDirs],
    asset_files: dict[str, int],
) -> tuple[dict[str, TemplateModel | str], list[str]]:
    """Read every template from its hoc file and the mod files of its directory.

    All hoc and mod files go in one parallel batch: the whole mod directory (a few dozen
    small files) is cheaper to fetch than to look up file by file.

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        asset: The circuit's ``sonata_circuit`` asset.
        temp_dir_path: Directory where files are staged for this request.
        templates_per_population: Population -> the templates to read.
        pop_to_model_dirs: Population -> where its hoc and mod files are.
        asset_files: The asset listing.

    Returns:
        Template -> its model, or the reason it could not be read; and the warnings.
    """

    def stage(path: str) -> Path:
        return _stage_file(db_client, circuit_id, asset, temp_dir_path, path)

    hoc_paths, template_dirs, reasons, warnings = _template_hoc_paths(
        templates_per_population, pop_to_model_dirs
    )
    result: dict[str, TemplateModel | str] = dict(reasons)
    if not hoc_paths:
        return result, warnings

    mod_paths = _mod_paths_per_dirs(
        (template_dirs[template].mod_dirs for template in hoc_paths),
        _mod_files_by_dir(asset_files),
    )
    files = _fetch_and_parse(
        [*hoc_paths.values(), *(p for paths in mod_paths.values() for p in paths)],
        _parse_model_file,
        stage,
    )
    indexes = {dirs: _mod_index(paths, files) for dirs, paths in mod_paths.items()}

    for template, hoc_path in hoc_paths.items():
        parsed = files[hoc_path]
        result[template] = (
            _template_model(parsed, indexes[template_dirs[template].mod_dirs])
            if isinstance(parsed, HocBiophysics)
            else _public_reason(parsed)
        )
    warnings += _fill_from_database(
        db_client,
        [
            mechanism
            for model in result.values()
            if isinstance(model, TemplateModel)
            for mechanism in model.mechanisms.values()
        ],
    )
    return result, warnings


def _undeclared_units(mechanism: ModMechanism) -> list[str]:
    """Variables shown in the response whose unit the mod file does not declare."""
    shown = (*mechanism.settable_range_variables, *mechanism.global_variables)
    return [name for name in shown if name not in mechanism.units]


def _normalized_unit(unit: str) -> str:
    """Spell a unit one way: ``mho`` is the old name of ``S``."""
    return unit.replace("mho", "S").replace(" ", "")


def _entity_units(model: IonChannelModel) -> dict[str, str]:
    """Variable -> unit declared by an ion channel model entity (empty units skipped)."""
    block = model.neuron_block
    entries = [*(block.range or []), *(block.global_ or [])] if block else []
    return {name: unit for entry in entries for name, unit in entry.items() if unit}


def _matching_models(
    mechanism: ModMechanism, models: Iterable[IonChannelModel]
) -> list[IonChannelModel]:
    """The entities with the mechanism's suffix that describe the same mechanism.

    Two mechanisms can share a suffix, so an entity counts only when every unit it shares
    with the mod file is equal.
    """
    declared = {name: _normalized_unit(unit) for name, unit in mechanism.units.items()}
    matching = []
    for model in models:
        units = _entity_units(model)
        if all(_normalized_unit(units[n]) == u for n, u in declared.items() if n in units):
            matching.append(model)
    return matching


def _database_units(mechanism: ModMechanism, models: Iterable[IonChannelModel]) -> dict[str, str]:
    """Units for the mechanism's undeclared variables, from entities with its suffix.

    Only matching entities count (``_matching_models``), and a unit is taken only when all
    of them agree.

    Returns:
        Variable -> unit, for the variables a unit was found for.
    """
    missing = _undeclared_units(mechanism)
    # Missing variable -> {normalized unit: unit as written}.
    found: dict[str, dict[str, str]] = defaultdict(dict)
    for model in _matching_models(mechanism, models):
        units = _entity_units(model)
        for name in missing:
            if name in units:
                found[name][_normalized_unit(units[name])] = units[name]
    return {name: next(iter(units.values())) for name, units in found.items() if len(units) == 1}


def _fill_from_database(
    db_client: entitysdk.client.Client, mechanisms: Iterable[ModMechanism]
) -> list[str]:
    """Fill, in place, each mechanism's ``entity_id`` and undeclared units.

    One search per distinct suffix, in parallel on ``FETCH_POOL``: entitycore filters one
    ``nmodl_suffix`` per request, and a template's 10-20 mechanisms then cost one round.
    The ``entity_id`` is set only when exactly one entity matches, so the UI never links
    a channel to the wrong model. A failed search is logged and leaves both empty.

    Returns:
        One warning naming the mechanisms left without an ``entity_id``, if any.
    """
    by_suffix: dict[str, list[ModMechanism]] = defaultdict(list)
    for mechanism in mechanisms:
        by_suffix[mechanism.suffix].append(mechanism)

    def search(suffix: str) -> list[IonChannelModel] | None:
        try:
            return db_client.search_entity(
                entity_type=IonChannelModel, query={"nmodl_suffix": suffix}
            ).all()
        except EntitySDKError:
            L.warning("Could not search ion channel models for %s", suffix, exc_info=True)
            return None

    unmatched: list[str] = []
    for suffix, models in zip(by_suffix, FETCH_POOL.map(search, by_suffix), strict=True):
        for mechanism in by_suffix[suffix]:
            matching = _matching_models(mechanism, models or [])
            mechanism.entity_id = str(matching[0].id) if len(matching) == 1 else None
            mechanism.units.update(_database_units(mechanism, matching))
        if any(mechanism.entity_id is None for mechanism in by_suffix[suffix]):
            unmatched.append(suffix)
    if not unmatched:
        return []
    warning = (
        f"No single ion channel model matches {_counted(len(unmatched), 'mechanism')}"
        f" ({_named_list(sorted(unmatched))}): none or several share the nmodl_suffix,"
        " so their entity_id is null."
    )
    return [warning]


def _template_model(biophysics: HocBiophysics, index: ModIndex) -> TemplateModel | str:
    """Join a parsed hoc file with its mechanisms' mod files, or return why it cannot be."""
    mechanisms: dict[str, ModMechanism] = {}
    for channel in sorted(biophysics.mod_file_mechanisms):
        mod = index.lookup(channel)
        if isinstance(mod, str):
            return mod
        mechanisms[channel] = mod
    return TemplateModel(biophysics=biophysics, mechanisms=mechanisms)


def _read_dataset(dataset: h5py.Dataset) -> np.ndarray:
    """Read a whole dataset through h5py."""
    return dataset[()]


def _unique_templates(
    group: h5py.Group, read_column: Callable[[h5py.Dataset], np.ndarray] = _read_dataset
) -> set[str] | None:
    """Return the distinct, non-empty ``model_template`` values of one population.

    An enumerated column (integers plus an ``@library`` of names) costs one small read:
    only the distinct integers are looked up.

    Args:
        group: The population's ``nodes/<population>/0`` group.
        read_column: Reads the column dataset. A remote file passes
            ``read_contiguous_dataset`` so the read does not hold h5py's lock.

    Returns:
        The template names, or None when the population has no ``model_template``.
    """
    if "model_template" not in group:
        return None
    column = read_column(group["model_template"])
    if "@library" in group and "model_template" in group["@library"]:
        library = group["@library/model_template"].asstr()[:]
        templates = {str(library[index]) for index in np.unique(column)}
    else:
        # Fixed-length strings are bytes, variable-length ones str.
        templates = {t.decode() if isinstance(t, bytes) else str(t) for t in column}
    return templates - {""}


def _population_templates(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    asset: Asset,
    temp_dir_path: Path,
    population: str,
    nodes_relative: str,
    size: int | None,
) -> set[str] | None:
    """Return one population's distinct ``model_template`` values, the cheapest way that works.

    1. A symlink to the mounted asset store.
    2. Byte-range reads of the column only (34 MB of a 743 MB file); needs ``size``.
    3. A full download, when ranges fail (logged) or the size is unknown.

    Returns:
        The template names, or None when the population has no ``model_template``.
    """
    try:
        path = _stage_file(
            db_client,
            circuit_id,
            asset,
            temp_dir_path,
            nodes_relative,
            strategy=FetchFileStrategy.link_only,
        )
    except EntitySDKError:
        if size is not None:
            try:
                remote = asset_range_file(
                    db_client,
                    entity_id=UUID(circuit_id),
                    entity_type=Circuit,
                    asset_id=asset.id,
                    asset_path=nodes_relative,
                    size=size,
                )
                with remote, h5py.File(remote, "r") as h5:
                    return _unique_templates(
                        h5[f"nodes/{population}/0"],
                        lambda dataset: read_contiguous_dataset(dataset, remote),
                    )
            except Exception:  # ruff: ignore[blind-except]
                L.warning(
                    "Partial read of %s failed, downloading it", nodes_relative, exc_info=True
                )
        path = _stage_file(db_client, circuit_id, asset, temp_dir_path, nodes_relative)
    with h5py.File(path, "r") as h5:
        return _unique_templates(h5[f"nodes/{population}/0"])


def _node_templates(
    temp_dir_path: Path,
    pop_to_nodes_path: dict[str, str],
    population: str,
    node_ids: list[int],
    circuit_id: str,
) -> list[str]:
    """The ``model_template`` of each node, read from the staged ``nodes.h5``.

    Raises:
        ValueError: The population has no nodes file or no ``model_template``.
    """
    try:
        nodes_relative = pop_to_nodes_path[population]
    except KeyError as err:
        msg = f"No nodes file found for population '{population}'."
        raise ValueError(msg) from err

    pop_obj = NodeStorage(str(temp_dir_path / nodes_relative)).open_population(population)
    if "model_template" not in pop_obj.attribute_names:
        msg = (
            f"Property 'model_template' not found in population"
            f" '{population}' of circuit {circuit_id}."
            f" Available: {list(pop_obj.attribute_names)}"
        )
        raise ValueError(msg)
    return pop_obj.get_attribute("model_template", node_ids)


def _stage_circuit_for_neuron_set_resolution(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    circuit_entity: Circuit,
    asset: Asset,
    neuron_set: NeuronSet,
    *,
    read_files: bool = True,
) -> tuple[list[str], TemplateNodes, dict[str, TemplateModel | str], list[str]]:
    """Stage the circuit, resolve the neuron set to node IDs and read their templates.

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        circuit_entity: The circuit entity, for its name.
        asset: The circuit's ``sonata_circuit`` asset.
        neuron_set: Neuron set to resolve; swept fields are expanded.
        read_files: False resolves the templates without reading their hoc and mod files
            (no listing either), so the caller uses the derivations.

    Returns:
        The populations, (population, node_id) -> model_template, model_template ->
        model or reason it could not be read, and the warnings. All are empty when the
        neuron set selects no neurons. Selected neurons of a population that is not
        biophysical (point neurons) have no mechanism variables: they are left out with
        one warning, and their population is still listed.

    ``ValueError`` propagates for a population without a nodes file or without
    ``model_template``.
    """
    # Listed while the circuit is staged: no extra wait.
    listing = FETCH_POOL.submit(_asset_files, db_client, circuit_id, asset) if read_files else None
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir).resolve()

        config_path, pop_to_nodes_path, pop_to_model_dirs = _stage_circuit_for_neuron_set(
            db_client,
            circuit_id,
            asset,
            temp_dir_path,
        )

        obi_circuit = ObiCircuit(name=circuit_entity.name or circuit_id, path=str(config_path))

        ids_per_population: dict[str, list[int]] = get_expanded_neuron_ids(neuron_set, obi_circuit)

        node_to_template: TemplateNodes = {}
        populations: list[str] = []
        templates_per_population: dict[str, set[str]] = {}
        not_biophysical: dict[str, int] = {}

        for population, node_ids in ids_per_population.items():
            if not node_ids:
                continue

            populations.append(population)
            if pop_to_model_dirs[population].population_type not in TYPES_OF_BIOPHYS_NODES:
                not_biophysical[population] = len(node_ids)
                continue
            templates = _node_templates(
                temp_dir_path, pop_to_nodes_path, population, node_ids, circuit_id
            )
            node_to_template.update(
                zip([(population, nid) for nid in node_ids], templates, strict=True)
            )
            templates_per_population[population] = set(templates)

        warnings = (
            [_not_biophysical_warning(not_biophysical, pop_to_model_dirs)]
            if not_biophysical
            else []
        )
        if not templates_per_population:
            # No templates to read; with no population either, the caller answers with a
            # warning of its own.
            return populations, {}, {}, warnings
        if listing is None:
            return populations, node_to_template, {}, warnings

        template_models, read_warnings = _read_template_models(
            db_client,
            circuit_id,
            asset,
            temp_dir_path,
            templates_per_population,
            pop_to_model_dirs,
            listing.result(),
        )

    return populations, node_to_template, template_models, [*warnings, *read_warnings]


def _not_biophysical_warning(
    neuron_counts: dict[str, int], pop_to_model_dirs: dict[str, PopulationModelDirs]
) -> str:
    """One warning for the selected neurons whose populations have no cell models."""
    populations = [
        f"'{population}' ({pop_to_model_dirs[population].population_type or 'no type'})"
        for population in neuron_counts
    ]
    return (
        f"{_counted(sum(neuron_counts.values()), 'selected neuron')} are in populations"
        f" that are not biophysical ({_named_list(populations)}), so they have no mechanism"
        " variables and are left out."
    )


def _collect_all_templates(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    asset: Asset,
) -> tuple[dict[str, set[str]], dict[str, TemplateModel | str], list[str]]:
    """Return every template of every biophysical population, with its model.

    Returns:
        Population -> its templates, template -> its model or the reason it failed, and
        the warnings.
    """
    # Listed while the config is fetched: no extra wait.
    listing = FETCH_POOL.submit(_asset_files, db_client, circuit_id, asset)
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir).resolve()
        _config_path, pop_to_nodes_path, pop_to_model_dirs = _stage_circuit_for_neuron_set(
            db_client,
            circuit_id,
            asset,
            temp_dir_path,
            population_types=TYPES_OF_BIOPHYS_NODES,
            stage_nodes=False,
        )
        asset_files = listing.result()
        templates_per_population: dict[str, set[str]] = {}
        for population, nodes_relative in pop_to_nodes_path.items():
            templates = _population_templates(
                db_client,
                circuit_id,
                asset,
                temp_dir_path,
                population,
                nodes_relative,
                asset_files.get(nodes_relative),
            )
            if templates is not None:
                templates_per_population[population] = templates
        template_models, warnings = _read_template_models(
            db_client,
            circuit_id,
            asset,
            temp_dir_path,
            templates_per_population,
            pop_to_model_dirs,
            asset_files,
        )
    return templates_per_population, template_models, warnings


def get_expanded_neuron_ids(neuron_set: NeuronSet, circuit: ObiCircuit) -> dict[str, list[int]]:
    """Resolve a neuron set to node IDs per population, expanding swept fields.

    A list in a block field is a scan dimension. Endpoints get no scan expansion, so each
    single-valued copy is resolved here and the node IDs are unioned per population.

    Returns:
        Population -> sorted union of node IDs.

    ``ValueError`` propagates from ``Block.expand_multi_values`` for too many combinations
    or a nested swept value.
    """
    ids_per_population: dict[str, set[int]] = {}
    for expanded in neuron_set.expand_multi_values():
        for population, node_ids in expanded.get_neuron_ids(circuit).items():
            ids_per_population.setdefault(population, set()).update(node_ids)

    return {population: sorted(ids) for population, ids in ids_per_population.items()}


def get_circuit_node_ids(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    neuron_set: NeuronSet,
) -> dict[str, list[int]]:
    """Resolve a neuron set to node IDs per population (see ``get_expanded_neuron_ids``).

    ``ValueError`` propagates when the circuit has no single ``sonata_circuit`` asset.
    """
    circuit_entity, asset = _get_circuit_asset(db_client, circuit_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir).resolve()

        config_path, _, _ = _stage_circuit_for_neuron_set(
            db_client,
            circuit_id,
            asset,
            temp_dir_path,
        )

        obi_circuit = ObiCircuit(name=circuit_entity.name or circuit_id, path=str(config_path))

        ids_per_population = get_expanded_neuron_ids(neuron_set, obi_circuit)

    return ids_per_population


def _build_template_groups(
    template_models: dict[str, TemplateModel | str],
    template_to_nodes: dict[str, list[tuple[str, int]]],
) -> tuple[dict[str, dict], dict[str, str | None], list[str]]:
    """Build one group of variables per template from its circuit files.

    A template missing from ``template_models`` was not read on purpose (the circuit-file
    path is switched off): it goes to the derivations with no reason.

    Returns:
        The groups (same shape as ``_build_emodel_groups``), template -> reason for the
        templates not read (None when not read on purpose), and warnings for values not
        readable.
    """
    groups: dict[str, dict] = {}
    failed: dict[str, str | None] = {}
    warnings: list[str] = []
    for template, node_keys in template_to_nodes.items():
        model = template_models.get(template)
        if not isinstance(model, TemplateModel):
            failed[template] = model
            continue
        variables, mapping = mechanism_variables(model.biophysics, model.mechanisms)
        warnings.extend(f"{template}: {warning}" for warning in model.biophysics.warnings)
        groups[template] = {
            "node_ids": sorted(node_keys),
            "model_template": template,
            "mechanism_variables_by_ion_channel": (
                _build_mechanism_variables_by_ion_channel_response(variables, mapping)
            ),
        }
    return groups, failed, warnings


def _build_groups_with_fallback(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    node_to_template: TemplateNodes,
    template_models: dict[str, TemplateModel | str],
) -> tuple[dict[str, dict], list[str], VariablesSource | None]:
    """Build groups from the circuit files, then from derivations for the templates left.

    Returns:
        The groups; one warning per reason and outcome naming the templates that needed
        the derivation or had none (one per template is hundreds on a large circuit); and
        where the groups come from, None when there is none.
    """
    template_to_nodes: dict[str, list[tuple[str, int]]] = {}
    for key, template in node_to_template.items():
        template_to_nodes.setdefault(template, []).append(key)

    groups, failed, warnings = _build_template_groups(template_models, template_to_nodes)
    if not failed:
        return groups, warnings, "circuit_files" if groups else None

    fallback_nodes = {key: tpl for key, tpl in node_to_template.items() if tpl in failed}
    label_to_emodel_id = _fetch_emodel_derivation_mapping(db_client, circuit_id)
    node_key_to_emodel, unmatched = _match_templates_to_emodels(fallback_nodes, label_to_emodel_id)
    derivation_groups = _build_emodel_groups(db_client, node_key_to_emodel, label_to_emodel_id)
    source: VariablesSource | None = None
    if derivation_groups:
        source = "mixed" if groups else "derivations"
    elif groups:
        source = "circuit_files"
    groups.update(derivation_groups)
    by_outcome: dict[tuple[str | None, bool], list[str]] = defaultdict(list)
    for template, reason in sorted(failed.items()):
        by_outcome[reason, template in unmatched].append(template)
    for (reason, no_derivation), templates in by_outcome.items():
        names = f"{_counted(len(templates), 'template')} ({_named_list(templates)})"
        if reason is None:
            # Derivations by choice: only a template without one is worth a warning.
            if no_derivation:
                warnings.append(f"No derivation found for {names}, so they are left out.")
            continue
        outcome = (
            f"No derivation found for {names} either, so they are left out"
            if no_derivation
            else f"Used the emodel_circuit derivation instead for {names}"
        )
        warnings.append(f"Circuit files: {reason}. {outcome}.")
    return groups, warnings, source


def _fetch_emodel_derivation_mapping(
    db_client: entitysdk.client.Client,
    circuit_id: str,
) -> dict[str, str]:
    """Fetch emodel_circuit derivations and build label -> emodel_id map."""
    derivations = db_client.search_entity(
        entity_type=DerivationModel,
        query={
            "generated__id": circuit_id,
            "derivation_type": "emodel_circuit",
        },
    ).all()
    label_to_emodel_id: dict[str, str] = {}
    for deriv in derivations:
        if deriv.label and deriv.used:
            label_to_emodel_id[deriv.label] = str(deriv.used.id)
    return label_to_emodel_id


def _match_templates_to_emodels(
    node_to_template: TemplateNodes,
    label_to_emodel_id: dict[str, str],
) -> tuple[TemplateNodes, set[str]]:
    """Match node model_template values to emodel IDs via derivation labels.

    Returns:
        Tuple of (node_key_to_emodel, unmatched_templates) where node_key is
        a (population, node_id) tuple.
    """
    node_key_to_emodel: TemplateNodes = {}
    unmatched_templates: set[str] = set()
    for key, template in node_to_template.items():
        if template in label_to_emodel_id:
            node_key_to_emodel[key] = label_to_emodel_id[template]
        else:
            unmatched_templates.add(template)
    return node_key_to_emodel, unmatched_templates


def _build_emodel_groups(
    db_client: entitysdk.client.Client,
    node_key_to_emodel: TemplateNodes,
    label_to_emodel_id: dict[str, str],
) -> dict[str, dict]:
    """Group nodes by emodel and fetch mechanism variables for each.

    A failed fetch is logged and leaves the group's variables empty, so the intersection
    skips it instead of failing the request.

    Returns:
        EModel ID -> ``{"node_ids", "model_template", "mechanism_variables_by_ion_channel"}``.
    """
    emodel_to_nodes: dict[str, list[tuple[str, int]]] = {}
    for key, emodel_id in node_key_to_emodel.items():
        emodel_to_nodes.setdefault(emodel_id, []).append(key)

    emodel_groups: dict[str, dict] = {}
    for emodel_id, group_node_ids in emodel_to_nodes.items():
        template = next(label for label, eid in label_to_emodel_id.items() if eid == emodel_id)
        try:
            variables, channel_mapping = get_mechanism_variables_for_emodel(db_client, emodel_id)
            mechanism_vars = _build_mechanism_variables_by_ion_channel_response(
                variables, channel_mapping
            )
        except Exception:  # ruff: ignore[blind-except]
            L.warning(
                "Failed to get mechanism variables for emodel %s",
                emodel_id,
                exc_info=True,
            )
            mechanism_vars = {}

        emodel_groups[emodel_id] = {
            "node_ids": sorted(group_node_ids),
            "model_template": template,
            "mechanism_variables_by_ion_channel": mechanism_vars,
        }
    return emodel_groups


def _compute_common_mechanism_variables(
    emodel_groups: dict[str, dict],
) -> dict[str, IonChannelVariables]:
    """Intersect the mechanism variables of all groups (templates or emodels).

    Only channels, variables and section lists present in every group are kept; limits
    take the most restrictive range. A single group is returned as is, values included.
    """
    if not emodel_groups:
        return {}

    groups = list(emodel_groups.values())

    # Filter out groups that failed to fetch mechanism variables
    groups_with_vars = [g for g in groups if g["mechanism_variables_by_ion_channel"]]
    if not groups_with_vars:
        return {}

    # Single emodel: return its variables directly (no intersection needed)
    if len(groups_with_vars) == 1:
        return groups_with_vars[0]["mechanism_variables_by_ion_channel"]

    # Multiple emodels: compute intersection
    all_channel_sets = [
        set(g["mechanism_variables_by_ion_channel"].keys()) for g in groups_with_vars
    ]
    common_channels = set.intersection(*all_channel_sets)

    if not common_channels:
        return {}

    result: dict[str, IonChannelVariables] = {}
    for channel in sorted(common_channels):
        # Intersect variables for this channel
        all_var_sets = [
            set(g["mechanism_variables_by_ion_channel"][channel].variables.keys())
            for g in groups_with_vars
        ]
        common_vars = set.intersection(*all_var_sets)
        if not common_vars:
            continue

        # Intersect section_lists for this channel
        all_section_lists = [
            set(g["mechanism_variables_by_ion_channel"][channel].section_lists)
            for g in groups_with_vars
        ]
        common_section_lists = sorted(set.intersection(*all_section_lists))
        if not common_section_lists:
            continue

        # Build variables with merged limits
        variables: dict[str, MechanismVariableDetail] = {}
        for var_name in sorted(common_vars):
            all_details = [
                g["mechanism_variables_by_ion_channel"][channel].variables[var_name]
                for g in groups_with_vars
            ]

            # Most restrictive limits
            all_limits = [d.limits for d in all_details if d.limits is not None]
            if all_limits:
                merged_limits: list[float] | None = [
                    max(lim[0] for lim in all_limits),
                    min(lim[1] for lim in all_limits),
                ]
            else:
                merged_limits = None

            # A derivation group can leave the unit empty; the first group that has one wins.
            variables[var_name] = MechanismVariableDetail(
                units=next((d.units for d in all_details if d.units), ""),
                limits=merged_limits,
                variable_type=all_details[0].variable_type,
                section_lists_original_values=dict.fromkeys(common_section_lists),
            )

        # The channel keeps its ion channel model only when every group names the same one.
        entity_ids = {
            g["mechanism_variables_by_ion_channel"][channel].entity_id for g in groups_with_vars
        }
        result[channel] = IonChannelVariables(
            section_lists=common_section_lists,
            entity_id=entity_ids.pop() if len(entity_ids) == 1 else None,
            variables=variables,
        )

    return result


def _empty_response(warning: str, populations: list[str] | None = None) -> dict:
    """A response with no variables and one warning."""
    return {
        "entity_type": "circuit",
        "populations": populations,
        CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL: {},
        "source": None,
        "warnings": [warning],
    }


def no_neurons_warning(neuron_set: NeuronSet, circuit_name: str) -> str:
    """Say which selection matched no neurons, so the user can pick another one."""
    selection = []
    population = getattr(neuron_set, "population", None)
    if population:
        selection.append(f"population '{population}'")
    node_sets = getattr(neuron_set, "node_set", None)
    if node_sets:
        names = [node_sets] if isinstance(node_sets, str) else node_sets
        selection.append(f"node sets {', '.join(names)}")
    details = f" ({'; '.join(selection)})" if selection else ""
    return (
        f"The neuron set selects no neurons in circuit '{circuit_name}'{details},"
        " so there are no mechanism variables to list."
    )


def _all_templates(
    db_client: entitysdk.client.Client, circuit_id: str, *, from_circuit_files: bool
) -> tuple[TemplateNodes, dict[str, TemplateModel | str], list[str]] | str:
    """Every template of the circuit, with its model, for a request without a neuron set.

    Read from the circuit files when ``from_circuit_files``; otherwise, or when the files
    cannot be used, the templates are the labels of the circuit's derivations.

    Returns:
        Synthetic node -> template (one per template: no node IDs are needed), template ->
        model or the reason it was not read, and the warnings; or the warning of an
        empty response.
    """
    reason: str | None = None
    if from_circuit_files:
        try:
            _circuit_entity, asset = _get_circuit_asset(db_client, circuit_id)
            templates_per_population, template_models, warnings = _collect_all_templates(
                db_client, circuit_id, asset
            )
        except CIRCUIT_FILES_ERRORS as err:
            # No sonata_circuit asset or unreadable files: only the derivations are left.
            L.warning("Could not read templates of circuit %s", circuit_id, exc_info=True)
            reason = _public_reason(err)
        else:
            node_to_template: TemplateNodes = {
                (population, index): template
                for population, templates in templates_per_population.items()
                for index, template in enumerate(sorted(templates))
            }
            if not node_to_template:
                return "No population with a model_template found in this circuit."
            return node_to_template, template_models, warnings

    label_to_emodel_id = _fetch_emodel_derivation_mapping(db_client, circuit_id)
    if not label_to_emodel_id:
        prefix = f"Circuit {reason}. " if reason else ""
        return f"{prefix}No emodel_circuit derivations found for this circuit."
    node_to_template = {
        ("__derivations__", index): label for index, label in enumerate(sorted(label_to_emodel_id))
    }
    # Without a reason the templates are not in the dict: derivations by choice.
    return node_to_template, dict.fromkeys(label_to_emodel_id, reason) if reason else {}, []


def get_circuit_manipulation_properties(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    neuron_set: NeuronSet | None = None,
    *,
    from_circuit_files: bool = True,
) -> dict:
    """Mechanism variables common to the cell templates of a circuit, or of its neuron set.

    Without a neuron set, every template of every biophysical population counts; with
    one, the templates of the nodes it selects. Each template is read from its hoc and
    mod files; one whose files cannot be read uses its emodel_circuit derivation instead,
    with a warning.

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        neuron_set: Neuron set to resolve; may span several populations.
        from_circuit_files: False reads no hoc or mod file: every template uses its
            derivation, as before the circuit-file path existed (a deployment switch).

    Returns:
        ``entity_type``, ``populations``, ``mechanism_variables_by_ion_channel``,
        ``source`` (``VariablesSource``, None when no template has variables) and
        ``warnings``.

    With a neuron set, ``ValueError`` propagates (HTTP 400) when the circuit has no single
    sonata_circuit asset or a population has no ``model_template``; a set that selects no
    neurons gives ``populations=[]``, no variables and a warning. Without one, such a
    circuit uses its derivations. ``CircuitListingError`` propagates in both modes when
    the circuit asset cannot be listed: retrying usually works.
    """
    resolved_populations: list[str] | None = None

    if neuron_set is None:
        templates = _all_templates(db_client, circuit_id, from_circuit_files=from_circuit_files)
        if isinstance(templates, str):
            return _empty_response(templates)
        node_to_template, template_models, read_warnings = templates
    else:
        circuit_entity, asset = _get_circuit_asset(db_client, circuit_id)
        resolved_populations, node_to_template, template_models, read_warnings = (
            _stage_circuit_for_neuron_set_resolution(
                db_client,
                circuit_id,
                circuit_entity,
                asset,
                neuron_set,
                read_files=from_circuit_files,
            )
        )
        if not resolved_populations:
            return _empty_response(
                no_neurons_warning(neuron_set, circuit_entity.name or circuit_id),
                populations=[],
            )

    emodel_groups, fallback_warnings, source = _build_groups_with_fallback(
        db_client, circuit_id, node_to_template, template_models
    )
    warning_messages = [*read_warnings, *fallback_warnings]

    common_vars = _compute_common_mechanism_variables(emodel_groups)

    if not common_vars and emodel_groups:
        warning_messages.append(
            "No common mechanism variables found across the selected neurons' emodels."
        )

    return {
        "entity_type": "circuit",
        "populations": resolved_populations,
        CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL: common_vars,
        "source": source,
        "warnings": warning_messages or None,
    }
