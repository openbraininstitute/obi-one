"""Read a cell model's mechanism variables from the files inside a SONATA circuit.

A biophysical circuit ships two kinds of model files:

- ``.hoc`` cell templates, one per ``model_template``, in ``biophysical_neuron_models_dir``.
  They say which mechanism (ion channel) is inserted in which section list (``somatic``,
  ``axonal``...) and the value of each variable there.
- ``.mod`` files (NMODL), one per mechanism, in ``mechanisms_dir``. They name the
  variables a mechanism exposes (``RANGE``, ``GLOBAL``) and their units.

The hoc files are printed by BluePyEModel's Jinja template
(``cell_template_neurodamus_*.jinja2``; format at
https://sonata-extension.readthedocs.io/en/latest/hoc-emodel.html). Inside
``proc insertChannel()`` and ``proc biophys()`` that template prints only three line shapes,
and this module reads only those:

- ``insert <mechanism>`` inside ``forsec this.<section_list> { ... }``
- ``<variable> = <number>`` inside ``forsec CellRef.<section_list> { ... }``
- ``distribute_distance(CellRef.<section_list>, "<variable>", "<formula>")``

Any other line in those two procedures raises ``HocTemplateError``: the file was not made
by the template, and nothing is guessed. GLOBAL values come from the template's
``check_parameter`` calls. Units come from the mod file's ``PARAMETER``, ``ASSIGNED`` and
``STATE`` blocks. NEURON's built-in mechanisms (``pas``, ``hh``...) have no mod file and
are described by ``BUILTIN_MECHANISMS``.

The result has the same types as ``emodel_parameters.get_mechanism_variables_for_emodel``,
so the response builder in ``memodel_circuit`` is shared by both.
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
NUMBER_RE = re.compile(rf"[-+]?{NUMBER_PATTERN.removeprefix('-?')}")
# BluePyOpt prints the distance to the soma into distribution formulas as this placeholder.
DISTANCE = "%.17g"
# A term built only from numbers, the distance, ``*`` and ``/``: the linear part of
# BluePyEModel's ``linear_e_pas_apic`` distribution, ``({value}-5*{distance}/150)``.
LINEAR_IN_DISTANCE_RE = re.compile(r"[0-9.eE*/()\s]+")
LINEAR_DISTRIBUTION_TERMS = 2  # the value, and the term linear in the distance
CHECK_PARAMETER_RE = re.compile(rf'check_parameter\("(\w+)", ({NUMBER_PATTERN}), \1\)')
MOD_BLOCK_RE = re.compile(r"\b(NEURON|PARAMETER|ASSIGNED|STATE)\s*\{(.*?)\n\s*\}", re.DOTALL)
# NMODL does not need a newline between NEURON block statements, so the block is split on
# its keywords rather than its lines.
MOD_NEURON_KEYWORD_RE = re.compile(
    r"\b(SUFFIX|POINT_PROCESS|ARTIFICIAL_CELL|RANGE|GLOBAL|USEION|NONSPECIFIC_CURRENT"
    r"|ELECTRODE_CURRENT|POINTER|BBCOREPOINTER|EXTERNAL|THREADSAFE|REPRESENTS)\b"
)
# ``name (unit)`` or ``name = value (unit)``; a line may declare several names.
MOD_UNIT_RE = re.compile(rf"\b([A-Za-z_]\w*)\s*(?:=\s*{NUMBER_PATTERN}\s*)?\(([^)]*)\)")
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
        units: Variable -> unit, for the variables whose unit is declared.
    """

    suffix: str
    range_variables: list[str] = field(default_factory=list)
    global_variables: list[str] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)

    @property
    def settable_range_variables(self) -> list[str]:
        """RANGE variables a user can set: all but the ionic currents (``ina``, ``ik``...)."""
        return [name for name in self.range_variables if not name.startswith("i")]


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
    """What a cell template's ``insertChannel()`` and ``biophys()`` procedures contain.

    Attributes:
        channels_by_section_list: Section list -> mechanisms inserted there, in file order.
        assignments: (section list, variable) -> value set with ``<variable> = <number>``.
        distributions: (section list, variable) -> value read from a
            ``distribute_distance`` formula, or None when it cannot be read.
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
    """Read the mechanism name, its variables and their units from a ``.mod`` file.

    Comments are removed first, so a block quoted in a ``COMMENT`` is not read.

    Args:
        mod_text: Content of the ``.mod`` file.

    Returns:
        The mechanism as the file declares it.

    Raises:
        HocTemplateError: The file has no ``NEURON`` block or no ``SUFFIX`` in it.
    """
    # A block can appear more than once (``StochKv3.mod`` has two ASSIGNED blocks), so
    # repeated blocks are joined rather than the last one replacing the others.
    blocks: dict[str, str] = {}
    for name, body in MOD_BLOCK_RE.findall(MOD_COMMENT_RE.sub("", mod_text)):
        blocks[name] = f"{blocks.get(name, '')}\n{body}"
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

    mechanism.units = _declared_units(blocks)
    return mechanism


def _declared_units(blocks: dict[str, str]) -> dict[str, str]:
    """Variable -> unit, from the blocks that declare variables with a unit.

    A variable is declared in ``PARAMETER`` (given by the user), ``ASSIGNED`` (computed,
    e.g. a conductance) or ``STATE`` (solved over time, e.g. ``cai``). If several blocks
    give a unit, ``PARAMETER`` wins.
    """
    units: dict[str, str] = {}
    for block in ("STATE", "ASSIGNED", "PARAMETER"):
        for line in blocks.get(block, "").splitlines():
            for match in MOD_UNIT_RE.finditer(line):
                units[match.group(1)] = match.group(2).strip()
    return units


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
    """Whether the ``+`` or ``-`` at ``index`` adds or subtracts, rather than being a sign."""
    before = expr[:index].rstrip()
    if not before or before[-1] in "(*/+-":
        return False  # unary sign
    # The sign of an exponent, as in 1.5e-05.
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
    """Return the optimised value inside a printed distribution formula, or None.

    BluePyOpt prints ``distribute_distance`` formulas from BluePyEModel distributions with
    ``{value}`` (the optimised parameter) and ``{distance}`` substituted. Every built-in
    distribution has one of two shapes, and the value is read only from those:

    - a product with ``{value}`` as one factor: ``exp``, ``exp_na_dend``,
      ``linear_hd_apic``, ``sigmoid_kad_apic``, ``linear_hdpas`` end with ``*{value}``,
      ``step`` starts with ``{value} *``. The value is the only top-level factor that
      is a plain number; every other factor depends on the distance.
    - ``linear_e_pas_apic``, ``({value}-5*{distance}/150)``: a number plus or minus a
      term linear in the distance.

    Anything else (a sum with a function, two plain-number factors) has no single
    reading, so None is returned rather than a guess.
    """
    expr = _strip_parens(formula)
    if DISTANCE not in expr:
        return float(expr) if NUMBER_RE.fullmatch(expr) else None
    terms = _top_level_parts(expr, "+-")
    if len(terms) > 1:  # a sum: only the linear_e_pas_apic shape has a readable value
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

    Args:
        hoc_text: Content of the ``.hoc`` cell template.

    Returns:
        The two procedures' content, plus GLOBAL values and warnings.

    Fails with ``HocTemplateError`` when a procedure is missing, its braces do not
    balance, or it holds a line the BluePyEModel template cannot print.
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
