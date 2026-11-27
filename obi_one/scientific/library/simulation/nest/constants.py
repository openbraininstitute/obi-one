TYPE_NEST_POINT = "nest_point"
TYPE_VIRTUAL = "virtual"
TYPE_NEST_CHEMICAL = "nest_chemical"
NEURON_TYPES = frozenset({TYPE_NEST_POINT})
NODE_TYPES = NEURON_TYPES | {TYPE_VIRTUAL}

IGNORED_KEYS = (
    ("conditions",),
    ("run", "spike_threshold"),
    ("run", "integration_method"),
    ("run", "nsteps_block"),
)

PREFIX_NEST = "nest:"
PREFIX_NESTML = "nestml:"


def split_model_template(model_template: str) -> tuple[str, str]:
    """Split a model reference into ``(backend, model_name)``.

    ``backend`` is ``"nest"`` (built-in), ``"nestml"`` (custom NESTML) or ``""`` when no recognised
    prefix is present (treated as a built-in NEST model name).
    """
    if model_template.startswith(PREFIX_NESTML):
        return "nestml", model_template[len(PREFIX_NESTML) :]
    if model_template.startswith(PREFIX_NEST):
        return "nest", model_template[len(PREFIX_NEST) :]
    return "", model_template
