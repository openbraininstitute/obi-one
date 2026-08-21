"""Normalize IonChannelModel metadata and build BluePyEModel params definitions."""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
    REGIONAL_PARAMETER_LOCATIONS,
    STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS,
    OptimizationValue,
    ParametersSelection,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.section_lists import (
    DEFAULT_SECTION_LIST_CATALOG,
    SectionListName,
)

from .morphology_preflight import MorphologyCapabilities

if TYPE_CHECKING:
    from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID

VariableType = Literal["RANGE", "GLOBAL"]

L = logging.getLogger(__name__)

DEFAULT_BOUNDS_FALLBACKS: dict[str, tuple[float, float]] = {
    "g_pas": (1e-5, 6e-5),
    "e_pas": (-95.0, -60.0),
}


@dataclass(frozen=True)
class IonChannelVariable:
    """Normalized variable metadata from an IonChannelModel neuron block."""

    name: str
    source_name: str
    units: str | None
    variable_type: VariableType


@dataclass(frozen=True)
class NormalizedIonChannelModel:
    """Entity metadata required to compile a mechanism and its parameters."""

    entity_id: str
    name: str
    nmodl_suffix: str
    is_stochastic: bool
    is_ljp_corrected: bool
    temperature_celsius: int | None
    range_variables: tuple[IonChannelVariable, ...]
    global_variables: tuple[IonChannelVariable, ...]

    @property
    def variables(self) -> tuple[IonChannelVariable, ...]:
        """All RANGE and GLOBAL variables in metadata order."""
        return self.range_variables + self.global_variables

    def find_variable(self, name: str) -> IonChannelVariable | None:
        """Find a variable by its qualified or source NMODL name."""
        qualified_name = name
        if not name.endswith(f"_{self.nmodl_suffix}"):
            qualified_name = f"{name}_{self.nmodl_suffix}"
        for variable in self.variables:
            if variable.name in {name, qualified_name} or variable.source_name == name:
                return variable
        return None


def _read_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _normalize_variables(
    entries: Iterable[Any] | None,
    suffix: str,
    variable_type: VariableType,
) -> tuple[IonChannelVariable, ...]:
    variables: list[IonChannelVariable] = []
    seen: set[str] = set()
    for entry in entries or []:
        if isinstance(entry, Mapping):
            if "variable" in entry and "units" in entry:
                items = [(entry["variable"], entry.get("units"))]
            else:
                items = entry.items()
        else:
            entry_name = _read_field(entry, "name") or _read_field(entry, "variable")
            items = [(entry_name, _read_field(entry, "units"))]
        for raw_name, units in items:
            if not raw_name:
                continue
            source_name = str(raw_name)
            name = source_name if source_name.endswith(f"_{suffix}") else f"{source_name}_{suffix}"
            if name in seen:
                continue
            seen.add(name)
            variables.append(
                IonChannelVariable(
                    name=name,
                    source_name=source_name,
                    units=str(units) if units is not None else None,
                    variable_type=variable_type,
                )
            )
    return tuple(variables)


def normalize_ion_channel_model(
    entity: Any,
    *,
    entity_id: str | None = None,
) -> NormalizedIonChannelModel:
    """Normalize an EntitySDK IonChannelModel or compatible test double."""
    suffix = _read_field(entity, "nmodl_suffix")
    if not suffix:
        msg = "IonChannelModel metadata must include nmodl_suffix."
        raise ValueError(msg)
    resolved_entity_id = entity_id or _read_field(entity, "id")
    if not resolved_entity_id:
        msg = f"IonChannelModel '{suffix}' has no entity ID."
        raise ValueError(msg)
    neuron_block = _read_field(entity, "neuron_block")
    if neuron_block is None:
        msg = f"IonChannelModel '{suffix}' has no neuron_block metadata."
        raise ValueError(msg)
    global_entries = _read_field(neuron_block, "global_")
    if global_entries is None:
        global_entries = _read_field(neuron_block, "global")
    return NormalizedIonChannelModel(
        entity_id=str(resolved_entity_id),
        name=str(_read_field(entity, "name") or suffix),
        nmodl_suffix=str(suffix),
        is_stochastic=bool(_read_field(entity, "is_stochastic", default=False)),
        is_ljp_corrected=bool(_read_field(entity, "is_ljp_corrected", default=False)),
        temperature_celsius=_read_field(entity, "temperature_celsius"),
        range_variables=_normalize_variables(
            _read_field(neuron_block, "range"),
            str(suffix),
            "RANGE",
        ),
        global_variables=_normalize_variables(
            global_entries,
            str(suffix),
            "GLOBAL",
        ),
    )


def resolve_ion_channel_models(
    references: Iterable[IonChannelModelFromID],
    db_client: Any,
) -> dict[str, NormalizedIonChannelModel]:
    """Resolve selected IonChannelModel references and normalize their metadata."""
    normalized: dict[str, NormalizedIonChannelModel] = {}
    for reference in references:
        normalized[reference.id_str] = normalize_ion_channel_model(
            reference.entity(db_client=db_client),
            entity_id=reference.id_str,
        )
    return normalized


def fetch_variable_catalog(
    ion_channel_ids: Iterable[str],
    db_client: Any,
) -> dict[str, NormalizedIonChannelModel]:
    """Fetch and normalize the RANGE/GLOBAL/conductance variable catalog for entities.

    This is the single owner of the ``gNa`` → ``gNa_NaTg`` qualified-naming rule and
    the RANGE-vs-GLOBAL placement rule (:meth:`NormalizedIonChannelModel.find_variable`,
    used by ``_build_mechanism_parameters()`` / ``_build_global_parameters()``). UI
    clients must consume this catalog through the ``GET /declared/mapped-ion-channel-
    properties/emodel-optimization-variables`` endpoint rather than re-deriving
    qualified names from raw EntitySDK ``neuron_block`` data, so the naming rule
    cannot drift between the compiler and the form.

    Returns a mapping keyed by entity ID, matching the shape used internally by
    :func:`resolve_ion_channel_models`.
    """
    from entitysdk.models import IonChannelModel  # ruff: ignore[import-outside-top-level]

    catalog: dict[str, NormalizedIonChannelModel] = {}
    for ion_channel_id in ion_channel_ids:
        entity = db_client.get_entity(
            entity_id=ion_channel_id,
            entity_type=IonChannelModel,
        )
        catalog[str(ion_channel_id)] = normalize_ion_channel_model(
            entity,
            entity_id=str(ion_channel_id),
        )
    return catalog


def _validate_bounds(name: str, bounds: tuple[float, float]) -> None:
    if any(not math.isfinite(bound) for bound in bounds):
        msg = f"Bounds for parameter '{name}' must be finite."
        raise ValueError(msg)
    if bounds[0] > bounds[1]:
        msg = f"Lower bound exceeds upper bound for parameter '{name}'."
        raise ValueError(msg)


def _resolve_value(
    name: str,
    value: OptimizationValue,
    bounds_fallbacks: Mapping[str, tuple[float, float]],
    *,
    fallback_names: Iterable[str] = (),
) -> float | list[float]:
    if value.mode == "fixed":
        if value.value is None:
            msg = f"Fixed parameter '{name}' has no value."
            raise ValueError(msg)
        return value.value

    bounds = value.bounds
    fallback_name = None
    if bounds is None:
        seen: set[str] = set()
        candidates = (*fallback_names, name)
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate in bounds_fallbacks:
                fallback_name = candidate
                bounds = bounds_fallbacks[candidate]
                break
    if bounds is None:
        msg = (
            f"Optimizable parameter '{name}' has no bounds and no approved type-specific fallback."
        )
        raise ValueError(msg)
    _validate_bounds(fallback_name or name, bounds)
    if fallback_name is not None:
        L.info(
            "Using approved fallback bounds for '%s' from '%s': %s",
            name,
            fallback_name,
            bounds,
        )
    return [bounds[0], bounds[1]]


def _parameter_entry(
    name: str,
    location: str,
    value: OptimizationValue,
    *,
    mechanism: str | None = None,
    distribution: str | None = None,
    fallback_names: Iterable[str] = (),
    bounds_fallbacks: Mapping[str, tuple[float, float]],
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": name,
        "value": _resolve_value(
            name,
            value,
            bounds_fallbacks,
            fallback_names=fallback_names,
        ),
        "location": location,
    }
    if mechanism is not None:
        entry["mechanism"] = mechanism
    if distribution is not None and distribution != "uniform":
        entry["dist"] = distribution
    return entry


def _validate_location(location: str) -> None:
    if location not in REGIONAL_PARAMETER_LOCATIONS:
        msg = f"Unsupported regional parameter location: {location}."
        raise ValueError(msg)


def _location_sort_key(location: SectionListName) -> tuple[int, str]:
    """Order broad aliases before narrower section-list rows."""
    if location not in REGIONAL_PARAMETER_LOCATIONS:
        return (0, location)
    return (-len(DEFAULT_SECTION_LIST_CATALOG.expand(location)), location)


def _ordered_locations(locations: Iterable[SectionListName]) -> list[SectionListName]:
    return sorted(locations, key=_location_sort_key)


def _warn_overlapping_locations(
    rows: Mapping[tuple[str, str | None], list[SectionListName]],
) -> None:
    """Warn about intersecting rows while retaining legacy broad-first semantics."""
    for (name, mechanism), locations in rows.items():
        for index, location in enumerate(locations):
            current_sections = set(DEFAULT_SECTION_LIST_CATALOG.expand(location))
            for previous_location in locations[:index]:
                previous_sections = set(DEFAULT_SECTION_LIST_CATALOG.expand(previous_location))
                overlap = current_sections & previous_sections
                if not overlap:
                    continue
                target = f"{mechanism}.{name}" if mechanism is not None else name
                L.warning(
                    "Overlapping parameter rows for '%s' target '%s' and '%s' "
                    "(%s); preserving broad-to-specific ordering.",
                    target,
                    previous_location,
                    location,
                    sorted(overlap),
                )


def _validate_distribution(
    distribution: str,
    distributions: Mapping[str, Any],
) -> None:
    if distribution not in distributions:
        msg = f"Parameter references undeclared distribution '{distribution}'."
        raise ValueError(msg)


def _build_mechanisms(
    selection: ParametersSelection,
    normalized_models: Mapping[str, NormalizedIonChannelModel],
) -> list[dict[str, Any]]:
    """Compile the mechanisms array, always including the built-in ``pas`` mechanism.

    ``pas`` (NEURON's built-in passive leak channel, with ``g_pas`` conductance and
    ``e_pas`` reversal potential) has no EntityCore entity: it is not an
    IonChannelModel selection, it is always available. It is emitted on every
    location where ``g_pas`` or ``e_pas`` is configured, matching legacy EMC files
    where ``pas`` is declared alongside its passive parameters (e.g. under ``"all"``).
    """
    mechanisms: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for location in _ordered_locations(selection.mechanism_regions):
        _validate_location(location)
        for assignment in selection.mechanism_regions[location]:
            model = normalized_models.get(assignment.ion_channel_model.id_str)
            if model is None:
                msg = (
                    "No normalized metadata for IonChannelModel "
                    f"'{assignment.ion_channel_model.id_str}'."
                )
                raise ValueError(msg)
            key = (model.nmodl_suffix, location)
            if key in seen:
                msg = (
                    f"IonChannelModel '{model.nmodl_suffix}' is assigned more than once "
                    f"to region '{location}'."
                )
                raise ValueError(msg)
            seen.add(key)
            mechanisms.append(
                {
                    "name": model.nmodl_suffix,
                    "stochastic": model.is_stochastic,
                    "location": location,
                    "version": None,
                    "temperature": model.temperature_celsius,
                    "ljp_corrected": model.is_ljp_corrected,
                    "id": model.entity_id,
                }
            )

    passive_locations = {
        location
        for location, parameters in selection.base_parameters.items()
        if {"g_pas", "e_pas"} & set(parameters)
    }
    for location in _ordered_locations(passive_locations):
        key = ("pas", location)
        if key in seen:
            continue
        mechanisms.append(
            {
                "name": "pas",
                "stochastic": False,
                "location": location,
                "version": None,
                "temperature": None,
                "ljp_corrected": None,
                "id": None,
            }
        )
    return mechanisms


def _build_global_parameters(
    selection: ParametersSelection,
    normalized_models: Mapping[str, NormalizedIonChannelModel],
    bounds_fallbacks: Mapping[str, tuple[float, float]],
) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    for name in sorted(selection.global_parameters):
        selected = selection.global_parameters[name]
        qualified_name = name
        if selected.ion_channel_model is not None:
            model = normalized_models.get(selected.ion_channel_model.id_str)
            if model is None:
                msg = (
                    "No normalized metadata for global parameter source "
                    f"'{selected.ion_channel_model.id_str}'."
                )
                raise ValueError(msg)
            variable = model.find_variable(name)
            if variable is None or variable.variable_type != "GLOBAL":
                msg = (
                    f"Global parameter '{name}' is not a GLOBAL variable of '{model.nmodl_suffix}'."
                )
                raise ValueError(msg)
            qualified_name = variable.name
        parameters.append(
            _parameter_entry(
                qualified_name,
                "global",
                selected.value,
                fallback_names=(name,),
                bounds_fallbacks=bounds_fallbacks,
            )
        )
    return parameters


def _build_base_parameters(
    selection: ParametersSelection,
    distributions: Mapping[str, Any],
    bounds_fallbacks: Mapping[str, tuple[float, float]],
) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    overlap_rows: dict[tuple[str, str | None], list[SectionListName]] = {}
    for location in _ordered_locations(selection.base_parameters):
        _validate_location(location)
        for name in sorted(selection.base_parameters[location]):
            selected = selection.base_parameters[location][name]
            _validate_distribution(selected.distribution, distributions)
            mechanism = "pas" if name in {"g_pas", "e_pas"} else None
            overlap_rows.setdefault((name, mechanism), []).append(location)
            parameters.append(
                _parameter_entry(
                    name,
                    location,
                    selected.value,
                    mechanism=mechanism,
                    distribution=selected.distribution,
                    bounds_fallbacks=bounds_fallbacks,
                )
            )
    _warn_overlapping_locations(overlap_rows)
    return parameters


def _build_mechanism_parameters(
    selection: ParametersSelection,
    normalized_models: Mapping[str, NormalizedIonChannelModel],
    distributions: Mapping[str, Any],
    bounds_fallbacks: Mapping[str, tuple[float, float]],
) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    overlap_rows: dict[tuple[str, str | None], list[SectionListName]] = {}
    for location in _ordered_locations(selection.mechanism_regions):
        _validate_location(location)
        for assignment in selection.mechanism_regions[location]:
            model = normalized_models[assignment.ion_channel_model.id_str]
            for name in sorted(assignment.parameters):
                selected = assignment.parameters[name]
                _validate_distribution(selected.distribution, distributions)
                variable = model.find_variable(name)
                if variable is None:
                    msg = (
                        f"Parameter '{name}' is not declared by IonChannelModel "
                        f"'{model.nmodl_suffix}'."
                    )
                    raise ValueError(msg)
                if variable.variable_type != "RANGE":
                    msg = (
                        f"Parameter '{name}' is GLOBAL and must be configured in global_parameters."
                    )
                    raise ValueError(msg)
                overlap_rows.setdefault((variable.name, model.nmodl_suffix), []).append(location)
                parameters.append(
                    _parameter_entry(
                        variable.name,
                        location,
                        selected.value,
                        mechanism=model.nmodl_suffix,
                        distribution=selected.distribution,
                        fallback_names=(
                            name,
                            variable.source_name,
                            f"{model.nmodl_suffix}.{variable.source_name}",
                        ),
                        bounds_fallbacks=bounds_fallbacks,
                    )
                )
    _warn_overlapping_locations(overlap_rows)
    return parameters


def _build_distribution_parameters(
    selection: ParametersSelection,
    distributions: Mapping[str, Any],
    bounds_fallbacks: Mapping[str, tuple[float, float]],
) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    for distribution_name in sorted(selection.distribution_parameters):
        distribution = distributions.get(distribution_name)
        if distribution is None:
            msg = f"Distribution '{distribution_name}' is not declared."
            raise ValueError(msg)
        declared = set(distribution.parameters or [])
        configured = selection.distribution_parameters[distribution_name]
        unknown = set(configured) - declared
        if unknown:
            msg = (
                f"Distribution '{distribution_name}' has undeclared parameters: {sorted(unknown)}."
            )
            raise ValueError(msg)
        parameters.extend(
            _parameter_entry(
                name,
                f"distribution_{distribution_name}",
                configured[name],
                fallback_names=(
                    f"distribution_{distribution_name}.{name}",
                    f"{distribution_name}.{name}",
                ),
                bounds_fallbacks=bounds_fallbacks,
            )
            for name in sorted(configured)
        )
    return parameters


def _validate_myelinated_capability(
    selection: ParametersSelection,
    capabilities: MorphologyCapabilities,
) -> None:
    if capabilities.has_myelinated is True:
        return
    uses_myelinated = (
        "myelinated" in selection.base_parameters or "myelinated" in selection.mechanism_regions
    )
    if not uses_myelinated:
        return
    if capabilities.has_myelinated is False:
        msg = (
            "The configuration selects myelinated parameters, but the imported morphology "
            "has no myelinated section list."
        )
    else:
        msg = (
            "The configuration selects myelinated parameters, but morphology preflight did "
            "not establish a myelinated section list."
        )
    raise ValueError(msg)


def _validate_physical_section_availability(
    selection: ParametersSelection,
    capabilities: MorphologyCapabilities,
) -> None:
    """Reject a configured region the source morphology does not physically provide.

    ``available_physical_sections`` is empty when preflight was skipped (e.g. a caller
    constructed ``MorphologyCapabilities`` directly, as tests and the strategy-only
    fallback in ``task.py`` do); in that case this check is intentionally a no-op.
    """
    if not capabilities.available_physical_sections:
        return
    available = set(capabilities.available_physical_sections) | {"myelinated"}
    configured_locations = set(selection.base_parameters) | set(selection.mechanism_regions)
    for location in sorted(configured_locations):
        expanded = set(DEFAULT_SECTION_LIST_CATALOG.expand(location))
        missing = expanded - available
        if missing:
            msg = (
                f"Configured region '{location}' expands to {sorted(expanded)}, but the "
                f"imported morphology has no source sections for {sorted(missing)}."
            )
            raise ValueError(msg)


def _validate_morphology_capabilities(
    selection: ParametersSelection,
    capabilities: MorphologyCapabilities | None,
) -> None:
    if capabilities is not None and not isinstance(capabilities, MorphologyCapabilities):
        msg = "morphology_capabilities must be a MorphologyCapabilities model."
        raise TypeError(msg)
    if capabilities is None:
        return
    _validate_myelinated_capability(selection, capabilities)
    _validate_physical_section_availability(selection, capabilities)


def build_params_definition(
    config: Any,
    normalized_models: Mapping[str, NormalizedIonChannelModel],
    *,
    morphology_capabilities: MorphologyCapabilities | None = None,
    bounds_fallbacks: Mapping[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Compile a complete BluePyEModel params definition from Task 2 config.

    Distribution names are resolved against the built-in standard catalog
    (``STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS``) first, then against the
    config's custom-only ``distance_dependent_distributions`` declarations.
    """
    selection: ParametersSelection = config.parameters_selection
    custom_distributions = config.distance_dependent_distributions
    combined_distributions = {**STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS, **custom_distributions}
    fallbacks = DEFAULT_BOUNDS_FALLBACKS if bounds_fallbacks is None else bounds_fallbacks
    for fallback_name, fallback_bounds in fallbacks.items():
        _validate_bounds(fallback_name, fallback_bounds)
    _validate_morphology_capabilities(selection, morphology_capabilities)
    used_distributions = {"uniform"}
    used_distributions.update(
        parameter.distribution
        for parameters in selection.base_parameters.values()
        for parameter in parameters.values()
    )
    used_distributions.update(
        parameter.distribution
        for assignments in selection.mechanism_regions.values()
        for assignment in assignments
        for parameter in assignment.parameters.values()
    )
    for distribution_name in used_distributions:
        _validate_distribution(distribution_name, combined_distributions)
        declared = set(combined_distributions[distribution_name].parameters or [])
        configured = selection.distribution_parameters.get(distribution_name, {})
        if declared - set(configured):
            missing = sorted(declared - set(configured))
            msg = (
                f"Used distribution '{distribution_name}' is missing values for "
                f"parameters: {missing}."
            )
            raise ValueError(msg)

    emitted_distribution_names = sorted(used_distributions | set(custom_distributions))
    return {
        "morphology": {},
        "mechanisms": _build_mechanisms(selection, normalized_models),
        "distributions": [
            combined_distributions[name].to_emc_dict(name=name)
            for name in emitted_distribution_names
        ],
        "parameters": [
            *_build_global_parameters(selection, normalized_models, fallbacks),
            *_build_distribution_parameters(selection, combined_distributions, fallbacks),
            *_build_base_parameters(selection, combined_distributions, fallbacks),
            *_build_mechanism_parameters(
                selection, normalized_models, combined_distributions, fallbacks
            ),
        ],
    }
