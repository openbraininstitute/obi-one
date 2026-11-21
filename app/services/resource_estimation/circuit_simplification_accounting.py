"""Map circuit-simplification algorithms to accounting service subtypes."""

from obp_accounting_sdk.constants import ServiceSubtype

from obi_one.scientific.tasks.circuit_simplification.algorithms.base import SimplificationAlgorithm

_SMALL = ServiceSubtype.CIRCUIT_SIMPLIFICATION_SMALL
_MEDIUM = ServiceSubtype.CIRCUIT_SIMPLIFICATION_MEDIUM
_LARGE = ServiceSubtype.CIRCUIT_SIMPLIFICATION_LARGE

# Algorithms billed by name alone (no filter_method).
_FIXED_ALGORITHM_SUBTYPE: dict[str, ServiceSubtype] = {
    "lif_nest": _SMALL,
    "adex_nest": _SMALL,
    "adex_brian2": _SMALL,
    "izhikevich_nest": _SMALL,
    "glif_nest": _SMALL,
    "gif_nest": _SMALL,
    "neuron_reduce": _MEDIUM,
    "neat_reduction": _LARGE,
    # Forward-looking NestML algorithms (not in the UI yet).
    "hh": _MEDIUM,
    "hh_pospischil": _MEDIUM,
    "hh_simulated_trace": _LARGE,
    "hh_pospischil_simulated_trace": _LARGE,
}

# Algorithms whose cost depends on filter_method (impedance vs timedomain).
_FILTER_METHOD_SUBTYPE: dict[tuple[str, str], ServiceSubtype] = {
    ("single_compartment", "impedance"): _MEDIUM,
    ("single_compartment", "timedomain"): _LARGE,
    ("rossert_detailed", "impedance"): _SMALL,
    ("rossert_detailed", "timedomain"): _LARGE,
    ("rossert_gif", "impedance"): _MEDIUM,
    ("rossert_gif", "timedomain"): _LARGE,
}


def service_subtype_for_algorithm(
    algorithm_name: str, *, filter_method: str | None = None
) -> ServiceSubtype:
    """Return the accounting subtype for a simplification algorithm and its filter_method."""
    if algorithm_name in _FIXED_ALGORITHM_SUBTYPE:
        return _FIXED_ALGORITHM_SUBTYPE[algorithm_name]

    filter_algorithms = {name for name, _method in _FILTER_METHOD_SUBTYPE}
    if algorithm_name in filter_algorithms:
        if filter_method is None:
            msg = f"Algorithm '{algorithm_name}' requires filter_method for accounting."
            raise ValueError(msg)
        key = (algorithm_name, filter_method)
        try:
            return _FILTER_METHOD_SUBTYPE[key]
        except KeyError:
            msg = (
                f"Unknown filter_method '{filter_method}' for algorithm '{algorithm_name}' "
                "in circuit simplification accounting."
            )
            raise ValueError(msg) from None

    msg = f"Unknown circuit simplification algorithm for accounting: '{algorithm_name}'"
    raise ValueError(msg)


def service_subtype_for_algorithm_block(block: SimplificationAlgorithm) -> ServiceSubtype:
    """Return the accounting subtype of the algorithm block selected in a config."""
    return service_subtype_for_algorithm(
        block.algorithm_name, filter_method=getattr(block, "filter_method", None)
    )
