"""SONATA circuit validation utilities."""

import logging
from pathlib import Path

import bluepysnap.circuit_validation as snap_circuit_validation

from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.circuit_constants import (
    ELECTRICAL_MODEL_NODE_PROPERTIES,
    SYNAPSE_PHYSIOLOGY_PROPERTIES,
)
from obi_one.utils.circuit import has_electrical_cell_models, has_synapse_physiology

L = logging.getLogger(__name__)

# Properties to ignore in SNAP validation.
# TODO: Refine SNAP validation.
# https://github.com/openbraininstitute/prod-build-circuit/issues/49
IGNORE_EDGE_PROPERTIES: list[str] = [
    "afferent_surface_x",
    "afferent_surface_y",
    "afferent_surface_z",
    "spine_length",
    "afferent_section_type",
]


def _structural_ignore_properties(circuit_path: str | Path) -> tuple[list[str], list[str]]:
    """Return (edge, node) property lists to ignore based on what the circuit lacks.

    Synapse physiology properties are ignored when no edge population has them; electrical
    cell model properties are ignored when no node population has an e-model. Falls back to
    strict validation (ignore nothing) if the circuit cannot be opened, so that SNAP reports
    the underlying problem instead of it being masked.
    """
    try:
        c = Circuit(name="validation", path=str(circuit_path))
        ignore_edge = [] if has_synapse_physiology(c) else list(SYNAPSE_PHYSIOLOGY_PROPERTIES)
        ignore_node = (
            [] if has_electrical_cell_models(c) else list(ELECTRICAL_MODEL_NODE_PROPERTIES)
        )
    except Exception as e:  # ruff: ignore[blind-except]
        L.warning(
            "Could not open %s to check circuit properties (%s); validating strictly",
            circuit_path,
            e,
        )
        return [], []
    return ignore_edge, ignore_node


def run_validation(
    circuit_path: str | Path,
    *,
    raise_on_error: bool = True,
) -> tuple[list[str], list[str]]:
    """Run SONATA circuit validation with OBI-specific ignore rules.

    Wraps ``bluepysnap.circuit_validation.validate`` and always applies
    ``IGNORE_EDGE_PROPERTIES``. For structural circuits, missing properties expected only on
    parameterized circuits are ignored: ``SYNAPSE_PHYSIOLOGY_PROPERTIES`` when there is no
    synapse physiology, and ``ELECTRICAL_MODEL_NODE_PROPERTIES`` when there are no electrical
    cell models. Unlike calling SNAP directly with ``only_errors=True``, this collects both
    FATAL errors and WARNINGs.

    Args:
        circuit_path: Path to ``circuit_config.json``.
        raise_on_error: When True (default), raise ``ValueError`` if any FATAL
            errors are found. Callers that want to aggregate results (e.g. the
            async circuit validation task) should pass ``False``.

    Returns:
        ``(fatal_errors, warnings)`` as lists of string messages. Empty lists
        when validation is clean.
    """
    structural_edge_ignore, node_ignore = _structural_ignore_properties(circuit_path)
    ignore_edge_properties = list(IGNORE_EDGE_PROPERTIES) + structural_edge_ignore

    errors = snap_circuit_validation.validate(
        str(circuit_path),
        skip_slow=False,
        only_errors=False,
        print_errors=False,
        ignore_edge_properties=ignore_edge_properties,
        ignore_node_properties=node_ignore,
    )
    fatal_errors = [str(e) for e in errors if e.level == "FATAL"]
    warnings = [str(e) for e in errors if e.level == "WARNING"]

    if fatal_errors:
        L.warning("SONATA validation found %d fatal error(s)", len(fatal_errors))
        if raise_on_error:
            msg = f"Circuit validation error(s) found:\n{fatal_errors}"
            raise ValueError(msg)
        return fatal_errors, warnings

    if warnings:
        L.warning("SONATA validation found %d warning(s)", len(warnings))
    else:
        L.info("No SONATA validation errors found!")
    return fatal_errors, warnings
