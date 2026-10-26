"""Neuronal manipulation properties for circuits.

Provides logic to:
- Resolve a neuron set to node IDs for a circuit.
- Read model_template property for selected node IDs.
- Read each template's mechanism variables from the circuit's hoc and mod files.
- Fall back to emodel_circuit derivations for templates whose files cannot be read.
- Compute the intersection (common) of mechanism variables across all templates.
- Return a flat response matching the MEModel response shape.

See ``docs/neuronal-manipulation-properties.md`` for the data flow and its limits.
"""

from __future__ import annotations

import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import numpy as np
from bluepysnap import Circuit as SnapCircuit
from entitysdk.models import Derivation as DerivationModel
from entitysdk.models.circuit import Circuit
from entitysdk.types import FetchFileStrategy
from libsonata import NodeStorage

from obi_one.scientific.library.circuit import Circuit as ObiCircuit
from obi_one.scientific.library.circuit_constants import TYPES_OF_BIOPHYS_NODES
from obi_one.scientific.library.emodel_circuit_files import (
    PAS_MECHANISM,
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
    from collections.abc import Callable, Iterable

    import entitysdk.client
    from libsonata import NodePopulation

    from obi_one.scientific.blocks.neuron_sets.base import NeuronSet

L = logging.getLogger(__name__)

# One pool for every request in the process: the API serves many requests at once, so a
# per-request pool would multiply threads and open connections with the request count.
# 16 lets one request fetch a typical template's mod files in a single round; under load,
# fetches queue here instead of piling onto entitycore and storage.
# ponytail: fixed process-wide cap; make it a setting if the API's request concurrency
# or the entitycore connection limits change.
FETCH_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="circuit-file-fetch")
# hoc and mod files are a few KB to tens of KB; anything far larger is not a cell model
# and is refused before it is read into memory.
MAX_MODEL_FILE_BYTES = 1_000_000

# (population, node_id) -> model_template, or -> EModel ID after derivation matching.
TemplateNodes = dict[tuple[str, int], str]


@dataclass
class PopulationModelDirs:
    """Where a population's cell templates and mechanisms live inside the circuit asset.

    Attributes:
        population_type: SONATA population type, e.g. ``biophysical`` or ``virtual``.
        hoc_dir: ``biophysical_neuron_models_dir`` as an asset path; None when unset or
            outside the asset.
        mod_dir: ``mechanisms_dir`` as an asset path; None when unset or outside the asset.
    """

    population_type: str
    hoc_dir: str | None
    mod_dir: str | None


@dataclass
class TemplateModel:
    """One cell template (``model_template`` value) read from the circuit's files.

    Attributes:
        biophysics: The parsed hoc file.
        mechanisms: Parsed mod files keyed by mechanism suffix, ``pas`` excluded.
    """

    biophysics: HocBiophysics
    mechanisms: dict[str, ModMechanism]


def _get_circuit_asset(
    db_client: entitysdk.client.Client,
    circuit_id: str,
) -> tuple[Circuit, UUID]:
    """Get circuit entity and its sonata_circuit directory asset ID."""
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

    asset_id = directory_assets[0].id
    if asset_id is None:
        msg = f"Circuit {circuit_id} sonata_circuit asset has no ID."
        raise ValueError(msg)

    return circuit_entity, asset_id


def _stage_file(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    asset_id: UUID,
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
        asset_id=asset_id,
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
    asset_id: UUID,
    temp_dir_path: Path,
) -> tuple[Path, dict[str, str], dict[str, PopulationModelDirs]]:
    """Stage the files needed to resolve a neuron set against a circuit.

    Copies circuit_config.json as a real file (not a symlink) so that
    $BASE_DIR resolves to the temp directory rather than the S3 cache.
    node_sets.json and every nodes.h5 are then staged concurrently on ``FETCH_POOL``
    with link_or_download (symlinks to the S3 cache where available, downloads
    otherwise). A missing node_sets.json is tolerated; it is optional in SONATA.

    Returns:
        The config path, population -> nodes.h5 asset path, and population ->
        type and hoc / mod directories. An ``EntitySDKError`` from fetching
        circuit_config.json or a nodes.h5 propagates.
    """
    # Copy config as a real file so $BASE_DIR resolves to temp_dir
    config_path = _stage_file(
        db_client,
        circuit_id,
        asset_id,
        temp_dir_path,
        "circuit_config.json",
        strategy=FetchFileStrategy.copy_or_download,
    )

    # Load circuit — $BASE_DIR now resolves to temp_dir because config is a real file.
    # Only the config is read here; node sets and nodes are read later, after staging.
    snap_circuit = SnapCircuit(str(config_path))

    pop_to_nodes_path = {
        population: str(
            Path(snap_circuit.nodes[population].h5_filepath).resolve().relative_to(temp_dir_path)
        )
        for population in snap_circuit.nodes.population_names
    }

    def stage(asset_path: str) -> Path:
        return _stage_file(db_client, circuit_id, asset_id, temp_dir_path, asset_path)

    def stage_node_sets() -> None:
        # Needed for neuron set resolution, but optional in SONATA.
        try:
            stage("node_sets.json")
        except Exception:  # ruff: ignore[blind-except]
            L.debug("node_sets.json not available, continuing without it")

    # Independent files: fetch together. A failed nodes.h5 re-raises from result().
    futures = [FETCH_POOL.submit(stage_node_sets)]
    futures.extend(FETCH_POOL.submit(stage, path) for path in pop_to_nodes_path.values())
    for future in futures:
        future.result()

    pop_to_model_dirs: dict[str, PopulationModelDirs] = {}
    for population in pop_to_nodes_path:
        pop_config = snap_circuit.nodes[population].config
        pop_to_model_dirs[population] = PopulationModelDirs(
            population_type=pop_config.get("type", ""),
            hoc_dir=_relative_dir(pop_config.get("biophysical_neuron_models_dir"), temp_dir_path),
            mod_dir=_relative_dir(pop_config.get("mechanisms_dir"), temp_dir_path),
        )

    return config_path, pop_to_nodes_path, pop_to_model_dirs


def _public_reason(err: Exception) -> str:
    """Why a template could not be read, safe to return to the API caller.

    Only our own parse errors are quoted. Other errors (HTTP, filesystem) may carry
    signed storage URLs, so the caller gets the error type and the log gets the rest.
    """
    return (
        str(err)
        if isinstance(err, HocTemplateError)
        else f"files not readable ({type(err).__name__})"
    )


def _fetch_and_parse[T](
    paths: Iterable[str],
    parse: Callable[[str], T],
    stage: Callable[[str], Path],
) -> dict[str, T | Exception]:
    """Stage and parse each asset path concurrently on ``FETCH_POOL``.

    Args:
        paths: Asset paths; duplicates are fetched once.
        parse: Turns a file's text into its parsed form.
        stage: Stages one asset path and returns the local file.

    Returns:
        Asset path -> parsed result, or the exception that stopped it. Failures are
        returned so one bad file does not fail the other templates.
    """

    def one(path: str) -> T | Exception:
        try:
            return parse(_read_model_file(stage(path)))
        except Exception as err:  # ruff: ignore[blind-except]
            L.warning("Could not read circuit file %s", path, exc_info=True)
            return err

    unique = sorted(set(paths))
    # Each fetch is a few HTTP round trips (API, redirect, storage); threads overlap them.
    return dict(zip(unique, FETCH_POOL.map(one, unique), strict=True))


def _read_template_models(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    asset_id: UUID,
    temp_dir_path: Path,
    templates_per_population: dict[str, set[str]],
    pop_to_model_dirs: dict[str, PopulationModelDirs],
) -> dict[str, TemplateModel | str]:
    """Read every template from its hoc file and the mod files it needs.

    Two concurrent batches: all hoc files, then the union of their mod files, so a mod
    file shared by several templates is fetched and parsed once.

    A template name is assumed to mean the same hoc file in every population that uses
    it; the first population listing it decides the directories.

    Returns:
        Template -> its model, or the reason it could not be read.
    """

    def stage(path: str) -> Path:
        return _stage_file(db_client, circuit_id, asset_id, temp_dir_path, path)

    result: dict[str, TemplateModel | str] = {}
    hoc_paths: dict[str, str] = {}
    template_dirs: dict[str, PopulationModelDirs] = {}
    for population, templates in templates_per_population.items():
        dirs = pop_to_model_dirs[population]
        for template in templates - template_dirs.keys():
            template_dirs[template] = dirs
            if dirs.hoc_dir is None:
                result[template] = "population has no biophysical_neuron_models_dir"
            else:
                name = template.rsplit(":", maxsplit=1)[-1]
                hoc_paths[template] = f"{dirs.hoc_dir}/{name}.hoc"

    hocs = _fetch_and_parse(hoc_paths.values(), read_hoc_biophysics, stage)

    mod_paths: dict[str, dict[str, str]] = {}
    for template, hoc_path in hoc_paths.items():
        biophysics = hocs[hoc_path]
        if isinstance(biophysics, Exception):
            result[template] = _public_reason(biophysics)
            continue
        channels = biophysics.inserted_mechanisms - {PAS_MECHANISM}
        mod_dir = template_dirs[template].mod_dir
        if channels and mod_dir is None:
            result[template] = "population has no mechanisms_dir"
            continue
        mod_paths[template] = {channel: f"{mod_dir}/{channel}.mod" for channel in channels}

    mods = _fetch_and_parse(
        (path for paths in mod_paths.values() for path in paths.values()),
        read_mod_mechanism,
        stage,
    )

    for template, paths in mod_paths.items():
        result[template] = _template_model(hocs[hoc_paths[template]], paths, mods)
    return result


def _template_model(
    biophysics: HocBiophysics | Exception,
    mod_paths: dict[str, str],
    mods: dict[str, ModMechanism | Exception],
) -> TemplateModel | str:
    """Join a parsed hoc file with its parsed mod files, or say why it cannot be."""
    if isinstance(biophysics, Exception):
        return _public_reason(biophysics)
    mechanisms: dict[str, ModMechanism] = {}
    for channel, path in mod_paths.items():
        mod = mods[path]
        if isinstance(mod, Exception):
            return _public_reason(mod)
        mechanisms[channel] = mod
    return TemplateModel(biophysics=biophysics, mechanisms=mechanisms)


def _unique_templates(pop_obj: NodePopulation) -> set[str]:
    """Distinct non-empty model_template values of a whole population.

    Large circuits store model_template as an enumeration (one small integer per node
    plus a value library); reading the integers avoids one Python string per node.
    """
    everyone = pop_obj.select_all()
    if "model_template" in pop_obj.enumeration_names:
        library = pop_obj.enumeration_values("model_template")
        indices = np.unique(pop_obj.get_enumeration("model_template", everyone))
        templates = {library[index] for index in indices}
    else:
        templates = set(pop_obj.get_attribute("model_template", everyone))
    return {template for template in templates if template}


def _stage_circuit_for_neuron_set_resolution(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    circuit_entity: Circuit,
    asset_id: UUID,
    neuron_set: NeuronSet,
) -> tuple[list[str], TemplateNodes, dict[str, TemplateModel | str]]:
    """Stage circuit files, resolve neuron set to node IDs, read model_template.

    Stages circuit_config.json, node_sets.json, and the nodes.h5 for each population
    the neuron set spans, then resolves the neuron set and reads model_template
    for the resulting node IDs across all populations. The hoc and mod files of
    every template found are read in the same staging directory.

    Returns:
        Tuple of (population_names, {(population, node_id): model_template},
        {model_template: TemplateModel or reason}) where the template dict is
        keyed by population-qualified node IDs to avoid collisions between
        populations with overlapping local node IDs.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir).resolve()

        config_path, pop_to_nodes_path, pop_to_model_dirs = _stage_circuit_for_neuron_set(
            db_client,
            circuit_id,
            asset_id,
            temp_dir_path,
        )

        obi_circuit = ObiCircuit(name=circuit_entity.name or circuit_id, path=str(config_path))

        ids_per_population: dict[str, list[int]] = neuron_set.get_neuron_ids(obi_circuit)
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
            asset_id,
            temp_dir_path,
            templates_per_population,
            pop_to_model_dirs,
        )

    return populations, node_to_template, template_models


def _collect_all_templates(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    asset_id: UUID,
) -> tuple[dict[str, set[str]], dict[str, TemplateModel | str]]:
    """Every model_template of every biophysical population, with its model."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir).resolve()
        _config_path, pop_to_nodes_path, pop_to_model_dirs = _stage_circuit_for_neuron_set(
            db_client,
            circuit_id,
            asset_id,
            temp_dir_path,
        )
        templates_per_population: dict[str, set[str]] = {}
        for population, nodes_relative in pop_to_nodes_path.items():
            if pop_to_model_dirs[population].population_type not in TYPES_OF_BIOPHYS_NODES:
                continue
            pop_obj = NodeStorage(str(temp_dir_path / nodes_relative)).open_population(population)
            if "model_template" in pop_obj.attribute_names:
                templates_per_population[population] = _unique_templates(pop_obj)
        template_models = _read_template_models(
            db_client,
            circuit_id,
            asset_id,
            temp_dir_path,
            templates_per_population,
            pop_to_model_dirs,
        )
    return templates_per_population, template_models


def get_circuit_node_ids(
    db_client: entitysdk.client.Client,
    circuit_id: str,
    neuron_set: NeuronSet,
) -> dict[str, list[int]]:
    """Resolve a neuron set to node IDs for a circuit.

    Args:
        db_client: entitysdk client.
        circuit_id: Circuit entity ID.
        neuron_set: Neuron set to resolve.

    Returns:
        Dict mapping population name to list of node IDs.
    """
    circuit_entity, asset_id = _get_circuit_asset(db_client, circuit_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir).resolve()

        config_path, _, _ = _stage_circuit_for_neuron_set(
            db_client,
            circuit_id,
            asset_id,
            temp_dir_path,
        )

        obi_circuit = ObiCircuit(name=circuit_entity.name or circuit_id, path=str(config_path))

        ids_per_population = neuron_set.get_neuron_ids(obi_circuit)

    return ids_per_population


def _build_template_groups(
    template_models: dict[str, TemplateModel | str],
    template_to_nodes: dict[str, list[tuple[str, int]]],
) -> tuple[dict[str, dict], dict[str, str], list[str]]:
    """Build one group per template from its circuit files.

    Returns:
        Groups in the shape ``_build_emodel_groups`` produces, the templates that could
        not be read with the reason, and warnings about values that could not be read.
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
    """Groups from circuit files first; the emodel_circuit derivation path for the rest."""
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

    A ``ValueError`` propagates when the circuit has no single sonata_circuit asset,
    the neuron set resolves to no nodes, or a selected population has no
    model_template; the endpoint maps it to HTTP 400.
    """
    resolved_populations: list[str] | None = None

    if neuron_set is None:
        try:
            _circuit_entity, asset_id = _get_circuit_asset(db_client, circuit_id)
            templates_per_population, template_models = _collect_all_templates(
                db_client, circuit_id, asset_id
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
        circuit_entity, asset_id = _get_circuit_asset(db_client, circuit_id)
        resolved_populations, node_to_template, template_models = (
            _stage_circuit_for_neuron_set_resolution(
                db_client,
                circuit_id,
                circuit_entity,
                asset_id,
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
