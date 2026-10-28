"""Read mechanism variables from the files a SONATA circuit already contains.

The ``.hoc`` cell templates in ``biophysical_neuron_models_dir`` are printed by the
BluePyEModel/BluePyOpt Jinja template (``cell_template_neurodamus_*.jinja2``, format
described at https://sonata-extension.readthedocs.io/en/latest/hoc-emodel.html). Inside
``proc insertChannel()`` and ``proc biophys()`` that template can only print three line
shapes, which is what this module reads:

- ``insert <mechanism>`` inside ``forsec this.<section_list> { ... }``
- ``<variable> = <number>`` inside ``forsec CellRef.<section_list> { ... }``
- ``distribute_distance(CellRef.<section_list>, "<variable>", "<formula>")``

Any other line inside those two procedures raises ``HocTemplateError``: the file was not
produced by the template, so nothing is guessed. Mechanism GLOBAL values are the ones the
template checks in ``proc check_simulator()``. The ``.mod`` files in ``mechanisms_dir``
give each mechanism's RANGE/GLOBAL variable names and the units declared in PARAMETER;
NEURON's built-in mechanisms have no mod file and are described by ``BUILTIN_MECHANISMS``.

The result uses the same types as ``emodel_parameters.get_mechanism_variables_for_emodel``
so the response builder in ``memodel_circuit`` stays unchanged.
"""

import re
from dataclasses import dataclass, field
from typing import NoReturn

from obi_one.scientific.library.emodel_parameters import (
    ChannelInfo,
    ChannelSectionListMapping,
    MechanismVariable,
    expand_section_list,
    extract_section_properties,
)

CONDUCTANCE_LIMITS = [0.0, 10.0]
# Built-in mechanisms with nothing settable through a ``<variable>_<mechanism>`` name:
# ``capacitance`` sets ``cm``, already a section property, and ion mechanisms
# (``na_ion`` and the like) are set directly, as ``ena = 50`` in biophys().
ION_MECHANISM_SUFFIX = "_ion"
CAPACITANCE_MECHANISM = "capacitance"
# Longest hoc line quoted in an error message; the message reaches the API response.
MAX_QUOTED_LINE = 120

NUMBER_PATTERN = r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
FORSEC_RE = re.compile(r"forsec (?:this|CellRef)\.(\w+) \{")
INSERT_RE = re.compile(r"insert (\w+)")
ASSIGN_RE = re.compile(rf"(\w+) = ({NUMBER_PATTERN})")
DISTRIBUTE_RE = re.compile(r'distribute_distance\(CellRef\.(\w+), "(\w+)", "([^"]*)"\)')
TRAILING_FACTOR_RE = re.compile(rf"\*\s*({NUMBER_PATTERN})\s*$")
CHECK_PARAMETER_RE = re.compile(rf'check_parameter\("(\w+)", ({NUMBER_PATTERN}), \1\)')
MOD_BLOCK_RE = re.compile(r"\b(NEURON|PARAMETER)\s*\{(.*?)\n\s*\}", re.DOTALL)
# NMODL does not need a newline between NEURON block statements, so the block is split on
# its keywords rather than its lines.
MOD_NEURON_KEYWORD_RE = re.compile(
    r"\b(SUFFIX|POINT_PROCESS|ARTIFICIAL_CELL|RANGE|GLOBAL|USEION|NONSPECIFIC_CURRENT"
    r"|ELECTRODE_CURRENT|POINTER|BBCOREPOINTER|EXTERNAL|THREADSAFE|REPRESENTS)\b"
)
MOD_UNIT_RE = re.compile(rf"^(\w+)\s*(?:=\s*{NUMBER_PATTERN})?\s*\(([^)]*)\)")


class HocTemplateError(ValueError):
    """A hoc or mod file is not one this module can read without guessing."""


@dataclass
class ModMechanism:
    """What a ``.mod`` file declares about one mechanism."""

    suffix: str
    range_variables: list[str] = field(default_factory=list)
    global_variables: list[str] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)


# Mechanisms NEURON ships without a mod file (the list BluePyEModel uses, minus the two
# above), with their settable RANGE variables and units from the NEURON documentation.
BUILTIN_MECHANISMS: dict[str, ModMechanism] = {
    name: ModMechanism(suffix=name, range_variables=variables, units=units)
    for name, variables, units in (
        ("pas", ["g", "e"], {"g": "S/cm2", "e": "mV"}),
        ("fastpas", ["g", "e"], {"g": "S/cm2", "e": "mV"}),
        (
            "hh",
            ["gnabar", "gkbar", "gl", "el"],
            {"gnabar": "S/cm2", "gkbar": "S/cm2", "gl": "S/cm2", "el": "mV"},
        ),
        (
            "extracellular",
            ["xraxial", "xg", "xc", "e_extracellular"],
            {"xraxial": "MOhm/cm", "xg": "S/cm2", "xc": "uF/cm2", "e_extracellular": "mV"},
        ),
    )
}


def has_variables(mechanism: str) -> bool:
    """Whether a mechanism exposes ``<variable>_<mechanism>`` names a user could set."""
    return mechanism != CAPACITANCE_MECHANISM and not mechanism.endswith(ION_MECHANISM_SUFFIX)


@dataclass
class HocBiophysics:
    """What a cell template's insertChannel() and biophys() procedures contain."""

    channels_by_section_list: dict[str, list[str]] = field(default_factory=dict)
    assignments: dict[tuple[str, str], float] = field(default_factory=dict)
    distributions: dict[tuple[str, str], float | None] = field(default_factory=dict)
    global_values: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def inserted_mechanisms(self) -> set[str]:
        """Every mechanism with variables inserted in any section list."""
        return {
            name
            for names in self.channels_by_section_list.values()
            for name in names
            if has_variables(name)
        }

    @property
    def mod_file_mechanisms(self) -> set[str]:
        """The inserted mechanisms that need a mod file: all but NEURON's built-ins."""
        return self.inserted_mechanisms - BUILTIN_MECHANISMS.keys()


def read_mod_mechanism(mod_text: str) -> ModMechanism:
    """Read SUFFIX, RANGE, GLOBAL and PARAMETER units from a ``.mod`` file."""
    blocks = dict(MOD_BLOCK_RE.findall(mod_text))
    if "NEURON" not in blocks:
        msg = "mod file has no NEURON block"
        raise HocTemplateError(msg)

    mechanism = ModMechanism(suffix="")
    code = "\n".join(line.split(":", 1)[0] for line in blocks["NEURON"].splitlines())
    statements = MOD_NEURON_KEYWORD_RE.split(code)[1:]  # [keyword, rest, keyword, rest, ...]
    for keyword, rest in zip(statements[::2], statements[1::2], strict=True):
        names = [name for name in re.split(r"[,\s]+", rest.strip()) if name]
        if keyword in {"SUFFIX", "POINT_PROCESS"} and names:
            mechanism.suffix = names[0]
        elif keyword == "RANGE":
            mechanism.range_variables.extend(names)
        elif keyword == "GLOBAL":
            mechanism.global_variables.extend(names)
    if not mechanism.suffix:
        msg = "mod file NEURON block has no SUFFIX"
        raise HocTemplateError(msg)

    for raw_line in blocks.get("PARAMETER", "").splitlines():
        match = MOD_UNIT_RE.match(raw_line.split(":", 1)[0].strip())
        if match:
            mechanism.units[match.group(1)] = match.group(2).strip()
    return mechanism


def _proc_lines(hoc_text: str, name: str) -> list[str]:
    """Non-empty stripped lines of ``proc <name>()``, found by brace matching."""
    start = hoc_text.find(f"proc {name}()")
    if start < 0:
        msg = f"hoc template has no 'proc {name}()'"
        raise HocTemplateError(msg)
    open_brace = hoc_text.index("{", start)
    depth = 0
    for index in range(open_brace, len(hoc_text)):
        if hoc_text[index] == "{":
            depth += 1
        elif hoc_text[index] == "}":
            depth -= 1
            if depth == 0:
                body = hoc_text[open_brace + 1 : index]
                return [line.strip() for line in body.splitlines() if line.strip()]
    msg = f"unbalanced braces in 'proc {name}()'"
    raise HocTemplateError(msg)


def _raise_unexpected(proc_name: str, line: str) -> NoReturn:
    """Reject a line the template cannot print, quoting at most MAX_QUOTED_LINE chars."""
    msg = f"unexpected line in {proc_name}(): {line[:MAX_QUOTED_LINE]!r}"
    raise HocTemplateError(msg)


def _distribution_value(formula: str) -> float | None:
    """The optimised value: the trailing factor every BluePyEModel distribution ends with.

    A number anywhere else is a coefficient of the distribution, so None is returned
    rather than a guess.
    """
    match = TRAILING_FACTOR_RE.search(formula)
    return float(match.group(1)) if match else None


def _read_insert_channel(hoc_text: str, result: HocBiophysics) -> None:
    """Fill ``channels_by_section_list`` from ``proc insertChannel()``."""
    section_list = None
    for line in _proc_lines(hoc_text, "insertChannel"):
        if match := FORSEC_RE.fullmatch(line):
            section_list = match.group(1)
            result.channels_by_section_list.setdefault(section_list, [])
        elif (match := INSERT_RE.fullmatch(line)) and section_list is not None:
            result.channels_by_section_list[section_list].append(match.group(1))
        elif line == "}":
            section_list = None
        else:
            _raise_unexpected("insertChannel", line)


def _read_biophys(hoc_text: str, result: HocBiophysics) -> None:
    """Fill ``assignments`` and ``distributions`` from ``proc biophys()``."""
    section_list = None
    for line in _proc_lines(hoc_text, "biophys"):
        if match := FORSEC_RE.fullmatch(line):
            section_list = match.group(1)
        elif (match := ASSIGN_RE.fullmatch(line)) and section_list is not None:
            result.assignments[section_list, match.group(1)] = float(match.group(2))
        elif match := DISTRIBUTE_RE.fullmatch(line):
            location, variable, formula = match.groups()
            value = _distribution_value(formula)
            if value is None:
                result.warnings.append(
                    f"{variable} on {location}: value not readable from its distribution"
                )
            result.distributions[location, variable] = value
        elif line == "}":
            section_list = None
        else:
            _raise_unexpected("biophys", line)


def read_hoc_biophysics(hoc_text: str) -> HocBiophysics:
    """Read channels per section list and assigned values from a cell template."""
    result = HocBiophysics()
    _read_insert_channel(hoc_text, result)
    _read_biophys(hoc_text, result)
    result.global_values = {
        name: float(value) for name, value in CHECK_PARAMETER_RE.findall(hoc_text)
    }
    return result


def _channel_section_lists(biophysics: HocBiophysics) -> dict[str, list[str]]:
    """Channel -> sorted section lists, with aliases such as ``all`` expanded."""
    sections: dict[str, set[str]] = {}
    inserted = biophysics.inserted_mechanisms
    for section_list, channels in biophysics.channels_by_section_list.items():
        for channel in channels:
            if channel in inserted:
                sections.setdefault(channel, set()).update(expand_section_list(section_list))
    return {channel: sorted(lists) for channel, lists in sections.items()}


def _values_by_section(biophysics: HocBiophysics) -> dict[tuple[str, str], float | None]:
    """(section list, variable) -> value, with ``all``-style aliases expanded."""
    values: dict[tuple[str, str], float | None] = {}
    for source in (biophysics.assignments, biophysics.distributions):
        for (section_list, variable), value in source.items():
            for expanded in expand_section_list(section_list):
                values[expanded, variable] = value
    return values


def mechanism_variables(
    biophysics: HocBiophysics,
    mechanisms: dict[str, ModMechanism],
) -> tuple[list[MechanismVariable], ChannelSectionListMapping]:
    """Build the mechanism variables of one cell template.

    Args:
        biophysics: The template's parsed hoc file.
        mechanisms: Parsed ``.mod`` files keyed by suffix, for every mechanism in
            ``biophysics.mod_file_mechanisms``.

    Returns:
        The same ``(variables, channel_mapping)`` pair ``get_mechanism_variables_for_emodel``
        returns. Channel ``entity_id`` is None: the files do not know database IDs.

    Raises:
        HocTemplateError: A mod file for an inserted mechanism is missing.
    """
    channel_sections = _channel_section_lists(biophysics)
    values = _values_by_section(biophysics)

    missing = sorted(biophysics.mod_file_mechanisms - mechanisms.keys())
    if missing:
        msg = f"no mod file for inserted mechanisms: {missing}"
        raise HocTemplateError(msg)

    mapping = ChannelSectionListMapping(
        channel_to_section_lists={
            channel: ChannelInfo(section_lists=section_lists, entity_id=None)
            for channel, section_lists in channel_sections.items()
        }
    )

    variables: list[MechanismVariable] = []
    for channel, section_lists in channel_sections.items():
        mechanism = BUILTIN_MECHANISMS.get(channel) or mechanisms[channel]
        for name in mechanism.range_variables:
            # Ionic currents (i*) cannot be set; same rule as the EModel metadata path.
            if name.startswith("i"):
                continue
            neuron_variable = f"{name}_{channel}"
            variables.extend(
                MechanismVariable(
                    neuron_variable=neuron_variable,
                    channel_name=channel,
                    section_list=section_list,
                    value=values.get((section_list, neuron_variable)),
                    units=mechanism.units.get(name, ""),
                    limits=CONDUCTANCE_LIMITS if neuron_variable.startswith("g") else None,
                    variable_type="RANGE",
                )
                for section_list in section_lists
            )
        variables.extend(
            MechanismVariable(
                neuron_variable=f"{name}_{channel}",
                channel_name=channel,
                section_list="",
                value=biophysics.global_values.get(f"{name}_{channel}"),
                units=mechanism.units.get(name, ""),
                limits=None,
                variable_type="GLOBAL",
            )
            for name in mechanism.global_variables
        )

    for prop in extract_section_properties(mapping):
        prop.value = values.get((prop.section_list, prop.neuron_variable))
        variables.append(prop)

    return variables, mapping
