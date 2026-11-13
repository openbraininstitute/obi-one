"""Read a cell model's mechanism variables from the hoc and mod files of a SONATA circuit.

- ``.hoc`` cell template (one per ``model_template``): which mechanism is inserted in
  which section list, and the value of each variable there.
- ``.mod`` file (one per mechanism): its ``RANGE`` / ``GLOBAL`` variables, which of them are
  inputs (``PARAMETER``), and their units.

The hoc files are printed by BluePyEModel's template (format:
https://sonata-extension.readthedocs.io/en/latest/hoc-emodel.html). In ``insertChannel()``
and ``biophys()`` it prints three line shapes, and only those are accepted:

- ``insert <mechanism>`` inside ``forsec this.<section_list> { ... }``
- ``<variable> = <number>`` inside ``forsec CellRef.<section_list> { ... }``
- ``distribute_distance(CellRef.<section_list>, "<variable>", "<formula>")``

Any other line raises ``HocTemplateError``; nothing is guessed. The result has the same
types as ``emodel_parameters.get_mechanism_variables_for_emodel``.
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

# The files carry no limits; conductances (``g*``) get the same ones as the EModel path.
CONDUCTANCE_LIMITS = [0.0, 10.0]
# Built-ins with no ``<variable>_<mechanism>`` name: ``cm`` is a section property, and
# ion variables (``ena``) are set directly in biophys().
ION_MECHANISM_SUFFIX = "_ion"
CAPACITANCE_MECHANISM = "capacitance"
# Error messages reach the API response.
MAX_QUOTED_LINE = 120

NUMBER_PATTERN = r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
FORSEC_RE = re.compile(r"forsec (?:this|CellRef)\.(\w+) \{")
INSERT_RE = re.compile(r"insert (\w+)")
ASSIGN_RE = re.compile(rf"(\w+) = ({NUMBER_PATTERN})")
DISTRIBUTE_RE = re.compile(r'distribute_distance\(CellRef\.(\w+), "(\w+)", "([^"]*)"\)')
NUMBER_RE = re.compile(rf"[-+]?{NUMBER_PATTERN.removeprefix('-?')}")
# How BluePyOpt prints the distance to the soma in a distribution formula.
DISTANCE = "%.17g"
# Numbers, the distance, ``*`` and ``/`` only: the linear term of ``linear_e_pas_apic``.
LINEAR_IN_DISTANCE_RE = re.compile(r"[0-9.eE*/()\s]+")
LINEAR_DISTRIBUTION_TERMS = 2  # the value, and the term linear in the distance
CHECK_PARAMETER_RE = re.compile(rf'check_parameter\("(\w+)", ({NUMBER_PATTERN}), \1\)')
MOD_BLOCK_START_RE = re.compile(r"\b(NEURON|PARAMETER|ASSIGNED|STATE)\s*\{")
# NEURON block statements need no newline between them: split on keywords, not lines.
MOD_NEURON_KEYWORD_RE = re.compile(
    r"\b(SUFFIX|POINT_PROCESS|ARTIFICIAL_CELL|RANGE|GLOBAL|USEION|NONSPECIFIC_CURRENT"
    r"|ELECTRODE_CURRENT|POINTER|BBCOREPOINTER|EXTERNAL|THREADSAFE|REPRESENTS)\b"
)
# ``name (unit)`` or ``name = value (unit)``; a line may declare several names.
MOD_UNIT_RE = re.compile(rf"\b([A-Za-z_]\w*)\s*(?:=\s*{NUMBER_PATTERN}\s*)?\(([^)]*)\)")
# What follows a name in a PARAMETER declaration: ``= value``, ``(unit)`` and ``<low, high>``.
MOD_DECLARATION_EXTRAS_RE = re.compile(
    rf"=\s*[-+]?{NUMBER_PATTERN.removeprefix('-?')}|\([^)]*\)|<[^>]*>"
)
IDENTIFIER_RE = re.compile(r"\b[A-Za-z_]\w*")
# NMODL comments: ``COMMENT ... ENDCOMMENT`` blocks and ``:`` to the end of the line.
MOD_COMMENT_RE = re.compile(r"^\s*COMMENT\b.*?^\s*ENDCOMMENT\b|:[^\n]*", re.DOTALL | re.MULTILINE)


class HocTemplateError(ValueError):
    """A hoc or mod file is not one this module can read without guessing."""


@dataclass
class ModMechanism:
    """What a ``.mod`` file declares about one mechanism.

    Attributes:
        suffix: Mechanism name, from ``SUFFIX``; variables are set as ``<name>_<suffix>``.
        range_variables: ``RANGE`` names: one value per section, e.g. a conductance.
        global_variables: ``GLOBAL`` names: one value for the whole simulation.
        parameter_variables: ``PARAMETER`` names: the mechanism's inputs.
        units: Variable -> unit, for the variables whose unit is declared.
        entity_id: ID of the ion channel model entity of this mechanism, when exactly one
            matches; filled from the database.
    """

    suffix: str
    range_variables: list[str] = field(default_factory=list)
    global_variables: list[str] = field(default_factory=list)
    parameter_variables: list[str] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)
    entity_id: str | None = None

    @property
    def settable_range_variables(self) -> list[str]:
        """RANGE variables a user can set: those in ``PARAMETER``.

        Every other RANGE name is computed by the mod file itself: currents (``ina``),
        ``STATE`` variables, and ``ASSIGNED`` values that ``BREAKPOINT`` recomputes every
        step (``gNaTg``), so setting them changes nothing.
        """
        parameters = set(self.parameter_variables)
        return [name for name in self.range_variables if name in parameters]


# Mechanisms NEURON ships without a mod file; variables and units from the NEURON docs.
BUILTIN_MECHANISMS: dict[str, ModMechanism] = {
    name: ModMechanism(
        suffix=name, range_variables=variables, parameter_variables=variables, units=units
    )
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
    """What a cell template's ``insertChannel()`` and ``biophys()`` contain.

    Attributes:
        channels_by_section_list: Section list -> mechanisms inserted there, in file order.
        assignments: (section list, variable) -> value from ``<variable> = <number>``.
        distributions: (section list, variable) -> value from ``distribute_distance``, or
            None when the formula cannot be read.
        global_values: GLOBAL variable -> value, from ``check_parameter``.
        warnings: One message per value that could not be read.
    """

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
    """Read the mechanism name, variables and units from the text of a ``.mod`` file.

    Raises:
        HocTemplateError: No ``NEURON`` block, no ``SUFFIX``, or unbalanced braces.
    """
    blocks = _mod_blocks(MOD_COMMENT_RE.sub("", mod_text))
    if "NEURON" not in blocks:
        msg = "mod file has no NEURON block"
        raise HocTemplateError(msg)

    mechanism = ModMechanism(suffix="")
    statements = MOD_NEURON_KEYWORD_RE.split(blocks["NEURON"])[1:]  # [keyword, rest, ...]
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

    mechanism.parameter_variables = _declared_names(blocks.get("PARAMETER", ""))
    mechanism.units = _declared_units(blocks)
    return mechanism


def _declared_names(block: str) -> list[str]:
    """Names declared in a block such as ``PARAMETER``, in file order."""
    names = IDENTIFIER_RE.findall(MOD_DECLARATION_EXTRAS_RE.sub(" ", block))
    return list(dict.fromkeys(names))


def _declared_units(blocks: dict[str, str]) -> dict[str, str]:
    """Variable -> unit from the ``STATE``, ``ASSIGNED`` and ``PARAMETER`` blocks; the last wins."""
    units: dict[str, str] = {}
    for block in ("STATE", "ASSIGNED", "PARAMETER"):
        for line in blocks.get(block, "").splitlines():
            for match in MOD_UNIT_RE.finditer(line):
                units[match.group(1)] = match.group(2).strip()
    return units


def _mod_blocks(mod_text: str) -> dict[str, str]:
    """Block name -> body, by brace matching (``STATE { m h }`` fits on one line).

    A repeated block (``StochKv3.mod`` has two ``ASSIGNED``) is joined, not replaced.
    """
    blocks: dict[str, str] = {}
    position = 0
    while match := MOD_BLOCK_START_RE.search(mod_text, position):
        name = match.group(1)
        body, position = _braced_body(mod_text, match.end() - 1, f"{name} block")
        blocks[name] = f"{blocks.get(name, '')}\n{body}"
    return blocks


def _braced_body(text: str, open_brace: int, what: str) -> tuple[str, int]:
    """Return the text inside the brace pair opened at ``open_brace`` and the index of its ``}``.

    Raises:
        HocTemplateError: The braces do not balance.
    """
    depth = 0
    for index in range(open_brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace + 1 : index], index
    msg = f"unbalanced braces in {what}"
    raise HocTemplateError(msg)


def _proc_lines(hoc_text: str, name: str) -> list[str]:
    """Non-empty stripped lines of ``proc <name>()``.

    Raises:
        HocTemplateError: The procedure is missing.
    """
    start = hoc_text.find(f"proc {name}()")
    if start < 0:
        msg = f"hoc template has no 'proc {name}()'"
        raise HocTemplateError(msg)
    body, _end = _braced_body(hoc_text, hoc_text.index("{", start), f"'proc {name}()'")
    return [line.strip() for line in body.splitlines() if line.strip()]


def _raise_unexpected(proc_name: str, line: str) -> NoReturn:
    """Reject a line the template cannot print."""
    msg = f"unexpected line in {proc_name}(): {line[:MAX_QUOTED_LINE]!r}"
    raise HocTemplateError(msg)


def _strip_parens(expr: str) -> str:
    """``expr`` without whitespace and without parentheses wrapping all of it."""
    expr = expr.strip()
    while expr.startswith("(") and _closing_paren(expr) == len(expr) - 1:
        expr = expr[1:-1].strip()
    return expr


def _closing_paren(expr: str) -> int:
    """Index of the parenthesis closing the one at index 0, or -1 when unbalanced."""
    depth = 0
    for index, char in enumerate(expr):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth == 0:
            return index
    return -1


def _is_binary_sign(expr: str, index: int) -> bool:
    """Whether the ``+`` or ``-`` at ``index`` is an operator, not a sign (``-3``, ``1e-05``)."""
    before = expr[:index].rstrip()
    if not before or before[-1] in "(*/+-":
        return False
    return not (
        before[-1] in "eE" and len(before) > 1 and (before[-2].isdigit() or before[-2] == ".")
    )


def _top_level_parts(expr: str, operators: str) -> list[str]:
    """``expr`` split at the ``operators`` outside any parentheses (signs are kept)."""
    parts, depth, start = [], 0, 0
    for index, char in enumerate(expr):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth or char not in operators:
            continue
        if char in "+-" and not _is_binary_sign(expr, index):
            continue
        parts.append(expr[start:index])
        start = index + (char == "*")  # keep the sign of a subtracted term
    parts.append(expr[start:])
    return [_strip_parens(part) for part in parts]


def _distribution_value(formula: str) -> float | None:
    """Return the optimised ``{value}`` of a printed distribution formula, or None.

    Every BluePyEModel distribution has one of two shapes, and only those are read:

    - a product where ``{value}`` is the only plain-number factor (``exp``, ``step``, ...)
    - ``{value}`` plus or minus a term linear in the distance (``linear_e_pas_apic``)

    Anything else has no single reading, so None is returned rather than a guess.
    """
    expr = _strip_parens(formula)
    if DISTANCE not in expr:
        return float(expr) if NUMBER_RE.fullmatch(expr) else None
    terms = _top_level_parts(expr, "+-")
    if len(terms) > 1:
        if (
            len(terms) == LINEAR_DISTRIBUTION_TERMS
            and NUMBER_RE.fullmatch(terms[0])
            and DISTANCE in terms[1]
            and LINEAR_IN_DISTANCE_RE.fullmatch(terms[1].lstrip("+-").replace(DISTANCE, "1"))
        ):
            return float(terms[0])
        return None
    factors = _top_level_parts(expr, "*")
    numbers = [factor for factor in factors if NUMBER_RE.fullmatch(factor)]
    others = [factor for factor in factors if not NUMBER_RE.fullmatch(factor)]
    if len(numbers) == 1 and others and all(DISTANCE in factor for factor in others):
        return float(numbers[0])
    return None


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
    """Read which channels a cell template inserts where, and the values it sets.

    ``HocTemplateError`` propagates when a procedure is missing or holds a line the
    BluePyEModel template cannot print.
    """
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
        mechanisms: Parsed mod files by suffix, covering ``biophysics.mod_file_mechanisms``.

    Returns:
        The ``(variables, channel_mapping)`` pair ``get_mechanism_variables_for_emodel``
        returns. Channel ``entity_id`` is None: the files do not know database IDs.

    Raises:
        HocTemplateError: An inserted mechanism has no mod file.
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
        for name in mechanism.settable_range_variables:
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
