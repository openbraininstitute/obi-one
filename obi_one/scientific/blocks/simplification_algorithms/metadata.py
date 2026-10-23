# Static copy of the sonata_simplify algorithm metadata, so the API and the form schema
# don't need the private sonata-simplify package installed (it is only in the launch env).
# test_metadata_matches_sonata_simplify checks for drift when sonata-simplify is installed.

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

_NMDA_LIMITATION = (
    " Limitation: excitatory synapses are modelled as AMPA-only — the NMDA component"
    " (~40 % of excitatory charge at rest) is not represented."
)

# Base-algorithm titles and descriptions (from sonata_simplify 0.2.5).
BASE_ALGORITHM_TITLES: dict[str, str] = {
    "single_compartment": "Single-Compartment with Synapse Relocation",
    "lif": "Leaky Integrate-and-Fire (LIF)",
    "adex": "Adaptive Exponential Integrate-and-Fire (AdEx)",
    "izhikevich": "Izhikevich",
    "glif": "Generalized Leaky Integrate-and-Fire (GLIF)",
    "gif": "Generalized Integrate-and-Fire (GIF)",
    "neuron_reduce": "Neuron_Reduce Impedance-Based Reduction",
}

BASE_ALGORITHM_DESCRIPTIONS: dict[str, str] = {
    "single_compartment": (
        "Reduces each biophysical morphology to a single-compartment sphere and relocates all"
        " synapses to the soma. Computes Rössert-style correction filters to preserve"
        " dendritic filtering effects. The output is a SONATA circuit with simplified"
        " point-neuron cell models that retain active and passive biophysical properties."
        " Best for: simulations where dendritic computation is captured by filters rather"
        " than explicit morphology."
    ),
    "lif": (
        "Converts to leaky integrate-and-fire (LIF) point neurons using literature-template"
        " capacitance and reset/refractory parameters — NOT fitted to the detailed cell."
        " Only input resistance, resting potential, rheobase-derived threshold and synaptic"
        " kinetics are derived from the circuit (C_m is measured-derived only when an etype"
        " supplies membrane_time_constant_ms). No morphology, no synapse relocation, no"
        " filter computation. Best for: large-scale rate-coded or spiking network"
        " simulations where biological detail is not needed." + _NMDA_LIMITATION
    ),
    "adex": (
        "Converts to adaptive exponential integrate-and-fire (AdEx) point neurons using"
        " literature-template capacitance and adaptation parameters (Delta_T, a, b, tau_w)"
        " — NOT fitted to the detailed cell. Only input resistance (g_L), resting potential"
        " (E_L), rheobase-derived threshold and synaptic kinetics are derived from the"
        " circuit. No morphology, no synapse relocation, no filter computation. Best for:"
        " simulations requiring spike-frequency adaptation without full morphological"
        " detail." + _NMDA_LIMITATION
    ),
    "izhikevich": (
        "Converts to Izhikevich point neurons (2 variables, 4 parameters) using"
        " literature-template presets selected by an explicit per-etype map — NOT fitted to"
        " the detailed cell (the dimensionless model ignores R_in and V_rest entirely; only"
        " synaptic kinetics are circuit-derived). Unknown etypes raise rather than being"
        " heuristically classified. No morphology, no synapse relocation, no filter"
        " computation. Best for: large-scale simulations requiring diverse firing patterns"
        " at minimal computational cost." + _NMDA_LIMITATION
    ),
    "glif": (
        "Converts to generalized leaky integrate-and-fire (GLIF) point neurons using"
        " literature-template capacitance and after-spike/ threshold-adaptation parameters"
        " — NOT fitted to the detailed cell. Only input resistance (g_L), resting potential"
        " (E_L), rheobase-derived threshold and synaptic kinetics are derived from the"
        " circuit. Supports GLIF levels 1\N{EN DASH}5; default is GLIF3. No morphology, no synapse"
        " relocation, no filter computation. Best for: simulations aligned with the Allen"
        " Brain Cell Atlas GLIF neuron models." + _NMDA_LIMITATION
    ),
    "gif": (
        "Converts to generalized integrate-and-fire (GIF) point neurons using"
        " literature-template capacitance, threshold and spike-triggered kernel parameters"
        " — NOT fitted to the detailed cell. Only input resistance (g_L), resting potential"
        " (E_L), rheobase-derived threshold and synaptic kinetics are derived from the"
        " circuit. No morphology, no synapse relocation, no filter computation. Best for:"
        " simulations requiring stochastic spiking with adaptation, compatible with the"
        " Gerstner lab framework. For trace-fitted GIF cells with soma relocation and"
        " synaptic correction filters use rossert_gif instead." + _NMDA_LIMITATION
    ),
    "neuron_reduce": (
        "Reduces each dendritic subtree of the biophysical ME-models to an equivalent"
        " cylinder with the neuron-reduce package (Amsalem et al. 2020), keeping soma, axon"
        " and the dendritic channel distribution. Afferent synapses are remapped onto the"
        " reduced cylinders by transfer-impedance matching. The output is a BBP SONATA"
        " circuit of reduced multi-compartment ME-models (generated HOC templates, reduced"
        " SWC, original MOD files). Holding, threshold, input resistance and resting"
        " potential are re-measured on the reduced cells (validate-then-shift, 5% tolerance)"
        " and recorded in a per-model manifest. Requires the optional 'reduction' extra"
        " (neuron-reduce + NEURON)."
    ),
}

# Base algorithms that can simplify only a node set (sonata_simplify capability).
NODE_SELECTION_ALGORITHMS = frozenset({"single_compartment"})

_SIMULATOR_SUFFIX = {None: "NEURON", "nest": "NEST", "brian2": "Brian2"}

# Display titles for compound names, with the simulator suffix used by OBI-One.
ALGORITHM_EXPORT_TITLES: dict[str, str] = {
    name: (
        f"{BASE_ALGORITHM_TITLES[base]}"
        f" ({_SIMULATOR_SUFFIX[exporter.split(':')[0] if exporter else None]})"
    )
    for name, (base, exporter) in ALGORITHM_EXPORT_MAP.items()
}

# Descriptions are shared by all simulator variants of the same base algorithm.
ALGORITHM_EXPORT_DESCRIPTIONS: dict[str, str] = {
    name: BASE_ALGORITHM_DESCRIPTIONS[base] for name, (base, _) in ALGORITHM_EXPORT_MAP.items()
}


def algorithm_supports_node_selection(algorithm_name: str) -> bool:
    """Whether sonata_simplify can simplify only a node set with this compound algorithm."""
    base_algorithm, _ = ALGORITHM_EXPORT_MAP[algorithm_name]
    return base_algorithm in NODE_SELECTION_ALGORITHMS
