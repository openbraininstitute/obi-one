"""Blocks for the 02_emodel_optimization stage."""

import ast
import math
import re
from collections.abc import Mapping
from typing import Annotated, Any, ClassVar, Literal

from bluepyemodel.preprocessing.schemas import (
    AXON_MODIFIER_DESCRIPTIONS,
    DEFAULT_SECTION_LIST_CATALOG,
    REGIONAL_SECTION_LIST_NAMES,
    AxonModifier,
    PhysicalSectionListName,
    RegionalSectionListName,
    SectionListChoice,
    SectionListName,
)
from entitysdk.types import EntityType, TaskResultType
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    FiniteFloat,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.etype_class_from_id import ETypeClassFromID
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID

MIN_CMA_OFFSPRING_SIZE = 2
MAX_OFFSPRING_SIZE = 20
MAX_NGEN = 50

OffspringSize = Annotated[PositiveInt, Field(le=MAX_OFFSPRING_SIZE)]
GenerationCount = Annotated[PositiveInt, Field(le=MAX_NGEN)]


_PLACEHOLDER_PATTERN = re.compile(r"\{(\w+)\}")

# BluePyEModel evaluates the distance function string with Python ``eval()`` at runtime
# (bluepyemodel.model.model.define_distributions). A user-supplied function is therefore
# arbitrary code (e.g. ``__import__('os').system(...)``). To close that hole we parse the
# function into an AST and reject anything outside this whitelist: arithmetic, comparisons,
# the bitwise ``&`` used by the ``step`` distribution, and calls to the two names the
# built-in distributions rely on (``math.<fn>`` and ``int``). No attribute access other
# than ``math.*``, no arbitrary names, no subscripts, comprehensions, lambdas, etc.
_ALLOWED_AST_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.Call,
    ast.Attribute,
    ast.Name,
    ast.Load,
    ast.Constant,
)
_ALLOWED_AST_OPS: tuple[type[ast.AST], ...] = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.USub,
    ast.UAdd,
    ast.BitAnd,
    ast.BitOr,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)
# Names callable directly, and the single module whose members may be accessed/called.
# ``int`` is intentionally excluded: it (and int-returning ``math`` functions) can produce
# arbitrary-precision integers, whose arithmetic (e.g. ``**``) is an unbounded memory/CPU DoS.
# Keeping only float-returning callables guarantees float semantics, which saturate/overflow in
# O(1) instead of allocating unbounded bignums.
_ALLOWED_CALL_NAMES = frozenset({"float", "abs", "min", "max"})
_ALLOWED_MODULES = frozenset({"math"})
_ALLOWED_MATH_FUNCTIONS = frozenset(
    {
        "exp",
        "expm1",
        "log",
        "log1p",
        "log2",
        "log10",
        "sqrt",
        "pow",
        "fabs",
        "hypot",
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "atan2",
        "sinh",
        "cosh",
        "tanh",
        "erf",
        "erfc",
        "degrees",
        "radians",
        "copysign",
        "fmod",
        "remainder",
    }
)
# Float constants on ``math`` that may be referenced directly (e.g. ``math.pi``). Combined with the
# functions, this is the ONLY set of ``math`` attributes allowed; everything else (``__dict__``,
# ``__loader__``, ``__globals__`` on functions, ...) is rejected to prevent introspection escapes.
_ALLOWED_MATH_CONSTANTS = frozenset({"pi", "e", "tau", "inf", "nan"})
_ALLOWED_MATH_ATTRIBUTES = _ALLOWED_MATH_FUNCTIONS | _ALLOWED_MATH_CONSTANTS
# Cap the expression size so a single evaluation is bounded, long expressions becomes a CPU sink).
_MAX_AST_NODES = 50
# Cap the raw string length before parsing.
MAX_DISTANCE_FUNCTION_LENGTH = 500
# Placeholders BluePyEModel fills at runtime from the morphology (not user-declared parameters).
# Only the ``step`` distribution uses them; they are always allowed in placeholder validation.
RUNTIME_PLACEHOLDERS = frozenset({"step_begin", "step_end"})
# Every identifier that may appear as a bare ``Name``. Placeholders are substituted with a
# numeric literal before parsing, so only these module/builtin names should remain.
_ALLOWED_NAMES = _ALLOWED_CALL_NAMES | _ALLOWED_MODULES

# A placeholder is exactly ``{`` + a Python identifier + ``}``. Anything else inside braces
# (a format spec ``{value:>9}``, conversion ``{value!r}``, attribute ``{value.x}``, index
# ``{value[0]}``, or a positional/empty field ``{0}``/``{}``) is rejected before parsing.
_PLACEHOLDER_FIELD_PATTERN = re.compile(r"\{[^{}]*\}")
_BARE_PLACEHOLDER_PATTERN = re.compile(r"\{[A-Za-z_]\w*\}")


def _distance_brace_or_comment_error(function: str) -> tuple[str, int, int] | None:
    """Reject ``#`` comments and non-placeholder brace fields before AST parsing.

    The AST validator never sees ``#`` comments (they are lexed away) and the placeholder
    substitution regex ignores brace fields carrying a spec/conversion (``:``/``!``/``.``/``[``).
    Such a field would survive untouched into bluepyopt's two ``str.format`` passes, where a width
    spec like ``{value:>999999999}`` pads a string to gigabytes (memory-exhaustion DoS). Braces can
    only legitimately be placeholders here, so any brace content that is not a bare identifier, or
    any ``#``, is rejected. Returns ``(reason, from, to)`` or ``None`` when safe.
    """
    hash_index = function.find("#")
    if hash_index != -1:
        return ("'#' (comments are not allowed)", hash_index, len(function))
    for match in _PLACEHOLDER_FIELD_PATTERN.finditer(function):
        if not _BARE_PLACEHOLDER_PATTERN.fullmatch(match.group(0)):
            reason = f"an invalid placeholder {match.group(0)!r} (use {{name}} only)"
            return (reason, match.start(), match.end())
    remaining = _PLACEHOLDER_FIELD_PATTERN.sub("", function)
    stray = remaining.find("{")
    if stray != -1:
        return ("an unbalanced '{'", function.find("{"), len(function))
    stray = remaining.find("}")
    if stray != -1:
        return ("an unbalanced '}'", function.find("}"), len(function))
    return None


def _distance_call_error(node: ast.Call) -> str | None:
    """Return why a call node is disallowed, or None if it is a safe math.*/builtin call."""
    func = node.func
    is_module_call = (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in _ALLOWED_MODULES
    )
    is_builtin_call = isinstance(func, ast.Name) and func.id in _ALLOWED_CALL_NAMES
    if not (is_module_call or is_builtin_call):
        return f"calls are limited to math.* and {sorted(_ALLOWED_CALL_NAMES)}"
    # Only float-returning math functions are allowed; int-returning ones (factorial, comb, ...)
    # would reintroduce unbounded-integer arithmetic.
    if is_module_call and func.attr not in _ALLOWED_MATH_FUNCTIONS:
        return f"math.{func.attr} is not an allowed function"
    if node.keywords:
        return "calls may not use keyword arguments"
    return None


def _distance_attribute_error(node: ast.Attribute) -> str | None:
    """Only ``math.<allowed function/constant>`` may be accessed; blocks introspection escapes."""
    if not (isinstance(node.value, ast.Name) and node.value.id in _ALLOWED_MODULES):
        return "attributes may only be accessed on the math module"
    if node.attr not in _ALLOWED_MATH_ATTRIBUTES:
        return f"math.{node.attr} is not an allowed attribute"
    return None


def _distance_constant_error(node: ast.Constant) -> str | None:
    """Only float literals (and ``bool`` masks) are allowed.

    Integer literals are arbitrary-precision (bignum DoS); strings/bytes enable ``%``-format and
    concatenation allocation bombs (e.g. ``"%10000000s" % x``).
    """
    if isinstance(node.value, (float, bool)):
        return None
    if isinstance(node.value, int):
        return "numeric literals must be floats (write 3.0, not 3)"
    return f"literals must be floats, not {type(node.value).__name__}"


def _distance_leaf_error(node: ast.AST) -> str | None:
    """Check the non-operator leaf nodes (attribute/name/constant/call)."""
    if isinstance(node, ast.Attribute):
        return _distance_attribute_error(node)
    if isinstance(node, ast.Name) and node.id not in _ALLOWED_NAMES:
        return f"disallowed name: {node.id!r}"
    if isinstance(node, ast.Constant):
        return _distance_constant_error(node)
    if isinstance(node, ast.Call):
        return _distance_call_error(node)
    return None


def _distance_node_error(node: ast.AST) -> str | None:
    """Return why ``node`` is disallowed in a distance function, or None if it is safe."""
    if isinstance(node, ast.operator | ast.unaryop | ast.boolop | ast.cmpop):
        allowed = isinstance(node, _ALLOWED_AST_OPS)
        return None if allowed else f"disallowed operator: {type(node).__name__}"
    if not isinstance(node, _ALLOWED_AST_NODES):
        return f"disallowed expression: {type(node).__name__}"
    return _distance_leaf_error(node)


def validate_safe_distance_function(function: str) -> None:
    """Reject distance functions that are not a safe, bounded arithmetic expression.

    The security boundary that prevents arbitrary code (RCE) and unbounded computation (DoS) from
    reaching BluePyEModel/bluepyopt's unsandboxed ``eval``. Enforces, in order:

    - a raw-string length cap (bounds parse-time cost of giant literals),
    - a node-count cap (bounds per-eval CPU),
    - a whitelist of nodes/operators/names/attributes/calls (blocks code execution),
    - float-only numerics: integer literals, ``int()``, and int-returning ``math`` functions are
      rejected, and ``**`` is disallowed, so no arbitrary-precision integer can form. Floats
      saturate to ``inf``/raise ``OverflowError`` in O(1), never allocating unbounded bignums.

    ``{placeholder}`` tokens are not valid Python, so each is substituted with a float literal
    before parsing.
    """
    if len(function) > MAX_DISTANCE_FUNCTION_LENGTH:
        msg = (
            f"Distance function is too long "
            f"({len(function)} chars > {MAX_DISTANCE_FUNCTION_LENGTH})."
        )
        raise ValueError(msg)

    brace_or_comment = _distance_brace_or_comment_error(function)
    if brace_or_comment is not None:
        reason, _, _ = brace_or_comment
        msg = f"Distance function contains {reason}."
        raise ValueError(msg)

    expression = _PLACEHOLDER_PATTERN.sub("1.0", function)
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        msg = f"Distance function is not a valid expression: {exc}."
        raise ValueError(msg) from exc

    node_count = sum(1 for _ in ast.walk(tree))
    if node_count > _MAX_AST_NODES:
        msg = (
            f"Distance function is too complex ({node_count} nodes > {_MAX_AST_NODES}). "
            "Simplify the expression."
        )
        raise ValueError(msg)

    for node in ast.walk(tree):
        reason = _distance_node_error(node)
        if reason is not None:
            msg = f"Distance function contains {reason}."
            raise ValueError(msg)


class DistanceFunctionCheck(BaseModel):
    """Structured result of validating a distance function, for editor feedback.

    ``from_`` / ``to`` are character offsets into the original ``function`` string delimiting the
    offending span (whole string when a position cannot be localized). Both are 0 when valid.
    """

    valid: bool
    error: str | None = None
    from_: int = Field(default=0, alias="from")
    to: int = 0

    model_config = ConfigDict(populate_by_name=True)


def _same_length_placeholder_token(match: re.Match[str]) -> str:
    """A valid float literal the same length as ``{name}`` so AST offsets map to the original."""
    length = len(match.group(0))
    # Shortest placeholder is ``{x}`` (3 chars); ``1.`` + zeros keeps a valid float of equal width.
    return "1." + "0" * (length - 2)


def _distance_pre_parse_check(function: str) -> "DistanceFunctionCheck | None":
    """Length and brace/comment guards that must run before parsing; span-aware, never raises."""
    if len(function) > MAX_DISTANCE_FUNCTION_LENGTH:
        return DistanceFunctionCheck(
            valid=False,
            error=(
                f"Distance function is too long "
                f"({len(function)} chars > {MAX_DISTANCE_FUNCTION_LENGTH})."
            ),
            **{"from": 0},
            to=len(function),
        )
    brace_or_comment = _distance_brace_or_comment_error(function)
    if brace_or_comment is not None:
        reason, start, end = brace_or_comment
        return DistanceFunctionCheck(
            valid=False,
            error=f"Distance function contains {reason}.",
            **{"from": start},
            to=end,
        )
    return None


def check_distance_function(
    function: str, parameters: tuple[str, ...] | None = None
) -> DistanceFunctionCheck:
    """Validate ``function`` and return a structured result with the error span (never raises).

    Mirrors :func:`validate_safe_distance_function` and the placeholder/declaration rules, but
    reports the character span of the first problem instead of raising, so an editor can highlight
    it. Placeholders are substituted with an equal-length token to keep offsets aligned.
    """
    pre_parse = _distance_pre_parse_check(function)
    if pre_parse is not None:
        return pre_parse

    expression = _PLACEHOLDER_PATTERN.sub(_same_length_placeholder_token, function)
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        offset = (exc.offset or 1) - 1
        return DistanceFunctionCheck(
            valid=False,
            error=f"Not a valid expression: {exc.msg}.",
            **{"from": min(offset, len(function))},
            to=len(function),
        )

    node_count = sum(1 for _ in ast.walk(tree))
    if node_count > _MAX_AST_NODES:
        return DistanceFunctionCheck(
            valid=False,
            error=(
                f"Distance function is too complex ({node_count} nodes > {_MAX_AST_NODES}). "
                "Simplify the expression."
            ),
            **{"from": 0},
            to=len(function),
        )

    for node in ast.walk(tree):
        reason = _distance_node_error(node)
        if reason is not None:
            start = getattr(node, "col_offset", 0)
            end = getattr(node, "end_col_offset", len(function))
            return DistanceFunctionCheck(
                valid=False,
                error=f"Distance function contains {reason}.",
                **{"from": start},
                to=end,
            )

    placeholder_error = _distance_placeholder_error(function, parameters)
    if placeholder_error is not None:
        return placeholder_error

    return DistanceFunctionCheck(valid=True)


def _distance_placeholder_error(
    function: str, parameters: tuple[str, ...] | None
) -> DistanceFunctionCheck | None:
    """Check required/declared/undeclared placeholders; return a whole-string error or None."""
    whole = {"from": 0}
    for required in ("value", "distance"):
        if f"{{{required}}}" not in function:
            return DistanceFunctionCheck(
                valid=False,
                error=f"Distance function must contain the {{{required}}} placeholder.",
                **whole,
                to=len(function),
            )
    declared = {"value", "distance", *RUNTIME_PLACEHOLDERS, *(parameters or [])}
    undeclared = sorted(set(_PLACEHOLDER_PATTERN.findall(function)) - declared)
    if undeclared:
        return DistanceFunctionCheck(
            valid=False,
            error=(
                f"Distance function contains undeclared placeholders: {undeclared}. "
                "Add them to 'parameters' or remove them."
            ),
            **whole,
            to=len(function),
        )
    return None


class DistanceDependentDistribution(Block):
    """Scales a parameter along the dendrites as a function of distance from the soma.

    Formulas in subclass docstrings use ``x`` = path distance from soma (um) and
    ``v`` = optimised value at soma.
    """

    _runtime_placeholders: ClassVar[frozenset[str]] = frozenset()

    name: str | None = Field(
        default=None,
        min_length=1,
        title="Distribution name",
        description="Optional name used by BluePyEModel parameter definitions.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    function: str | None = Field(
        default=None,
        max_length=MAX_DISTANCE_FUNCTION_LENGTH,
        title="Distance function",
        description=(
            "Python expression of {value} and {distance}, plus any names listed in parameters."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT_NULLABLE},
    )
    soma_ref_location: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        title="Soma reference location",
        description="Reference location of the soma along the morphology.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT},
    )
    parameters: tuple[str, ...] | None = Field(
        default=None,
        title="Distribution parameters",
        description=(
            "Names of additional parameters that parametrize the function "
            "(excluding {value} and {distance}). Used by BluePyEModel's "
            "ParameterScaler."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_LIST_OPTIONAL},
    )

    @model_validator(mode="after")
    def validate_function(self) -> "DistanceDependentDistribution":
        """Require functions to expose implicit and declared inputs, and be safe.

        BluePyEModel evaluates the function string with Python ``eval()`` at runtime
        (see ``bluepyemodel.model.model.define_distributions()``). Because the string is
        user-controlled, this validator restricts it to a safe arithmetic AST via
        ``validate_safe_distance_function`` before any placeholder/declaration checks.
        """
        if self.parameters and self.function is None:
            msg = "Distance-dependent distributions with parameters must define a function."
            raise ValueError(msg)
        if self.function is not None:
            validate_safe_distance_function(self.function)
        if self.function is not None and "{value}" not in self.function:
            msg = "Distance-dependent functions must contain the {value} placeholder."
            raise ValueError(msg)
        if self.function is not None and "{distance}" not in self.function:
            msg = "Distance-dependent functions must contain the {distance} placeholder."
            raise ValueError(msg)
        if self.function is not None:
            for parameter in self.parameters or []:
                placeholder = f"{{{parameter}}}"
                if placeholder not in self.function:
                    msg = (
                        f"Distance-dependent functions must contain the {placeholder} placeholder."
                    )
                    raise ValueError(msg)
            declared = {"value", "distance", *(self.parameters or []), *self._runtime_placeholders}
            undeclared = set(_PLACEHOLDER_PATTERN.findall(self.function)) - declared
            if undeclared:
                msg = (
                    "Distance-dependent function contains undeclared placeholders: "
                    f"{sorted(undeclared)}. Add them to 'parameters' or remove them."
                )
                raise ValueError(msg)
        return self

    def to_emc_dict(self, name: str | None = None) -> dict[str, Any]:
        """Convert the block to the legacy EMC distribution representation."""
        emc_dict: dict[str, Any] = {
            "name": name or self.name,
            "function": self.function,
            "soma_ref_location": self.soma_ref_location,
        }
        if self.parameters:
            emc_dict["parameters"] = list(self.parameters)
        return emc_dict


class UniformDistanceDependentDistribution(DistanceDependentDistribution):
    """Constant value on all sections; the default for EMC parameters.

    Formula: ``v``.
    """

    title: ClassVar[str] = "Uniform (constant)"

    name: str = Field(
        default="uniform",
        frozen=True,
        title="Distribution name",
        description="Fixed BluePyEModel distribution name.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    function: None = Field(
        default=None,
        frozen=True,
        title="Distance function",
        description="Expression using {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )


class ExponentialDistanceDependentDistribution(DistanceDependentDistribution):
    """Exponential rise with distance; used by SSCX and thalamus models.

    Formula: ``v * (-0.8696 + 2.087 * exp(0.0031 * x))``.
    """

    title: ClassVar[str] = "Exponential increase (SSCX/thalamus)"

    name: str = Field(
        default="exp",
        frozen=True,
        title="Distribution name",
        description="Fixed BluePyEModel distribution name.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    function: str = Field(
        default="(-0.8696 + 2.087*math.exp(({distance})*0.0031))*{value}",
        frozen=True,
        max_length=MAX_DISTANCE_FUNCTION_LENGTH,
        title="Distance function",
        description="Expression using {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT},
    )


class StepDistanceDependentDistribution(DistanceDependentDistribution):
    """Calcium hot-spot step on the apical dendrite; used by detailed SSCX models.

    Formula: ``v`` for ``step_begin < x < step_end``, else ``0.1 * v``.

    ``{step_begin}`` and ``{step_end}`` are not user-declared placeholders.
    BluePyEModel's ``define_distributions()`` special-cases the name ``step`` and
    computes both values from the imported morphology's calcium hot-spot via
    ``get_hotspot_location()`` (Larkum & Zhu, 2002). Do not add them to
    ``parameters``; they must remain in the function string verbatim.
    """

    title: ClassVar[str] = "Step: Ca hot-spot"
    _runtime_placeholders: ClassVar[frozenset[str]] = frozenset({"step_begin", "step_end"})

    name: str = Field(
        default="step",
        frozen=True,
        title="Distribution name",
        description="Fixed BluePyEModel distribution name.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    function: str = Field(
        default="{value} * (0.1 + 0.9 * float(({distance} > {step_begin}) & "
        "({distance} < {step_end})))",
        frozen=True,
        max_length=MAX_DISTANCE_FUNCTION_LENGTH,
        title="Distance function",
        description="Expression using {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT},
    )


class ExponentialNaDendDistanceDependentDistribution(DistanceDependentDistribution):
    """Exponential decay of dendritic Na with distance; used by hippocampus models.

    Formula: ``v * exp(-x / 50)``.
    """

    title: ClassVar[str] = "Exponential decay, dendritic Na (hippocampus)"

    name: str = Field(
        default="exp_na_dend",
        frozen=True,
        title="Distribution name",
        description="Fixed BluePyEModel distribution name.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    function: str = Field(
        default="math.exp((-{distance})/50.)*{value}",
        frozen=True,
        max_length=MAX_DISTANCE_FUNCTION_LENGTH,
        title="Distance function",
        description="Expression using {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT},
    )


class LinearHDApicDistanceDependentDistribution(DistanceDependentDistribution):
    """Linear rise of Ih (hd) with distance; used by hippocampus (rat and mouse) models.

    Replaces BluePyEModel ``linear_hd_apic`` and ``linear_hdpas`` (same formula).
    Formula: ``v * (1 + 0.03 * x)``.
    """

    title: ClassVar[str] = "Linear increase (Ih)"

    name: str = Field(
        default="linear_hd_apic",
        frozen=True,
        title="Distribution name",
        description="Fixed BluePyEModel distribution name.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    function: str = Field(
        default="(1. + 3./100. * {distance})*{value}",
        frozen=True,
        max_length=MAX_DISTANCE_FUNCTION_LENGTH,
        title="Distance function",
        description="Expression using {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT},
    )


class SigmoidKADApicDistanceDependentDistribution(DistanceDependentDistribution):
    """Sigmoid rise of apical KA with distance; used by hippocampus models.

    Formula: ``v * 15 / (1 + exp((300 - x) / 50))``.
    """

    title: ClassVar[str] = "Sigmoid increase, apical KA (hippocampus)"

    name: str = Field(
        default="sigmoid_kad_apic",
        frozen=True,
        title="Distribution name",
        description="Fixed BluePyEModel distribution name.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    function: str = Field(
        default="(15./(1. + math.exp((300.-{distance})/50.)))*{value}",
        frozen=True,
        max_length=MAX_DISTANCE_FUNCTION_LENGTH,
        title="Distance function",
        description="Expression using {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT},
    )


class LinearEPasApicDistanceDependentDistribution(DistanceDependentDistribution):
    """Linear drop of apical e_pas with distance (additive); used by hippocampus models.

    Formula: ``v - x / 30``.
    """

    title: ClassVar[str] = "Linear decrease, apical e_pas (additive)"

    name: str = Field(
        default="linear_e_pas_apic",
        frozen=True,
        title="Distribution name",
        description="Fixed BluePyEModel distribution name.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    function: str = Field(
        default="({value}-5.*{distance}/150.)",
        frozen=True,
        max_length=MAX_DISTANCE_FUNCTION_LENGTH,
        title="Distance function",
        description="Expression using {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT},
    )


class SigmoidKADDistanceDependentDistribution(DistanceDependentDistribution):
    """Sigmoid rise of KA with distance; used by mouse hippocampus models.

    Formula: ``v * 15 / (1 + exp((150 - x) / 10))``.
    """

    title: ClassVar[str] = "Sigmoid increase, KA (mouse)"

    name: str = Field(
        default="sigmoid_kad",
        frozen=True,
        title="Distribution name",
        description="Fixed BluePyEModel distribution name.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    function: str = Field(
        default="(15./(1. + math.exp((150.-{distance})/10.)))*{value}",
        frozen=True,
        max_length=MAX_DISTANCE_FUNCTION_LENGTH,
        title="Distance function",
        description="Expression using {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT},
    )


class SigmoidKDBMApicDistanceDependentDistribution(DistanceDependentDistribution):
    """Sigmoid drop of apical KD with distance; used by mouse hippocampus models.

    Formula: ``v * 15 / (1 + exp((x - 50) / 50))``.
    """

    title: ClassVar[str] = "Sigmoid decrease, apical KD (mouse)"

    name: str = Field(
        default="sigmoid_kdbm_apic",
        frozen=True,
        title="Distribution name",
        description="Fixed BluePyEModel distribution name.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    function: str = Field(
        default="(15./(1. + math.exp(({distance}-50.)/50.)))*{value}",
        frozen=True,
        max_length=MAX_DISTANCE_FUNCTION_LENGTH,
        title="Distance function",
        description="Expression using {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT},
    )


class CustomDistanceDependentDistribution(DistanceDependentDistribution):
    """User-defined distribution for any parameter.

    Formula: the user expression in ``{value}``, ``{distance}`` and declared parameters.
    """

    title: ClassVar[str] = "Custom formula"
    function: str = Field(
        min_length=1,
        max_length=MAX_DISTANCE_FUNCTION_LENGTH,
        title="Custom distance function",
        description="Python expression containing at least {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT},
    )


DistanceDependentDistributionUnion = Annotated[
    UniformDistanceDependentDistribution
    | ExponentialDistanceDependentDistribution
    | StepDistanceDependentDistribution
    | ExponentialNaDendDistanceDependentDistribution
    | LinearHDApicDistanceDependentDistribution
    | SigmoidKADApicDistanceDependentDistribution
    | LinearEPasApicDistanceDependentDistribution
    | SigmoidKADDistanceDependentDistribution
    | SigmoidKDBMApicDistanceDependentDistribution
    | CustomDistanceDependentDistribution,
    Discriminator("type"),
]


class OptimizationInitialize(Block):
    """Entity-based inputs for the optimisation stage's Setup > Initialization card."""

    emodel: str = Field(
        title="E-Model name",
        description="Top-level key in ``recipes.json`` to operate on (e.g. ``L5PC``).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    etype: ETypeClassFromID = Field(
        title="E-type",
        description="Electrical type entity selected from the database.",
        json_schema_extra={
            # ETypeClass is an Identifiable, not an Entity, so model_selector_single
            # (which requires entity_query semantics) does not apply here (per Gil's
            # review). etype_selector is a new, dedicated ui_element for this case.
            SchemaKey.UI_ELEMENT: UIElement.ETYPE_SELECTOR,
            SchemaKey.ENTITY_QUERY: {
                "type": "etype",
            },
        },
    )
    target_efeatures: TaskResultFromID = Field(
        title="Target EFeatures",
        description=(
            "TaskResult entity from the 01_efeature_extraction stage. Its extracted-features "
            "asset is staged as the optimization target configuration."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.TASK_RESULT_SELECTOR,
            # Concrete TaskResult subtype the frontend resolves and filters on.
            SchemaKey.TASK_RESULT_TYPE: TaskResultType.efeature_extraction__result,
        },
    )
    morphology: CellMorphologyFromID = Field(
        title="Cell morphology",
        description=(
            "CellMorphology entity whose SWC asset is staged into ``./morphologies/``. "
            "The m-type, species, and brain region are derived from this entity."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            SchemaKey.ENTITY_QUERY: {"type": EntityType.cell_morphology},
        },
    )


def default_distance_dependent_distributions() -> dict[str, DistanceDependentDistributionUnion]:
    """Custom distance-dependent distributions declared by the user (empty by default).

    The ten legacy distributions from
    ``bluepyemodel.preprocessing.schemas.STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS``
    are always selectable by name without being declared here; this dict only holds
    user-defined distributions (see ``CustomDistanceDependentDistribution``).
    """
    return {}


ParameterLocation = Literal["global"] | SectionListName

REGIONAL_PARAMETER_LOCATIONS: frozenset[RegionalSectionListName] = frozenset(
    REGIONAL_SECTION_LIST_NAMES
)


class OptimizationValue(Block):
    """A fixed value or an optimizable lower/upper bound pair.

    Mode ``fixed`` requires ``value``; mode ``bounds`` requires ``bounds``. The field the mode
    does not use stays null.
    """

    # The JSON schema form of validate_mode, so the frontend can enforce it too.
    json_schema_extra_additions: ClassVar[dict] = {
        "if": {"properties": {"mode": {"const": "bounds"}}, "required": ["mode"]},
        "then": {
            "required": ["bounds"],
            "properties": {"bounds": {"type": "array"}, "value": {"type": "null"}},
        },
        "else": {
            "required": ["value"],
            "properties": {"value": {"type": "number"}, "bounds": {"type": "null"}},
        },
    }

    mode: Literal["fixed", "bounds"] = Field(
        default="fixed",
        title="Value mode",
        description="Choose a fixed value or an optimizable interval.",
    )
    value: FiniteFloat | None = Field(
        default=None,
        title="Fixed value",
        description="Value used when the mode is fixed.",
    )
    # Not tuple[float, float]: its schema types the items with `prefixItems`, which the
    # frontend's draft-07 ajv ignores, so null items would pass. `items` is checked by both.
    bounds: (
        Annotated[
            tuple[FiniteFloat, ...],
            Field(
                min_length=2,
                max_length=2,
                json_schema_extra={SchemaKey.STRICTLY_INCREASING: True},
            ),
        ]
        | None
    ) = Field(
        default=None,
        title="Optimization bounds",
        description=(
            "Lower and upper bounds used when the mode is bounds. The upper bound must be "
            "greater than the lower bound."
        ),
    )

    @model_validator(mode="after")
    def validate_mode(self) -> "OptimizationValue":
        """Require the field of the selected mode only, with increasing bounds."""
        if self.mode == "fixed":
            if self.value is None:
                msg = "A fixed optimization value is required when mode is 'fixed'."
                raise ValueError(msg)
            if self.bounds is not None:
                msg = "Bounds cannot be provided when mode is 'fixed'."
                raise ValueError(msg)
        else:
            if self.bounds is None:
                msg = "Bounds are required when mode is 'bounds'."
                raise ValueError(msg)
            if self.value is not None:
                msg = "A fixed value cannot be provided when mode is 'bounds'."
                raise ValueError(msg)
            if self.bounds[0] >= self.bounds[1]:
                msg = "Optimization upper bound must be greater than the lower bound."
                raise ValueError(msg)
        return self


class ParameterSelection(Block):
    """Value and distance-distribution selection for one regional parameter."""

    value: OptimizationValue
    distribution: str = Field(
        default="uniform",
        min_length=1,
        title="Distance distribution",
        description=(
            "Reusable distance-dependent distribution applied to this regional parameter. "
            "Uniform is the default."
        ),
    )


class GlobalParameterSelection(Block):
    """Value selection for a global parameter."""

    value: OptimizationValue
    ion_channel_model: IonChannelModelFromID | None = Field(
        default=None,
        title="Ion channel model",
        description="Optional source entity when the global variable belongs to a mechanism.",
        json_schema_extra={
            SchemaKey.ENTITY_QUERY: {"type": EntityType.ion_channel_model},
        },
    )


# block_dictionary additionalProperties must expose a discriminated ``oneOf`` even when
# there is currently only one concrete block type (see docs/gui-definition-spec), matching
# the pattern used elsewhere in the codebase (e.g. build_synaptome.SynapticModelPlacerUnion).
ParameterSelectionUnion = Annotated[ParameterSelection, Discriminator("type")]
GlobalParameterSelectionUnion = Annotated[GlobalParameterSelection, Discriminator("type")]
OptimizationValueUnion = Annotated[OptimizationValue, Discriminator("type")]


ParameterGroupKind = Literal["global", "distribution", "region"]


class ParameterRowView(BaseModel):
    """One editable row inside a parameter group, shaped for the Figma parameter cards."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_key: str
    kind: ParameterGroupKind
    key: str
    name: str
    value: OptimizationValue
    location: str
    mechanism: str | None = None
    distribution: str | None = None
    ion_channel_model: IonChannelModelFromID | None = None
    editable: bool = True


class ParameterGroupView(BaseModel):
    """One card in the Figma "Parameters grouped by region" list.

    Groups are always ``global``, then ``distribution``, then regions in the
    section-list catalog's display order. This mirrors the Figma step-4A
    layout, where ``Global`` and ``Distribution parameters`` are separate
    cards, not a single merged list.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    kind: ParameterGroupKind
    label: str
    description: str
    order: int
    item_count: int
    count_label: str
    section_lists: tuple[PhysicalSectionListName, ...] | None = None


class MechanismRegionSelection(Block):
    """One IonChannelModel assigned to a morphology region."""

    ion_channel_model: IonChannelModelFromID = Field(
        title="Ion channel model",
        description="IonChannelModel entity whose mechanism is active in this region.",
        json_schema_extra={
            SchemaKey.ENTITY_QUERY: {"type": EntityType.ion_channel_model},
        },
    )
    parameters: dict[str, ParameterSelectionUnion] = Field(
        default_factory=dict,
        title="Mechanism parameters",
        description="All selected NMODL variables and their values for this region.",
        json_schema_extra={
            SchemaKey.SINGULAR_NAME: "Mechanism Parameter",
        },
    )


AXON_MODIFIER_TITLES: dict[str, str] = {
    AxonModifier.replace_axon_with_taper.value: "Replace axon with taper",
    AxonModifier.replace_axon_legacy.value: "Replace axon (legacy)",
    AxonModifier.replace_axon_olfactory_bulb.value: "Replace axon (olfactory bulb)",
    AxonModifier.bluepyopt_replace_axon.value: "BluePyOpt replace axon",
    AxonModifier.none.value: "No replacement",
}


class MorphologySettings(Block):
    """Morphology transformation settings used by BluePyEModel."""

    axon_modifier: AxonModifier = Field(
        default=AxonModifier.replace_axon_with_taper,
        title="Axon replacement",
        description=(
            "BluePyEModel axon strategy. The default tapered modifier creates a myelinated "
            "section list. Legacy and BluePyOpt replacement do not create one; no replacement "
            "preserves the source morphology, but staged SWC preflight cannot establish a "
            "populated myelinated section list."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.AXON_MODIFIER,
            SchemaKey.TITLE_BY_KEY: AXON_MODIFIER_TITLES,
            SchemaKey.DESCRIPTION_BY_KEY: {
                modifier.value: description
                for modifier, description in AXON_MODIFIER_DESCRIPTIONS.items()
            },
        },
    )

    def to_pipeline_settings(self) -> dict[str, list[str]]:
        """Return the BluePyEModel pipeline setting for the selected modifier."""
        if self.axon_modifier == AxonModifier.none:
            return {"morph_modifiers": []}
        return {"morph_modifiers": [self.axon_modifier.value]}

    @property
    def expected_myelinated(self) -> bool | None:
        """Expected myelination derived from the selected modifier."""
        if self.axon_modifier in {
            AxonModifier.replace_axon_with_taper,
            AxonModifier.replace_axon_olfactory_bulb,
        }:
            return True
        if self.axon_modifier in {
            AxonModifier.replace_axon_legacy,
            AxonModifier.bluepyopt_replace_axon,
        }:
            return False
        return None

    def section_list_choices(self) -> tuple[SectionListChoice, ...]:
        """Return section-list choices for the selected morphology modifier."""
        return DEFAULT_SECTION_LIST_CATALOG.choices(axon_modifier=self.axon_modifier)

    def available_section_list_names(self) -> tuple[SectionListName, ...]:
        """Return section-list names currently selectable in the form."""
        return tuple(choice.name for choice in self.section_list_choices() if choice.available)


def _fixed_parameter(value: float) -> ParameterSelection:
    return ParameterSelection(value=OptimizationValue(value=value))


def _bounded_parameter(lower: float, upper: float) -> ParameterSelection:
    return ParameterSelection(
        value=OptimizationValue(mode="bounds", bounds=(lower, upper)),
    )


# A plain JSON default rather than a default_factory, so it is published in the schema and the
# frontend reads it from there. Fields using it set validate_default=True to get the blocks.
DEFAULT_GLOBAL_PARAMETERS = {
    "v_init": {"type": "GlobalParameterSelection", "value": {"mode": "fixed", "value": -80.0}},
    "celsius": {"type": "GlobalParameterSelection", "value": {"mode": "fixed", "value": 34.0}},
}


def _default_base_parameters() -> dict[SectionListName, dict[str, ParameterSelection]]:
    """Generic passive-cable bootstrap values, not a validated fit for any cell type."""
    return {
        SectionListName.all: {
            "Ra": _fixed_parameter(100.0),
            "g_pas": _bounded_parameter(1e-5, 6e-5),
            "e_pas": _bounded_parameter(-95.0, -60.0),
        },
        SectionListName.axonal: {"cm": _fixed_parameter(1.0)},
        SectionListName.somatic: {"cm": _fixed_parameter(1.0)},
        SectionListName.apical: {"cm": _fixed_parameter(2.0)},
        SectionListName.basal: {"cm": _fixed_parameter(2.0)},
    }


def _duplicate_entity_ids(models: tuple[IonChannelModelFromID, ...]) -> None:
    """Raise if ``models`` contains duplicate entity IDs."""
    selected_ids = {model.id_str for model in models}
    if len(selected_ids) != len(models):
        msg = "ion_channel_models must not contain duplicate entity IDs."
        raise ValueError(msg)


def _validate_mechanism_region_references(
    ion_channel_models: tuple[IonChannelModelFromID, ...],
    mechanism_regions: Mapping[SectionListName, tuple["MechanismRegionSelection", ...]],
) -> None:
    """Ensure every mechanism-region assignment references a catalogued model."""
    selected_ids = {model.id_str for model in ion_channel_models}
    for location, selections in mechanism_regions.items():
        if location not in REGIONAL_PARAMETER_LOCATIONS:
            msg = f"Unsupported mechanism region: {location}."
            raise ValueError(msg)
        for selection in selections:
            if selection.ion_channel_model.id_str not in selected_ids:
                msg = "Every mechanism region entity must also be listed in ion_channel_models."
                raise ValueError(msg)


def _validate_base_parameter_locations(
    base_parameters: Mapping[SectionListName, Mapping[str, "ParameterSelection"]],
) -> None:
    """Ensure ``base_parameters`` keys are valid regional section-list locations."""
    for location in base_parameters:
        if location not in REGIONAL_PARAMETER_LOCATIONS:
            msg = f"Unsupported base parameter region: {location}."
            raise ValueError(msg)


def _validate_global_parameter_references(
    ion_channel_models: tuple[IonChannelModelFromID, ...],
    global_parameters: Mapping[str, "GlobalParameterSelection"],
) -> None:
    """Ensure global-parameter mechanism references were also catalogued."""
    selected_ids = {model.id_str for model in ion_channel_models}
    for name, selection in global_parameters.items():
        if (
            selection.ion_channel_model is not None
            and selection.ion_channel_model.id_str not in selected_ids
        ):
            msg = f"Global parameter '{name}' source must also be listed in ion_channel_models."
            raise ValueError(msg)


class MechanismsBySectionList(Block):
    """Mechanism catalogue and region assignments for the GUI workflow."""

    ion_channel_models: tuple[IonChannelModelFromID, ...] = Field(
        min_length=1,
        max_length=20,
        title="Ion channel models",
        description=(
            "Ion channel model entities available for assignment to morphology section lists."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER_MULTIPLE},
    )
    mechanism_regions: dict[
        SectionListName,
        Annotated[tuple[MechanismRegionSelection, ...], Field(min_length=1)],
    ] = Field(
        min_length=1,
        title="Mechanisms by section list",
        description=(
            "Assign selected ion channel models to BluePyEModel section lists. The same model "
            "may be assigned to multiple section lists."
        ),
        json_schema_extra={
            "choices": DEFAULT_SECTION_LIST_CATALOG.schema_choices(),
            "availability_by_axon_modifier": (
                DEFAULT_SECTION_LIST_CATALOG.schema_availability_by_modifier()
            ),
            "alias_expansions": DEFAULT_SECTION_LIST_CATALOG.to_alias_expansions(),
        },
    )

    @model_validator(mode="after")
    def validate_mechanism_filing(self) -> "MechanismsBySectionList":
        """Validate mechanism filing without requiring conversion to ``ParametersSelection``."""
        _duplicate_entity_ids(self.ion_channel_models)
        _validate_mechanism_region_references(self.ion_channel_models, self.mechanism_regions)
        return self


class EModelOptimisationParameters(Block):
    """Root-level Task 2 mechanism and optimization-parameter configuration."""

    mechanisms: MechanismsBySectionList = Field(
        title="Mechanisms",
        description=(
            "Select ion channel models, assign them to section lists, and configure their "
            "optimization parameters."
        ),
    )
    global_parameters: dict[str, GlobalParameterSelectionUnion] = Field(
        default=DEFAULT_GLOBAL_PARAMETERS,
        validate_default=True,
        title="Global parameters",
        description="Editable global values such as v_init and celsius.",
    )
    base_parameters: dict[SectionListName, dict[str, ParameterSelectionUnion]] = Field(
        default_factory=_default_base_parameters,
        title="Base and passive parameters",
        description="Editable built-in parameters assigned to section lists.",
        json_schema_extra={
            "choices": DEFAULT_SECTION_LIST_CATALOG.schema_choices(),
            "availability_by_axon_modifier": (
                DEFAULT_SECTION_LIST_CATALOG.schema_availability_by_modifier()
            ),
            "alias_expansions": DEFAULT_SECTION_LIST_CATALOG.to_alias_expansions(),
        },
    )
    distribution_parameters: dict[str, dict[str, OptimizationValueUnion]] = Field(
        default_factory=dict,
        title="Distribution parameters",
        description="Values for placeholders declared by sibling distance-dependent distributions.",
    )

    def to_parameters_selection(self) -> "ParametersSelection":
        """Return the canonical selection consumed by validation and compilation."""
        return ParametersSelection(
            ion_channel_models=self.mechanisms.ion_channel_models,
            mechanism_regions=self.mechanisms.mechanism_regions,
            global_parameters=self.global_parameters,
            base_parameters=self.base_parameters,
            distribution_parameters=self.distribution_parameters,
        )

    @classmethod
    def from_parameters_selection(
        cls, selection: "ParametersSelection"
    ) -> "EModelOptimisationParameters":
        """Convert the legacy selection block to the root-level representation."""
        return cls(
            mechanisms=MechanismsBySectionList(
                ion_channel_models=selection.ion_channel_models,
                mechanism_regions=selection.mechanism_regions,
            ),
            global_parameters=selection.global_parameters,
            base_parameters=selection.base_parameters,
            distribution_parameters=selection.distribution_parameters,
        )

    @model_validator(mode="after")
    def validate_cross_field_references(self) -> "EModelOptimisationParameters":
        """Validate global/base parameter references without requiring conversion."""
        _validate_base_parameter_locations(self.base_parameters)
        _validate_global_parameter_references(
            self.mechanisms.ion_channel_models,
            self.global_parameters,
        )
        return self


class ParametersSelection(Block):
    """Canonical internal selection consumed by Task 2 validation and compilation.

    The public GUI configuration is ``EModelOptimisationParameters``. This model is
    retained as the normalized compatibility representation for existing runtime code.
    """

    ion_channel_models: tuple[IonChannelModelFromID, ...] = Field(
        default_factory=tuple,
        title="Ion channel models",
        description=(
            "Ion channel model entities whose .mod assets are staged into mechanisms. "
            "The same entity may be assigned to multiple regions."
        ),
        json_schema_extra={
            SchemaKey.ENTITY_QUERY: {"type": EntityType.ion_channel_model},
        },
    )
    mechanism_regions: dict[SectionListName, tuple[MechanismRegionSelection, ...]] = Field(
        default_factory=dict,
        title="Mechanisms by region",
        description=(
            "Assign selected IonChannelModel entities and parameters to a canonical "
            "BluePyEModel section list. Composite choices expand through the recipe map. "
            "Overlapping rows are preserved and compiled from broad to narrow locations."
        ),
        json_schema_extra={
            SchemaKey.SINGULAR_NAME: "Mechanism Region",
            "choices": DEFAULT_SECTION_LIST_CATALOG.schema_choices(),
            "availability_by_axon_modifier": (
                DEFAULT_SECTION_LIST_CATALOG.schema_availability_by_modifier()
            ),
            "alias_expansions": DEFAULT_SECTION_LIST_CATALOG.to_alias_expansions(),
        },
    )
    global_parameters: dict[str, GlobalParameterSelectionUnion] = Field(
        default=DEFAULT_GLOBAL_PARAMETERS,
        validate_default=True,
        title="Global parameters",
        description=(
            "Editable global values such as v_init and celsius. Shown as the 'Global' card; "
            "see parameter_group_view for the Figma-shaped card list, which keeps distribution "
            "constants on their own 'Distribution parameters' card."
        ),
        json_schema_extra={
            SchemaKey.SINGULAR_NAME: "Global Parameter",
            "derived_view": "parameter_group_view",
        },
    )
    base_parameters: dict[SectionListName, dict[str, ParameterSelectionUnion]] = Field(
        default_factory=_default_base_parameters,
        title="Base and passive parameters",
        description=(
            "Editable built-in parameters such as pas, cm, Ra, g_pas, and e_pas. "
            "Regional rows use the canonical section-list catalog and expose the distance "
            "distribution selector. Overlapping rows are preserved and compiled from broad "
            "to narrow locations."
        ),
        json_schema_extra={
            SchemaKey.SINGULAR_NAME: "Base Parameter Region",
            "choices": DEFAULT_SECTION_LIST_CATALOG.schema_choices(),
            "availability_by_axon_modifier": (
                DEFAULT_SECTION_LIST_CATALOG.schema_availability_by_modifier()
            ),
            "alias_expansions": DEFAULT_SECTION_LIST_CATALOG.to_alias_expansions(),
        },
    )
    distribution_parameters: dict[str, dict[str, OptimizationValueUnion]] = Field(
        default_factory=dict,
        title="Distribution parameters",
        description=(
            "Values for placeholders declared by reusable distance-dependent distributions."
        ),
        json_schema_extra={
            SchemaKey.SINGULAR_NAME: "Distribution Parameter",
        },
    )

    def _global_group_rows(self) -> tuple[ParameterRowView, ...]:
        return tuple(
            ParameterRowView(
                group_key="global",
                kind="global",
                key=name,
                name=name,
                value=selection.value,
                location="global",
                ion_channel_model=selection.ion_channel_model,
            )
            for name, selection in sorted(self.global_parameters.items())
        )

    def _distribution_group_rows(self) -> tuple[ParameterRowView, ...]:
        return tuple(
            ParameterRowView(
                group_key="distribution",
                kind="distribution",
                key=f"distribution_{distribution_name}.{name}",
                name=name,
                value=value,
                location=f"distribution_{distribution_name}",
                distribution=distribution_name,
            )
            for distribution_name in sorted(self.distribution_parameters)
            for name, value in sorted(self.distribution_parameters[distribution_name].items())
        )

    def _region_group_rows(self, location: SectionListName) -> tuple[ParameterRowView, ...]:
        empty_base: dict[str, ParameterSelection] = {}
        base_parameters = self.base_parameters.get(location, empty_base)
        mechanism_assignments = self.mechanism_regions.get(location) or ()
        rows = [
            ParameterRowView(
                group_key=location,
                kind="region",
                key=f"{location}.{name}",
                name=name,
                value=selected.value,
                location=location,
                mechanism="pas" if name in {"g_pas", "e_pas"} else None,
                distribution=selected.distribution,
            )
            for name, selected in sorted(base_parameters.items())
        ]
        rows.extend(
            ParameterRowView(
                group_key=location,
                kind="region",
                key=f"{location}.{assignment.ion_channel_model.id_str}.{name}",
                name=name,
                value=selected.value,
                location=location,
                mechanism=assignment.ion_channel_model.id_str,
                distribution=selected.distribution,
                ion_channel_model=assignment.ion_channel_model,
            )
            for assignment in mechanism_assignments
            for name, selected in sorted(assignment.parameters.items())
        )
        return tuple(rows)

    def parameter_rows(self, group_key: str) -> tuple[ParameterRowView, ...]:
        """Return the editable rows for one parameter-group card."""
        if group_key == "global":
            return self._global_group_rows()
        if group_key == "distribution":
            return self._distribution_group_rows()
        return self._region_group_rows(SectionListName(group_key))

    @property
    def parameter_group_view(self) -> tuple[ParameterGroupView, ...]:
        """Figma-shaped card list: ``Global``, ``Distribution parameters``, then regions.

        Regions are ordered by the section-list catalog's display order and only
        included when they have configured base or mechanism parameters, so the
        card list matches what the user has actually configured.
        """
        groups = [
            ParameterGroupView(
                key="global",
                kind="global",
                label="Global",
                description="Global values such as v_init and celsius.",
                order=0,
                item_count=len(self.global_parameters),
                count_label=f"{len(self.global_parameters)} parameters",
            ),
            ParameterGroupView(
                key="distribution",
                kind="distribution",
                label="Distribution parameters",
                description="Values for placeholders declared by distance-dependent distributions.",
                order=1,
                item_count=sum(len(values) for values in self.distribution_parameters.values()),
                count_label=(
                    f"{sum(len(values) for values in self.distribution_parameters.values())} "
                    "parameters"
                ),
            ),
        ]
        configured_locations = set(self.base_parameters) | set(self.mechanism_regions)
        ordered_choices = sorted(
            (
                choice
                for choice in DEFAULT_SECTION_LIST_CATALOG.choices()
                if choice.name in configured_locations
            ),
            key=lambda choice: choice.display_order,
        )
        for order, choice in enumerate(ordered_choices, start=len(groups)):
            channels_assigned = len(self.mechanism_regions.get(choice.name, ()))
            groups.append(
                ParameterGroupView(
                    key=choice.name,
                    kind="region",
                    label=choice.label,
                    description=choice.description,
                    order=order,
                    item_count=channels_assigned,
                    count_label=f"{channels_assigned} channels assigned",
                    section_lists=DEFAULT_SECTION_LIST_CATALOG.expand(choice.name),
                )
            )
        return tuple(groups)

    @property
    def ion_channel_model_references(self) -> tuple[IonChannelModelFromID, ...]:
        """All referenced IonChannelModel entities, deduplicated by entity ID."""
        references = list(self.ion_channel_models)
        references.extend(
            assignment.ion_channel_model
            for selections in self.mechanism_regions.values()
            for assignment in selections
        )
        references.extend(
            selection.ion_channel_model
            for selection in self.global_parameters.values()
            if selection.ion_channel_model is not None
        )
        unique_references: dict[str, IonChannelModelFromID] = {}
        for reference in references:
            unique_references.setdefault(reference.id_str, reference)
        return tuple(unique_references.values())

    @model_validator(mode="after")
    def validate_selection_references(self) -> "ParametersSelection":
        """Validate locations and ensure regional references were selected."""
        _duplicate_entity_ids(self.ion_channel_models)
        _validate_mechanism_region_references(self.ion_channel_models, self.mechanism_regions)
        _validate_global_parameter_references(self.ion_channel_models, self.global_parameters)
        _validate_base_parameter_locations(self.base_parameters)
        return self


Probability = Annotated[float, Field(ge=0.0, le=1.0)]
ProbabilityValue = Probability | list[Probability]


class EfelSettings(Block):
    """Validated common eFEL settings forwarded through the pipeline recipe."""

    model_config = ConfigDict(extra="forbid")

    strict_stiminterval: bool = Field(
        default=True,
        title="Strict stim interval",
        description="Enforce strict stimulus-interval checks in eFEL feature extraction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    interp_step: PositiveFloat = Field(
        default=0.025,
        title="Interpolation step",
        description="Interpolation step (ms) used by eFEL when resampling traces.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT},
    )

    def to_recipe_dict(self) -> dict[str, Any]:
        """Serialize as the eFEL settings object expected by BluePyEModel.

        The model is closed (``extra="forbid"``): only the declared fields are serialized, so
        every key has a schema and can be validated.
        """
        return self.model_dump(mode="json")


class PhasePlotSettings(Block):
    """Settings for BluePyEModel phase-plot analysis."""

    model_config = ConfigDict(extra="forbid")

    prot_names: tuple[str, ...] = Field(
        default=("idrest",),
        title="Protocol names",
        description="Protocol names used for phase-plot analysis.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_LIST_INPUT},
    )
    amplitude: float = Field(
        default=150.0,
        title="Amplitude",
        description="Stimulus amplitude used for phase-plot analysis.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT},
    )
    amp_window: PositiveFloat = Field(
        default=1.5,
        title="Amplitude window",
        description="Time window (ms) around the amplitude used for phase-plot analysis.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT},
    )
    relative_amp: bool = Field(
        default=True,
        title="Relative amplitude",
        description="Interpret the amplitude as relative to threshold rather than absolute.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_recipe_dict(self) -> dict[str, Any]:
        """Serialize tuple-based form metadata as the recipe list expected by BluePyEModel."""
        return {
            "prot_names": list(self.prot_names),
            "amplitude": self.amplitude,
            "amp_window": self.amp_window,
            "relative_amp": self.relative_amp,
        }


class SineSpecSettings(Block):
    """Settings for optional BluePyEModel SineSpec analysis."""

    model_config = ConfigDict(extra="forbid")

    amp: PositiveFloat = Field(
        default=0.05,
        title="Amplitude",
        description="Stimulus amplitude used for optional SineSpec analysis.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT},
    )
    threshold_based: bool = Field(
        default=False,
        title="Threshold based",
        description="Interpret the amplitude as threshold-based rather than absolute.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_recipe_dict(self) -> dict[str, Any]:
        """Serialize as the SineSpec settings object expected by BluePyEModel."""
        return self.model_dump(mode="json")


class OptimizationParams(Block):
    """Algorithm-specific ``optimisation_params`` passed to BluePyEModel."""

    offspring_size: OffspringSize | list[OffspringSize] = Field(
        default=5,
        title="Offspring size",
        description=(
            "Population size per generation. The L5PC example uses 20; we default"
            " to a small value so the bundled example completes quickly."
            f" Capped at {MAX_OFFSPRING_SIZE}; CMA optimisers need at least 2."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    sigma: PositiveFloat | list[PositiveFloat] | None = Field(
        default=None,
        title="CMA initial sigma",
        description=(
            "Initial standard deviation for SO-CMA or MO-CMA. Leave empty to use "
            "BluePyEModel's optimizer default."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    weight_hv: ProbabilityValue | None = Field(
        default=None,
        title="MO-CMA hypervolume weight",
        description=(
            "Weight of the hypervolume score for MO-CMA. Only valid for MO-CMA; "
            "leave empty to use the BluePyEModel default."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    eta: PositiveFloat | list[PositiveFloat] | None = Field(
        default=None,
        title="IBEA distribution index",
        description="Distribution index for IBEA crossover/mutation. Only valid for IBEA.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    mutpb: ProbabilityValue | None = Field(
        default=None,
        title="IBEA mutation probability",
        description="Mutation probability for IBEA; only valid for IBEA.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    cxpb: ProbabilityValue | None = Field(
        default=None,
        title="IBEA crossover probability",
        description="Crossover probability for IBEA; only valid for IBEA.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    centroids: tuple[float, ...] | None = Field(
        default=None,
        title="CMA centroids",
        description="Optional fixed initial CMA centroid vector; valid for SO-CMA and MO-CMA.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    @model_validator(mode="after")
    def validate_centroids(self) -> "OptimizationParams":
        """Reject invalid CMA centroids."""
        if self.centroids is not None and any(not math.isfinite(value) for value in self.centroids):
            msg = "CMA centroids must contain only finite values."
            raise ValueError(msg)
        return self

    def validate_for_optimiser(self, optimiser: str) -> None:
        """Reject optimizer parameters that BluePyEModel will not consume."""
        cma_values = {
            "sigma": self.sigma,
            "weight_hv": self.weight_hv,
            "centroids": self.centroids,
        }
        ibea_values = {
            "eta": self.eta,
            "mutpb": self.mutpb,
            "cxpb": self.cxpb,
        }
        if optimiser == "IBEA" and any(value is not None for value in cma_values.values()):
            msg = "sigma, weight_hv, and centroids are only valid for SO-CMA or MO-CMA."
            raise ValueError(msg)
        if optimiser != "IBEA" and any(value is not None for value in ibea_values.values()):
            msg = "eta, mutpb, and cxpb are only valid for IBEA."
            raise ValueError(msg)
        if optimiser == "SO-CMA" and self.weight_hv is not None:
            msg = "weight_hv is only valid for MO-CMA."
            raise ValueError(msg)
        if optimiser in {"SO-CMA", "MO-CMA"}:
            offspring_sizes = (
                self.offspring_size
                if isinstance(self.offspring_size, list)
                else [self.offspring_size]
            )
            if any(size < MIN_CMA_OFFSPRING_SIZE for size in offspring_sizes):
                msg = (
                    "CMA offspring_size must be at least "
                    f"{MIN_CMA_OFFSPRING_SIZE} to initialize the optimizer."
                )
                raise ValueError(msg)

    def to_dict(self, optimiser: str = "MO-CMA") -> dict[str, Any]:
        """Serialize only parameters accepted by the selected BluePyEModel optimizer."""
        self.validate_for_optimiser(optimiser)
        result: dict[str, Any] = {"offspring_size": self.offspring_size}
        if optimiser in {"SO-CMA", "MO-CMA"}:
            if self.sigma is not None:
                result["sigma"] = self.sigma
            if self.centroids is not None:
                result["centroids"] = list(self.centroids)
            if optimiser == "MO-CMA" and self.weight_hv is not None:
                result["weight_hv"] = self.weight_hv
        else:
            for name in ("eta", "mutpb", "cxpb"):
                value = getattr(self, name)
                if value is not None:
                    result[name] = value
        return result


class OptimizationSettings(Block):
    """Pydantic form for optimization, evaluation, validation, and analysis recipe settings."""

    optimiser: Literal["SO-CMA", "MO-CMA", "IBEA"] = Field(
        default="SO-CMA",
        title="Optimiser",
        description=(
            "BluePyEModel optimiser. ``SO-CMA`` is single-objective CMA, ``MO-CMA`` is "
            "multi-objective CMA, and ``IBEA`` is the Indicator-Based Evolutionary Algorithm."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    max_ngen: GenerationCount | list[GenerationCount] = Field(
        default=20,
        title="Max generations",
        description=f"Maximum number of optimizer generations (at most {MAX_NGEN}).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    optimisation_timeout: PositiveFloat | list[PositiveFloat] = Field(
        default=300.0,
        title="Optimisation timeout",
        description="Maximum duration in seconds for an optimization evaluation.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    optimisation_checkpoint_period: NonNegativeFloat | list[NonNegativeFloat] | None = Field(
        default=None,
        title="Checkpoint period",
        description=(
            "Minimum seconds between optimization checkpoint writes; empty uses the "
            "backend default."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )
    use_stagnation_criterion: bool = Field(
        default=True,
        title="Use stagnation criterion",
        description="Enable optimizer stagnation stopping in addition to max generations.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    threshold_efeature_std: NonNegativeFloat | list[NonNegativeFloat] | None = Field(
        default=None,
        title="E-feature standard-deviation threshold",
        description=(
            "Optional minimum standard deviation relative to each e-feature mean "
            "during optimization."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )
    minimum_protocol_delay: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        title="Minimum protocol delay",
        description="Minimum initial protocol delay in seconds used by optimization evaluations.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    stochasticity: bool | tuple[str, ...] = Field(
        default=False,
        title="Stochasticity",
        description="Enable stochastic mechanisms globally or only for the listed protocol names.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STOCHASTICITY},
    )
    validation_function: Literal["max_score", "mean_score"] = Field(
        default="max_score",
        title="Validation function",
        description="Safe built-in validation score function used by downstream validation.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    validation_threshold: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Validation threshold",
        description="Score threshold below which a model is considered validated.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    seed: NonNegativeInt | list[NonNegativeInt] = Field(
        default=1,
        title="Random seed",
        description=(
            "Seed forwarded to setup_and_run_optimisation. It is execution-only and is not "
            "written into recipes.json."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    neuron_dt: PositiveFloat | list[PositiveFloat] | None = Field(
        default=None,
        title="NEURON fixed time step",
        description="Simulation time step; empty selects BluePyEModel CVode behavior.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )
    cvode_minstep: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        title="CVode minimum step",
        description="Minimum time step permitted by CVode.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    use_params_for_seed: bool = Field(
        default=True,
        title="Seed simulator from parameters",
        description="Use a hash of the parameter dictionary as the simulator seed.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    current_precision: PositiveFloat | list[PositiveFloat] = Field(
        default=0.01,
        title="Current search precision",
        description="Current interval precision for threshold and rheobase searches.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    max_threshold_voltage: float | list[float] = Field(
        default=-30.0,
        title="Maximum threshold voltage",
        description="Upper voltage bound used during threshold and rheobase searches.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    strict_holding_bounds: bool = Field(
        default=True,
        title="Strict holding-current bounds",
        description="Keep the configured holding-current search bounds fixed.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    max_depth_holding_search: PositiveInt | list[PositiveInt] = Field(
        default=7,
        title="Holding search depth",
        description="Maximum binary-search depth for holding current.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    max_depth_threshold_search: PositiveInt | list[PositiveInt] = Field(
        default=10,
        title="Threshold search depth",
        description="Maximum binary-search depth for threshold current.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    spikecount_timeout: PositiveFloat | list[PositiveFloat] = Field(
        default=50.0,
        title="Spike-count timeout",
        description="Timeout in seconds for spike-count searches.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    default_std_value: PositiveFloat | list[PositiveFloat] = Field(
        default=0.01,
        title="Default std value",
        description="Replacement standard deviation for zero-variance extracted features.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    efel_settings: EfelSettings = Field(
        default=EfelSettings(),
        title="eFEL settings",
        description="Common eFEL settings forwarded to optimization evaluations.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.OBJECT},
    )
    validation_protocols: tuple[str, ...] = Field(
        default=(),
        title="Validation protocols",
        description="Protocol names held out from optimization and used only for validation.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_LIST_INPUT},
    )
    name_rin_protocol: str | None = Field(
        default=None,
        title="Rin protocol name",
        description="Protocol used to compute input resistance; empty disables Rin correction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    name_rmp_protocol: str | None = Field(
        default=None,
        title="RMP protocol name",
        description="Protocol for resting membrane potential; empty disables RMP correction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    plot_optimisation_progress: bool = Field(
        default=True,
        title="Plot optimization progress",
        description="Plot optimizer progress from checkpoints.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_parameter_evolution: bool = Field(
        default=True,
        title="Plot parameter evolution",
        description="Plot parameter evolution during optimization.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_distributions: bool = Field(
        default=True,
        title="Plot distributions",
        description="Plot optimized parameter distributions.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_scores: bool = Field(
        default=True,
        title="Plot scores",
        description="Plot optimization scores.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_traces: bool = Field(
        default=True,
        title="Plot traces",
        description="Plot simulated and target traces.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_thumbnail: bool = Field(
        default=True,
        title="Plot thumbnail",
        description="Plot a thumbnail trace for the resulting model.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_currentscape: bool = Field(
        default=True,
        title="Plot currentscape",
        description="Plot currentscapes for optimization recordings.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_dendritic_ISI_CV: bool = Field(  # ruff: ignore[mixed-case-variable-in-class-scope]
        default=True,
        title="Plot dendritic ISI CV",
        description="Plot dendritic inter-spike-interval coefficient of variation when available.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_dendritic_rheobase: bool = Field(
        default=True,
        title="Plot dendritic rheobase",
        description="Plot dendritic rheobase when available.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_bAP_EPSP: bool = Field(  # ruff: ignore[mixed-case-variable-in-class-scope]
        default=False,
        title="Plot bAP/EPSP",
        description="Run and plot back-propagating action-potential and EPSP protocols.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_IV_curves: bool = Field(  # ruff: ignore[mixed-case-variable-in-class-scope]
        default=False,
        title="Plot IV curves",
        description="Plot IV curves; requires extracted BluePyEfe pickle data.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_FI_curve_comparison: bool = Field(  # ruff: ignore[mixed-case-variable-in-class-scope]
        default=False,
        title="Plot FI curve comparison",
        description="Plot experimental versus simulated FI curves.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    plot_traces_comparison: bool = Field(
        default=False,
        title="Plot trace comparison",
        description="Plot simulated traces over experimental traces.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    run_plot_custom_sinspec: bool = Field(
        default=False,
        title="Run SineSpec plot",
        description="Run and plot the optional SineSpec protocol.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    IV_curve_prot_name: str = Field(
        default="iv",
        min_length=1,
        title="IV curve protocol",
        description="Protocol name used by IV curve analysis.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    FI_curve_prot_name: str = Field(
        default="idrest",
        min_length=1,
        title="FI curve protocol",
        description="Protocol name used by FI curve comparison.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    plot_phase_plot: bool = Field(
        default=False,
        title="Plot phase plot",
        description="Plot the phase trajectory for the configured protocol.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    phase_plot_settings: PhasePlotSettings = Field(
        default=PhasePlotSettings(),
        title="Phase plot settings",
        description="Protocol and amplitude settings for phase-plot analysis.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.OBJECT},
    )
    sinespec_settings: SineSpecSettings = Field(
        default=SineSpecSettings(),
        title="SineSpec settings",
        description="Amplitude settings for optional SineSpec analysis.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.OBJECT},
    )
    custom_bluepyefe_cells_pklpath: str | None = Field(
        default=None,
        title="Custom BluePyEfe cells pickle",
        description="Optional path to a non-standard BluePyEfe cells.pkl file.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    custom_bluepyefe_protocols_pklpath: str | None = Field(
        default=None,
        title="Custom BluePyEfe protocols pickle",
        description="Optional path to a non-standard BluePyEfe protocols.pkl file.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    save_recordings: bool = Field(
        default=False,
        title="Save recordings",
        description="Save optimization response recordings under the task output directory.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_dict(self, optimisation_params: OptimizationParams) -> dict[str, Any]:
        """Serialize validated fields using BluePyEModel's recipe setting names."""
        optimisation_params.validate_for_optimiser(self.optimiser)
        d: dict[str, Any] = {
            "optimiser": self.optimiser,
            "max_ngen": self.max_ngen,
            "optimisation_timeout": self.optimisation_timeout,
            "optimisation_params": optimisation_params.to_dict(self.optimiser),
            "validation_function": self.validation_function,
            "validation_threshold": self.validation_threshold,
            "default_std_value": self.default_std_value,
            "efel_settings": self.efel_settings.to_recipe_dict(),
            "validation_protocols": list(self.validation_protocols),
            "optimisation_checkpoint_period": self.optimisation_checkpoint_period,
            "use_stagnation_criterion": self.use_stagnation_criterion,
            "threshold_efeature_std": self.threshold_efeature_std,
            "minimum_protocol_delay": self.minimum_protocol_delay,
            "stochasticity": (
                list(self.stochasticity)
                if isinstance(self.stochasticity, tuple)
                else self.stochasticity
            ),
            "neuron_dt": self.neuron_dt,
            "cvode_minstep": self.cvode_minstep,
            "use_params_for_seed": self.use_params_for_seed,
            "current_precision": self.current_precision,
            "max_threshold_voltage": self.max_threshold_voltage,
            "strict_holding_bounds": self.strict_holding_bounds,
            "max_depth_holding_search": self.max_depth_holding_search,
            "max_depth_threshold_search": self.max_depth_threshold_search,
            "spikecount_timeout": self.spikecount_timeout,
            "plot_optimisation_progress": self.plot_optimisation_progress,
            "plot_parameter_evolution": self.plot_parameter_evolution,
            "plot_distributions": self.plot_distributions,
            "plot_scores": self.plot_scores,
            "plot_traces": self.plot_traces,
            "plot_thumbnail": self.plot_thumbnail,
            "plot_currentscape": self.plot_currentscape,
            "plot_dendritic_ISI_CV": self.plot_dendritic_ISI_CV,
            "plot_dendritic_rheobase": self.plot_dendritic_rheobase,
            "plot_bAP_EPSP": self.plot_bAP_EPSP,
            "plot_IV_curves": self.plot_IV_curves,
            "plot_FI_curve_comparison": self.plot_FI_curve_comparison,
            "plot_traces_comparison": self.plot_traces_comparison,
            "run_plot_custom_sinspec": self.run_plot_custom_sinspec,
            "IV_curve_prot_name": self.IV_curve_prot_name,
            "FI_curve_prot_name": self.FI_curve_prot_name,
            "plot_phase_plot": self.plot_phase_plot,
            "phase_plot_settings": self.phase_plot_settings.to_recipe_dict(),
            "sinespec_settings": self.sinespec_settings.to_recipe_dict(),
            "save_recordings": self.save_recordings,
        }
        if self.name_rin_protocol is not None:
            d["name_Rin_protocol"] = self.name_rin_protocol
        if self.name_rmp_protocol is not None:
            d["name_rmp_protocol"] = self.name_rmp_protocol
        if self.custom_bluepyefe_cells_pklpath is not None:
            d["custom_bluepyefe_cells_pklpath"] = self.custom_bluepyefe_cells_pklpath
        if self.custom_bluepyefe_protocols_pklpath is not None:
            d["custom_bluepyefe_protocols_pklpath"] = self.custom_bluepyefe_protocols_pklpath
        return d
