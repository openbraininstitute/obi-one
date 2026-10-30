"""Which mechanism variables a neuronal manipulation can change in a circuit.

For a circuit and an optional neuron set, the steps are:

1. Find the cell templates (``model_template`` values) of the selected neurons in
   ``nodes.h5``. Without a neuron set, only that column is read, by byte ranges.
2. Read each template's ``.hoc`` file and the ``.mod`` files of its mechanisms from the
   circuit asset, all fetched in parallel.
3. Fill units the mod files leave undeclared from the ion channel model entities.
4. For a template whose files cannot be read, use its emodel_circuit derivation instead.
5. Keep the channels, variables and section lists common to all templates, and return
   them in the MEModel response shape.

See ``docs/neuronal-manipulation-properties.md`` for the data flow and its limits.
"""

from __future__ import annotations

import logging
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING
from uuid import UUID

import h5py
import numpy as np
from bluepysnap import Circuit as SnapCircuit
from entitysdk.exception import EntitySDKError
from entitysdk.models import Derivation as DerivationModel, IonChannelModel
from entitysdk.models.circuit import Circuit
from entitysdk.types import FetchFileStrategy
from libsonata import NodeStorage

from obi_one.db_sdk.assets import open_asset_h5
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

if TYPE_CHECKING:
    from collections.abc import Callable, Container, Hashable, Iterable

    import entitysdk.client
    from entitysdk.models.asset import Asset

    from obi_one.scientific.blocks.neuron_sets.base import NeuronSet

L = logging.getLogger(__name__)

# One pool for every request in the process: the API serves many requests at once, so a
# per-request pool would multiply threads and open connections with the request count.
# 16 lets one request fetch a typical template's mod files in a single round; under load,
# fetches queue here instead of piling onto entitycore and storage. The cap is fixed;
# make it a setting if the API's request concurrency or entitycore's limits change.
FETCH_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="circuit-file-fetch")
# hoc and mod files are a few KB to tens of KB; anything far larger is not a cell model
# and is refused before it is read into memory.
MAX_MODEL_FILE_BYTES = 1_000_000
# Where circuits keep mod files when the config declares no mechanisms_dir, in order of
# preference: OBI circuits use ``mod`` (see ``ensure_mechanisms_dir``), entitysdk's MEModel
# staging writes ``mechanisms``. The first that holds a ``.mod`` file in the asset listing wins.
UNDECLARED_MOD_DIRS = (CIRCUIT_MOD_DIR, "mechanisms")

# (population, node_id) -> model_template, or -> EModel ID after derivation matching.
TemplateNodes = dict[tuple[str, int], str]


@dataclass
class PopulationModelDirs:
    """Where a population's cell templates and mechanisms live inside the circuit asset.

    Attributes:
        population_type: SONATA population type, e.g. ``biophysical`` or ``virtual``.
        hoc_dir: ``biophysical_neuron_models_dir`` as an asset path; None when unset or
            outside the asset.
        mod_dirs: ``mechanisms_dir`` as an asset path, or ``UNDECLARED_MOD_DIRS`` when it is
            unset or outside the asset.
    """

    population_type: str
    hoc_dir: str | None
    mod_dirs: tuple[str, ...]


@dataclass
class TemplateModel:
    """One cell template (``model_template`` value) read from the circuit's files.

    Attributes:
        biophysics: The parsed hoc file.
        mechanisms: Parsed mod files keyed by mechanism suffix, NEURON built-ins excluded.
    """

    biophysics: HocBiophysics
    mechanisms: dict[str, ModMechanism]


def _get_circuit_asset(
    db_client: entitysdk.client.Client,
    circuit_id: str,
) -> tuple[Circuit, Asset]:
    """Get circuit entity and its sonata_circuit directory asset.

    The asset object, not its id, is passed on to ``fetch_file``: given an id, entitysdk
    fetches the asset's metadata again before every file, one extra request per file.
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
    """Stage a single file from the circuit's sonata_circuit asset into temp_dir.

    A file already staged in this temp_dir is reused: one request stages each path once.

    Raises:
        ValueError: ``asset_path`` is absolute or climbs out of the asset with ``..``.
            Paths are built from circuit content, so they are untrusted.
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
    # Comments may hold non-UTF-8 author names; only ASCII syntax is read.
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
    """Stage the files needed to resolve a neuron set against a circuit.

    Copies circuit_config.json as a real file (not a symlink) so that
    $BASE_DIR resolves to the temp directory rather than the S3 cache.
    node_sets.json and the nodes.h5 of every population (or only those whose type is in
    ``population_types``) are then staged concurrently on ``FETCH_POOL`` with
    link_or_download (symlinks to the S3 cache where available, downloads otherwise).
    A missing node_sets.json is tolerated; it is optional in SONATA. With
    ``stage_nodes=False`` neither is fetched: the nodes paths are returned for the caller
    to read another way.

    Returns:
        The config path, population -> nodes.h5 asset path for the selected populations,
        and population -> type and hoc / mod directories for every population. An
        ``EntitySDKError`` from fetching circuit_config.json or a nodes.h5 propagates.
    """
    # Copy config as a real file so $BASE_DIR resolves to temp_dir
    config_path = _stage_file(
        db_client,
        circuit_id,
        asset,
        temp_dir_path,
        "circuit_config.json",
        strategy=FetchFileStrategy.copy_or_download,
    )

    # Load circuit — $BASE_DIR now resolves to temp_dir because config is a real file.
    # Only the config is read here; node sets and nodes are read later, after staging.
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

    def stage(asset_path: str) -> Path:
        return _stage_file(db_client, circuit_id, asset, temp_dir_path, asset_path)

    def stage_node_sets() -> None:
        # Needed for neuron set resolution, but optional in SONATA.
        try:
            stage("node_sets.json")
        except Exception:  # ruff: ignore[blind-except]
            L.debug("node_sets.json not available, continuing without it")

    if stage_nodes:
        # Independent files: fetch together. A failed nodes.h5 re-raises from result().
        futures = [FETCH_POOL.submit(stage_node_sets)]
        futures.extend(FETCH_POOL.submit(stage, path) for path in pop_to_nodes_path.values())
        for future in futures:
            future.result()

    return config_path, pop_to_nodes_path, pop_to_model_dirs


def _public_reason(err: object) -> str:
    """Why a template could not be read, safe to return to the API caller.

    Only our own parse errors are quoted. Other errors (HTTP, filesystem) may carry
    signed storage URLs, so the caller gets the error type and the log gets the rest.
    """
    return (
        str(err)
        if isinstance(err, HocTemplateError)
        else f"files not readable ({type(err).__name__})"
    )


def _fetch_and_parse[K: Hashable, T](
    keys: Iterable[K],
    parse: Callable[[K, str], T],
    stage: Callable[[K], Path],
) -> dict[K, T | Exception]:
    """Stage and parse one file per key concurrently on ``FETCH_POOL``.

    Args:
        keys: What to fetch, as ``stage`` understands it; duplicates are fetched once.
        parse: Turns a key and its file's text into the parsed form.
        stage: Stages the file of one key and returns the local file.

    Returns:
        Key -> parsed result, or the exception that stopped it. Failures are returned so
        one bad file does not fail the other templates.
    """

    def one(key: K) -> T | Exception:
        try:
            return parse(key, _read_model_file(stage(key)))
        except Exception as err:  # ruff: ignore[blind-except]
            L.warning("Could not read circuit file %s", key, exc_info=True)
            return err

    unique = list(dict.fromkeys(keys))
    # Each fetch is a few HTTP round trips (API, redirect, storage); threads overlap them.
    return dict(zip(unique, FETCH_POOL.map(one, unique), strict=True))


def _parse_model_file(path: str, text: str) -> HocBiophysics | ModMechanism:
    """Parse a hoc or mod file, chosen by the file extension."""
    return read_hoc_biophysics(text) if path.endswith(".hoc") else read_mod_mechanism(text)


def _asset_files(
    db_client: entitysdk.client.Client, circuit_id: str, asset: Asset
) -> dict[str, int] | Exception:
    """Return asset path -> size in bytes for every file of the circuit, or the error.

    One request lists the whole asset. The result serves two readers: the ``nodes.h5``
    sizes let the byte-range read skip a ``HEAD`` request (storage refuses ``HEAD`` on
    presigned URLs), and the paths show where the ``.mod`` files are.

    A failure is logged and returned, not raised, like a failed file in
    ``_fetch_and_parse``: ``nodes.h5`` is then downloaded whole, and every template
    reports the reason.
    """
    try:
        listing = db_client.list_directory(
            entity_id=UUID(circuit_id), entity_type=Circuit, asset_id=asset.id
        )
    except Exception as err:  # ruff: ignore[blind-except]
        L.warning("Could not list the files of circuit %s", circuit_id, exc_info=True)
        return err
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
    """The mod files of one mechanisms directory, found by the mechanism each defines.

    NEURON names a mechanism by the ``SUFFIX`` written inside the file, not by the file
    name (rCA1's ``kdrbca1.mod`` defines ``kdrb``). So every mod file of the directory is
    read, and indexed by its ``SUFFIX``.

    Attributes:
        mechanisms: SUFFIX -> parsed mod file, or the error when two files define it.
        unread: Errors of files that could not be fetched; which mechanisms they define
            is unknown, so a mechanism missing from ``mechanisms`` is reported with one.
    """

    mechanisms: dict[str, ModMechanism | Exception]
    unread: list[Exception]

    def lookup(self, channel: str) -> ModMechanism | str:
        """The mechanism's parsed mod file, or the reason there is none."""
        mod = self.mechanisms.get(channel)
        if isinstance(mod, ModMechanism):
            return mod
        if mod is not None:
            return _public_reason(mod)
        if self.unread:
            return _public_reason(self.unread[0])
        return f"no mod file in the circuit defines mechanism '{channel}'"


def _mod_index(
    mod_paths: Iterable[str], files: dict[str, HocBiophysics | ModMechanism | Exception]
) -> ModIndex:
    """Index the parsed mod files of one directory by their ``SUFFIX``.

    A file that is not a mechanism this module reads (it has no ``SUFFIX`` line) is
    skipped. A file that could not be fetched or is too large is kept in ``unread``.
    """
    index = ModIndex(mechanisms={}, unread=[])
    for path in mod_paths:
        parsed = files[path]
        if isinstance(parsed, ModMechanism):
            if parsed.suffix in index.mechanisms:
                msg = f"mechanism '{parsed.suffix}' is defined by more than one mod file"
                index.mechanisms[parsed.suffix] = HocTemplateError(msg)
            else:
                index.mechanisms[parsed.suffix] = parsed
        elif isinstance(parsed, Exception) and not isinstance(parsed, HocTemplateError):
            index.unread.append(parsed)
    return index


def _template_hoc_paths(
    templates_per_population: dict[str, set[str]],
    pop_to_model_dirs: dict[str, PopulationModelDirs],
) -> tuple[dict[str, str], dict[str, PopulationModelDirs], dict[str, str]]:
    """Find each template's hoc file and model directories.

    A template name is assumed to mean the same hoc file in every population that uses
    it, so the first population that lists it decides its directories.

    Returns:
        Template -> hoc asset path, template -> its population's directories, and
        template -> why it has no hoc path (its population declares no hoc directory).
    """
    hoc_paths: dict[str, str] = {}
    template_dirs: dict[str, PopulationModelDirs] = {}
    reasons: dict[str, str] = {}
    for population, templates in templates_per_population.items():
        dirs = pop_to_model_dirs[population]
        for template in templates - template_dirs.keys():
            template_dirs[template] = dirs
            if dirs.hoc_dir is None:
                reasons[template] = "population has no biophysical_neuron_models_dir"
            else:
                name = template.rsplit(":", maxsplit=1)[-1]
                hoc_paths[template] = f"{dirs.hoc_dir}/{name}.hoc"
    return hoc_paths, template_dirs, reasons


def _mod_paths_per_dirs(
    candidates: Iterable[tuple[str, ...]], mod_files_by_dir: dict[str, list[str]]
) -> dict[tuple[str, ...], list[str]]:
    """Pick, for each list of candidate directories, the mod files of the first one.

    The first candidate that holds any ``.mod`` file wins; none gives an empty list.
    """
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
    asset_files: dict[str, int] | Exception,
) -> dict[str, TemplateModel | str]:
    """Read every template from its hoc file and the mod files of its directory.

    The listing gives the mod file paths, then all hoc and mod files are fetched and parsed
    in one parallel batch. Reading the whole mechanisms directory (a few dozen small files)
    costs less than looking for each mechanism's file one by one, and the mod files do not
    depend on the hoc files, so nothing waits. Units the mod files leave undeclared are
    then filled from the database (``_fill_units_from_database``).

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        asset: The circuit's ``sonata_circuit`` asset.
        temp_dir_path: Directory where files are staged for this request.
        templates_per_population: Population -> the templates to read.
        pop_to_model_dirs: Population -> where its hoc and mod files are.
        asset_files: The asset listing from ``_asset_files``, or why it failed.

    Returns:
        Template -> its model, or the reason it could not be read.
    """

    def stage(path: str) -> Path:
        return _stage_file(db_client, circuit_id, asset, temp_dir_path, path)

    hoc_paths, template_dirs, reasons = _template_hoc_paths(
        templates_per_population, pop_to_model_dirs
    )
    result: dict[str, TemplateModel | str] = dict(reasons)
    if not hoc_paths:
        return result
    if isinstance(asset_files, Exception):
        return result | dict.fromkeys(hoc_paths, _public_reason(asset_files))

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
    _fill_units_from_database(
        db_client,
        [
            mechanism
            for model in result.values()
            if isinstance(model, TemplateModel)
            for mechanism in model.mechanisms.values()
        ],
    )
    return result


def _undeclared_units(mechanism: ModMechanism) -> list[str]:
    """Variables shown in the response whose unit the mod file does not declare."""
    shown = (*mechanism.settable_range_variables, *mechanism.global_variables)
    return [name for name in shown if name not in mechanism.units]


def _normalized_unit(unit: str) -> str:
    """Write a unit so that equal units compare equal: ``mho`` is the old name of ``S``."""
    return unit.replace("mho", "S").replace(" ", "")


def _entity_units(model: IonChannelModel) -> dict[str, str]:
    """Variable -> unit declared by an ion channel model entity (empty units skipped)."""
    block = model.neuron_block
    entries = [*(block.range or []), *(block.global_ or [])] if block else []
    return {name: unit for entry in entries for name, unit in entry.items() if unit}


def _database_units(mechanism: ModMechanism, models: Iterable[IonChannelModel]) -> dict[str, str]:
    """Find units for the mechanism's undeclared variables in entities with its suffix.

    Two mechanisms can share a suffix and still differ, so an entity is used only when
    every unit that both it and the mod file declare is the same. A missing unit is taken
    only when all those entities give the same one; otherwise it stays empty.

    Example:
        rCA1's ``kmb.mod`` declares ``gbar (mho/cm2)`` but no unit for ``tau``. An entity
        with ``gbar: S/cm2`` and ``tau: ms`` matches (``mho`` is ``S``), so ``tau`` gets
        ``ms``. An entity with ``gbar: mV`` is another mechanism and is ignored.

    Returns:
        Variable -> unit, only for the variables a unit was found for.
    """
    declared = {name: _normalized_unit(unit) for name, unit in mechanism.units.items()}
    missing = _undeclared_units(mechanism)
    # Missing variable -> {normalized unit: unit as written}, over the matching entities.
    found: dict[str, dict[str, str]] = defaultdict(dict)
    for model in models:
        units = _entity_units(model)
        if any(_normalized_unit(units[n]) != u for n, u in declared.items() if n in units):
            continue  # same suffix, different mechanism
        for name in missing:
            if name in units:
                found[name][_normalized_unit(units[name])] = units[name]
    return {name: next(iter(units.values())) for name, units in found.items() if len(units) == 1}


def _fill_units_from_database(
    db_client: entitysdk.client.Client, mechanisms: Iterable[ModMechanism]
) -> None:
    """Fill the units the mod files leave undeclared, from ion channel model entities.

    Some circuits' mod files declare no unit for some variables (the rCA1 circuits miss
    15, such as ``tau_kmb``), while the database entity of the same mechanism has it.
    The ``mechanisms`` are updated in place.

    There is one search per suffix that misses a unit, all sent in parallel on
    ``FETCH_POOL``. One search for all suffixes is not possible: entitycore filters one
    ``nmodl_suffix`` per request, and searching by name would miss a third of the
    entities, whose name differs from their suffix. A failed search is logged and leaves
    the units empty: a unit is shown to the user, it is not worth failing the template.
    """
    # The same parsed mod file is shared by every template that inserts it, so it can
    # appear several times; filling it again gives the same units.
    by_suffix: dict[str, list[ModMechanism]] = defaultdict(list)
    for mechanism in mechanisms:
        if _undeclared_units(mechanism):
            by_suffix[mechanism.suffix].append(mechanism)

    def search(suffix: str) -> list[IonChannelModel] | Exception:
        try:
            return db_client.search_entity(
                entity_type=IonChannelModel, query={"nmodl_suffix": suffix}
            ).all()
        except Exception as err:  # ruff: ignore[blind-except]
            L.warning("Could not search ion channel models for %s", suffix, exc_info=True)
            return err

    for suffix, models in zip(by_suffix, FETCH_POOL.map(search, by_suffix), strict=True):
        if isinstance(models, Exception):
            continue
        for mechanism in by_suffix[suffix]:
            mechanism.units.update(_database_units(mechanism, models))


def _template_model(biophysics: HocBiophysics, index: ModIndex) -> TemplateModel | str:
    """Join a parsed hoc file with the mod files of the mechanisms it inserts.

    Returns:
        The template's model, or the reason when one mechanism has no usable mod file.
    """
    mechanisms: dict[str, ModMechanism] = {}
    for channel in sorted(biophysics.mod_file_mechanisms):
        mod = index.lookup(channel)
        if isinstance(mod, str):
            return mod
        mechanisms[channel] = mod
    return TemplateModel(biophysics=biophysics, mechanisms=mechanisms)


def _unique_templates(group: h5py.Group) -> set[str] | None:
    """Return the distinct, non-empty ``model_template`` values of one population.

    Only the ``model_template`` column is read. Large circuits store it as a SONATA
    enumeration: one small integer per node plus an ``@library`` list of the names, so
    the integers are read and only the distinct ones are looked up. The same code works
    on a local file and on a remote one read by byte ranges.

    Args:
        group: The population's ``nodes/<population>/0`` group.

    Returns:
        The template names, or None when the population has no ``model_template``.
    """
    if "model_template" not in group:
        return None
    column = group["model_template"]
    if "@library" in group and "model_template" in group["@library"]:
        library = group["@library/model_template"].asstr()[:]
        templates = {str(library[index]) for index in np.unique(column[:])}
    else:
        templates = {str(template) for template in column.asstr()[:]}
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
    """Return one population's distinct ``model_template`` values, reading little data.

    The first way that works is used:

    1. A symlink to the mounted asset store: no transfer at all.
    2. Byte-range reads of only the ``model_template`` column (a 743 MB ``nodes.h5``
       costs about 34 MB). Needs the file ``size`` from the listing.
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
                with open_asset_h5(
                    db_client,
                    entity_id=UUID(circuit_id),
                    entity_type=Circuit,
                    asset_id=asset.id,
                    asset_path=nodes_relative,
                    size=size,
                ) as h5:
                    return _unique_templates(h5[f"nodes/{population}/0"])
            except Exception:  # ruff: ignore[blind-except]
                L.warning(
                    "Partial read of %s failed, downloading it", nodes_relative, exc_info=True
                )
        path = _stage_file(db_client, circuit_id, asset, temp_dir_path, nodes_relative)
    with h5py.File(path, "r") as h5:
        return _unique_templates(h5[f"nodes/{population}/0"])


def _stage_circuit_for_neuron_set_resolution(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    circuit_entity: Circuit,
    asset: Asset,
    neuron_set: NeuronSet,
) -> tuple[list[str], TemplateNodes, dict[str, TemplateModel | str]]:
    """Stage circuit files, resolve neuron set to node IDs, read model_template.

    Stages circuit_config.json, node_sets.json, and the nodes.h5 for each population
    the neuron set spans, then resolves the neuron set (every scan value, see
    ``get_expanded_neuron_ids``) and reads model_template
    for the resulting node IDs across all populations. The hoc and mod files of
    every template found are read in the same staging directory.

    Returns:
        Tuple of (population_names, {(population, node_id): model_template},
        {model_template: TemplateModel or reason}) where the template dict is
        keyed by population-qualified node IDs to avoid collisions between
        populations with overlapping local node IDs.
    """
    # Listed while the circuit is staged and the neuron set resolved: no extra wait.
    listing = FETCH_POOL.submit(_asset_files, db_client, circuit_id, asset)
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
        if not ids_per_population:
            msg = f"Neuron set resolved to no node IDs for circuit {circuit_id}."
            raise ValueError(msg)

        node_to_template: TemplateNodes = {}
        populations: list[str] = []
        templates_per_population: dict[str, set[str]] = {}

        for population, node_ids in ids_per_population.items():
            if not node_ids:
                continue

            populations.append(population)

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

            templates = pop_obj.get_attribute("model_template", node_ids)
            node_to_template.update(
                zip(
                    [(population, nid) for nid in node_ids],
                    templates,
                    strict=True,
                )
            )
            templates_per_population[population] = set(templates)

        if not populations:
            msg = f"Neuron set resolved to no node IDs for circuit {circuit_id}."
            raise ValueError(msg)

        template_models = _read_template_models(
            db_client,
            circuit_id,
            asset,
            temp_dir_path,
            templates_per_population,
            pop_to_model_dirs,
            listing.result(),
        )

    return populations, node_to_template, template_models


def _collect_all_templates(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    asset: Asset,
) -> tuple[dict[str, set[str]], dict[str, TemplateModel | str]]:
    """Return every template of every biophysical population, with its model.

    Virtual populations are skipped: they have no ``model_template``, and their
    ``nodes.h5`` can be large. Populations are read one after the other, since a circuit
    has one or two biophysical ones. The asset listing runs while the config is fetched.

    Returns:
        Population -> its templates, and template -> its model or the reason it failed.
    """
    # Listed while circuit_config.json is fetched: no extra wait.
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
        sizes = {} if isinstance(asset_files, Exception) else asset_files
        templates_per_population: dict[str, set[str]] = {}
        for population, nodes_relative in pop_to_nodes_path.items():
            templates = _population_templates(
                db_client,
                circuit_id,
                asset,
                temp_dir_path,
                population,
                nodes_relative,
                sizes.get(nodes_relative),
            )
            if templates is not None:
                templates_per_population[population] = templates
        template_models = _read_template_models(
            db_client,
            circuit_id,
            asset,
            temp_dir_path,
            templates_per_population,
            pop_to_model_dirs,
            asset_files,
        )
    return templates_per_population, template_models


def get_expanded_neuron_ids(neuron_set: NeuronSet, circuit: ObiCircuit) -> dict[str, list[int]]:
    """Resolve a neuron set to node IDs per population, expanding swept fields.

    A list in a block field is a parameter scan dimension: in a ScanConfig it produces
    one single config per value. Declared endpoints receive no such expansion, so the
    sweep is expanded here instead and the per-coordinate node IDs are unioned per
    population — equivalent to resolving every scan point and merging its selection.

    Args:
        neuron_set: Neuron set to resolve (fields may hold swept list values).
        circuit: The circuit to resolve against.

    Returns:
        Dict mapping population name to the sorted union of node IDs across all
        expanded single-valued neuron sets.
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
    """Resolve a neuron set to node IDs for a circuit.

    Swept fields of the neuron set are expanded and the resulting node IDs are
    unioned per population.

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        neuron_set: Neuron set to resolve.

    Returns:
        Dict mapping population name to list of node IDs.
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
) -> tuple[dict[str, dict], dict[str, str], list[str]]:
    """Build one group of variables per template, from its circuit files.

    Returns:
        The groups, in the shape ``_build_emodel_groups`` returns; template -> reason for
        the templates that could not be read; and warnings for values not readable.
    """
    groups: dict[str, dict] = {}
    failed: dict[str, str] = {}
    warnings: list[str] = []
    for template, node_keys in template_to_nodes.items():
        model = template_models.get(template, "circuit files not read")
        if isinstance(model, str):
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
) -> tuple[dict[str, dict], list[str]]:
    """Build groups from the circuit files, and from derivations for the templates left.

    Each template that needed the derivation, or had none, gets one warning with the
    reason its files could not be read.

    Returns:
        The groups, and the warnings.
    """
    template_to_nodes: dict[str, list[tuple[str, int]]] = {}
    for key, template in node_to_template.items():
        template_to_nodes.setdefault(template, []).append(key)

    groups, failed, warnings = _build_template_groups(template_models, template_to_nodes)
    if not failed:
        return groups, warnings

    # Fallback kept for circuits whose files cannot be read this way.
    fallback_nodes = {key: tpl for key, tpl in node_to_template.items() if tpl in failed}
    label_to_emodel_id = _fetch_emodel_derivation_mapping(db_client, circuit_id)
    node_key_to_emodel, unmatched = _match_templates_to_emodels(fallback_nodes, label_to_emodel_id)
    groups.update(_build_emodel_groups(db_client, node_key_to_emodel, label_to_emodel_id))
    for template, reason in sorted(failed.items()):
        outcome = (
            "No derivation found for model_template"
            if template in unmatched
            else "used the emodel_circuit derivation instead"
        )
        warnings.append(f"{outcome}: {template} (circuit files: {reason})")
    return groups, warnings


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
    """Group nodes by emodel and fetch mechanism variables for each."""
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
    """Compute the intersection of mechanism variables across all emodel groups.

    Returns only channels and variables that are present in ALL emodel groups.
    For limits, takes the most restrictive range (max of lower bounds, min of upper bounds).
    For section_lists, takes the intersection across groups.

    Special case: if there is only one emodel group, returns its full variable set
    with original values preserved.
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

            variables[var_name] = MechanismVariableDetail(
                units=all_details[0].units,
                limits=merged_limits,
                variable_type=all_details[0].variable_type,
                section_lists_original_values=dict.fromkeys(common_section_lists),
            )

        result[channel] = IonChannelVariables(
            section_lists=common_section_lists,
            entity_id=None,
            variables=variables,
        )

    return result


def _empty_response(warning: str) -> dict:
    """A response with no variables and one warning."""
    return {
        "entity_type": "circuit",
        "populations": None,
        CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL: {},
        "warnings": [warning],
    }


def get_circuit_manipulation_properties(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    neuron_set: NeuronSet | None = None,
) -> dict:
    """Get neuronal manipulation properties for a circuit + neuron set.

    Two modes:
    1. neuron_set=None: every model_template of every biophysical population.
    2. neuron_set provided: Stage files, resolve neuron set, read model_template.

    Each template's variables come from its hoc and mod files inside the circuit.
    Templates whose files cannot be read fall back to the emodel_circuit derivation.

    Returns the intersection (common) of mechanism variables across all templates
    in the selection.

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        neuron_set: Neuron set to resolve (may span multiple populations).

    Returns:
        Dict with entity_type, populations, mechanism_variables_by_ion_channel,
        and optional warnings. Each template that needed the derivation fallback, or
        could not be resolved at all, gets one warning with the reason.

    A ``ValueError`` propagates when the circuit has no single sonata_circuit asset (in
    both modes), the neuron set resolves to no nodes, or a selected population has no
    model_template; the endpoint maps it to HTTP 400.
    """
    resolved_populations: list[str] | None = None
    circuit_entity, asset = _get_circuit_asset(db_client, circuit_id)

    if neuron_set is None:
        try:
            templates_per_population, template_models = _collect_all_templates(
                db_client, circuit_id, asset
            )
        except Exception as err:  # ruff: ignore[blind-except]
            # Circuit files unreadable: the derivation path is all that is left.
            L.warning("Could not read templates of circuit %s", circuit_id, exc_info=True)
            label_to_emodel_id = _fetch_emodel_derivation_mapping(db_client, circuit_id)
            if not label_to_emodel_id:
                return _empty_response(
                    f"Circuit {_public_reason(err)}."
                    " No emodel_circuit derivations found for this circuit."
                )
            templates_per_population = {"__derivations__": set(label_to_emodel_id)}
            template_models: dict[str, TemplateModel | str] = dict.fromkeys(
                label_to_emodel_id, _public_reason(err)
            )
        node_to_template: TemplateNodes = {
            (population, index): template
            for population, templates in templates_per_population.items()
            for index, template in enumerate(sorted(templates))
        }
        if not node_to_template:
            return _empty_response("No population with a model_template found in this circuit.")
    else:
        resolved_populations, node_to_template, template_models = (
            _stage_circuit_for_neuron_set_resolution(
                db_client,
                circuit_id,
                circuit_entity,
                asset,
                neuron_set,
            )
        )

    emodel_groups, warning_messages = _build_groups_with_fallback(
        db_client, circuit_id, node_to_template, template_models
    )

    common_vars = _compute_common_mechanism_variables(emodel_groups)

    if not common_vars and emodel_groups:
        warning_messages.append(
            "No common mechanism variables found across the selected neurons' emodels."
        )

    return {
        "entity_type": "circuit",
        "populations": resolved_populations,
        CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL: common_vars,
        "warnings": warning_messages or None,
    }
