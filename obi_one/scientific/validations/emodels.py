"""Emodels validations."""

from pathlib import Path

BUILTIN_NEURON_MECHANISMS: frozenset[str] = frozenset({"pas", "hh", "extracellular", "capacitance"})

_HOC_TEMPLATE_DECLARATION_PARTS = 2
_MECHANISM_INSERT_PARTS = 2


def check_structure(hoc_path: str | Path) -> None:
    """Checks that the hoc file is a valid hoc template.

    It must contain `begintemplate` and `endtemplate`.
    """
    hoc_content = Path(hoc_path).read_text(encoding="utf-8")

    template_name = None
    for raw_line in hoc_content.splitlines():
        splitted_line = raw_line.strip().split()
        if (
            len(splitted_line) == _HOC_TEMPLATE_DECLARATION_PARTS
            and splitted_line[0] == "begintemplate"
        ):
            template_name = splitted_line[1]
            break

    if template_name is None:
        msg = f"Could not find 'begintemplate' in {hoc_path}"
        raise ValueError(msg)
    if f"endtemplate {template_name}" not in hoc_content:
        msg = f"Could not find 'endtemplate {template_name}' in {hoc_path}"
        raise ValueError(msg)


def check_mechanisms(hoc_path: str | Path, expected_suffixes: set[str]) -> None:
    """Checks that the mechanisms declared in the hoc file are in the expected set."""
    hoc_content = Path(hoc_path).read_text(encoding="utf-8")

    declared_mechanisms = set()
    for raw_line in hoc_content.splitlines():
        splitted_line = raw_line.strip().split()
        if len(splitted_line) == _MECHANISM_INSERT_PARTS and splitted_line[0] == "insert":
            declared_mechanisms.add(splitted_line[1])

    for suffix in declared_mechanisms:
        if suffix not in expected_suffixes and suffix not in BUILTIN_NEURON_MECHANISMS:
            msg = (
                f"Declared mechanism '{suffix}' in {hoc_path} is not in "
                f"expected suffixes {expected_suffixes}"
            )
            raise ValueError(msg)


def bluecellulab_initializable(
    hoc_path: str | Path,
    morphology_path: str | Path,
    template_format: str = "v6",
    holding_current: float = 0.0,
    threshold_current: float = 0.0,
) -> None:
    """Checks that the hoc file can be initialized in bluecellulab.

    Expects mechanisms to be already compiled.
    """
    from bluecellulab import Cell  # noqa: PLC0415
    from bluecellulab.circuit.circuit_access.definition import EmodelProperties  # noqa: PLC0415

    emodel_properties = EmodelProperties(
        holding_current=holding_current, threshold_current=threshold_current
    )
    _ = Cell(
        template_path=hoc_path,
        morphology_path=morphology_path,
        template_format=template_format,
        emodel_properties=emodel_properties,
    )
