"""SONATA circuit validation utilities."""

import logging
from pathlib import Path

import bluepysnap.circuit_validation as snap_circuit_validation

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


def run_validation(
    circuit_path: str | Path,
    *,
    raise_on_error: bool = True,
) -> tuple[list[str], list[str]]:
    """Run SONATA circuit validation with OBI-specific ignore rules.

    Wraps ``bluepysnap.circuit_validation.validate`` and always applies
    ``IGNORE_EDGE_PROPERTIES``. Unlike calling SNAP directly with
    ``only_errors=True``, this collects both FATAL errors and WARNINGs.

    Args:
        circuit_path: Path to ``circuit_config.json``.
        raise_on_error: When True (default), raise ``ValueError`` if any FATAL
            errors are found. Callers that want to aggregate results (e.g. the
            async circuit validation task) should pass ``False``.

    Returns:
        ``(fatal_errors, warnings)`` as lists of string messages. Empty lists
        when validation is clean.
    """
    errors = snap_circuit_validation.validate(
        str(circuit_path),
        skip_slow=False,
        only_errors=False,
        print_errors=False,
        ignore_edge_properties=IGNORE_EDGE_PROPERTIES,
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
