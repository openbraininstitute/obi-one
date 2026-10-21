from sonata_simplify.algorithms import (
    ALGORITHM_DESCRIPTIONS,
    ALGORITHM_TITLES,
    get_algorithm_spec,
)

# Maps compound name -> (base_algorithm, exporter_name or None).
# Brian2 currently supports AdEx; other point-neuron algorithms use NEST.
ALGORITHM_EXPORT_MAP: dict[str, tuple[str, str | None]] = {
    "single_compartment": ("single_compartment", None),
    "lif_nest": ("lif", "nest:iaf_psc_alpha"),
    "adex_nest": ("adex", "nest:aeif_cond_alpha"),
    "adex_brian2": ("adex", "brian2:adex"),
    "izhikevich_nest": ("izhikevich", "nest:izhikevich"),
    "glif_nest": ("glif", "nest:glif_psc"),
    "gif_nest": ("gif", "nest:gif_cond_exp"),
    "neuron_reduce": ("neuron_reduce", None),
}

# Display titles for compound names, extending the sonata_simplify metadata with
# the simulator suffix used by OBI-One.
ALGORITHM_EXPORT_TITLES: dict[str, str] = {
    "single_compartment": (
        f"{ALGORITHM_TITLES.get('single_compartment', 'Single Compartment')} (NEURON)"
    ),
    "lif_nest": f"{ALGORITHM_TITLES.get('lif', 'LIF')} (NEST)",
    "adex_nest": f"{ALGORITHM_TITLES.get('adex', 'AdEx')} (NEST)",
    "adex_brian2": f"{ALGORITHM_TITLES.get('adex', 'AdEx')} (Brian2)",
    "izhikevich_nest": f"{ALGORITHM_TITLES.get('izhikevich', 'Izhikevich')} (NEST)",
    "glif_nest": f"{ALGORITHM_TITLES.get('glif', 'GLIF')} (NEST)",
    "gif_nest": f"{ALGORITHM_TITLES.get('gif', 'GIF')} (NEST)",
    "neuron_reduce": f"{ALGORITHM_TITLES.get('neuron_reduce', 'Neuron_Reduce')} (NEURON)",
}

# Descriptions remain sourced from sonata_simplify and are shared by all
# simulator variants of the same base algorithm.
ALGORITHM_EXPORT_DESCRIPTIONS: dict[str, str] = {
    name: ALGORITHM_DESCRIPTIONS.get(base, "") for name, (base, _) in ALGORITHM_EXPORT_MAP.items()
}


def algorithm_supports_node_selection(algorithm_name: str) -> bool:
    """Whether sonata_simplify can simplify only a node set with this compound algorithm."""
    base_algorithm, _ = ALGORITHM_EXPORT_MAP[algorithm_name]
    return get_algorithm_spec(base_algorithm).capabilities.supports_node_selection
