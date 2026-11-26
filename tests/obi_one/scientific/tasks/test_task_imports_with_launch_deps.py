"""Each launched task must import under the optional packages its deps file provides.

Parses ``app/mappings.py`` for ``TaskType → launch *.in``, reads the ``obi-one[extras]``
line (and any extra requirement names), then imports that task's ClassRefs with every
*other* optional top-level package blocked. Runtime of missing optionals can still fail;
import must not.
"""

import ast
import re
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from pathlib import Path

import pytest

from obi_one.scientific.mappings_and_registry.config_task_map import TASK_SPECS
from obi_one.types import TaskType

_REPO_ROOT = Path(__file__).resolve().parents[4]
_MAPPINGS_PATH = _REPO_ROOT / "app" / "mappings.py"
_LAUNCH_SCRIPTS = _REPO_ROOT / "launch_scripts"

# Importable top-level names provided by each obi-one optional extra (not transitive commons).
_EXTRA_IMPORT_NAMES: dict[str, frozenset[str]] = {
    "bluecellulab": frozenset({"bluecellulab"}),
    "bluerecording": frozenset({"bluerecording", "neurodamus"}),
    "brian2": frozenset({"brian2"}),
    "circuit-extraction": frozenset({"brainbuilder"}),
    "connectivity": frozenset({"conntility", "connectome_manipulator", "connalysis"}),
    "emodel": frozenset({"bluepyemodel", "bluecellulab"}),
    "meshing": frozenset({"ultraliser"}),
    "simplification": frozenset({"sonata_simplify"}),
    "notebooks": frozenset(),
    "service": frozenset(),
    "all": frozenset(),
}

_ALL_OPTIONAL_IMPORT_NAMES: frozenset[str] = frozenset().union(*_EXTRA_IMPORT_NAMES.values())

_OBI_ONE_REQ = re.compile(
    r"^obi-one(?:\[(?P<extras>[^\]]*)\])?(?:==| @|@|$)",
    re.IGNORECASE,
)
_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _norm_pkg(name: str) -> str:
    return name.lower().replace("-", "_").replace(".", "_")


def _parse_in_allowed_imports(in_path: Path) -> frozenset[str]:
    """Return optional import names allowed by a launch ``*.in`` file."""
    allowed: set[str] = set()
    for raw in in_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        obi = _OBI_ONE_REQ.match(line)
        if obi:
            extras = obi.group("extras") or ""
            for extra in (part.strip() for part in extras.split(",") if part.strip()):
                allowed.update(_EXTRA_IMPORT_NAMES.get(extra, ()))
            continue
        match = _REQ_NAME.match(line)
        if match:
            allowed.add(_norm_pkg(match.group(1)))
    return frozenset(allowed)


def _attr_name(node: ast.AST) -> str | None:
    return node.attr if isinstance(node, ast.Attribute) else None


def _const_str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _task_type_name(node: ast.AST) -> str | None:
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "TaskType"
    ):
        return node.attr
    return None


def _keyword_str(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return _const_str(keyword.value)
    return None


def _deps_basename_from_code_value(node: ast.AST) -> str | None:
    """Resolve ``code=`` value to a launch deps ``*.txt`` basename."""
    if not isinstance(node, ast.Call):
        return None
    fn = node.func.id if isinstance(node.func, ast.Name) else _attr_name(node.func)
    if fn == "_neurodamus_image_code":
        return "neurodamus_image.txt"
    if fn == "_obi_one_code":
        if node.args:
            return _const_str(node.args[0])
        return _keyword_str(node, "deps_name")
    if fn == "PythonRepositoryCode":
        dep = _keyword_str(node, "dependencies")
        return Path(dep).name if dep else None
    return None


def launch_deps_by_task_type() -> dict[TaskType, Path]:
    """Map launchable TaskTypes to their ``*.in`` file under ``launch_scripts/``."""
    tree = ast.parse(_MAPPINGS_PATH.read_text(encoding="utf-8"))
    txt_by_task: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func.id if isinstance(node.func, ast.Name) else _attr_name(node.func)
        if fn not in {"TaskDefinition", "TaskDefinitionLegacy"}:
            continue
        task_name = None
        deps_txt = None
        for keyword in node.keywords:
            if keyword.arg == "task_type":
                task_name = _task_type_name(keyword.value)
            elif keyword.arg == "code":
                deps_txt = _deps_basename_from_code_value(keyword.value)
        if task_name and deps_txt:
            txt_by_task[task_name] = deps_txt

    in_files = {
        path.with_suffix(".txt").name: path
        for path in _LAUNCH_SCRIPTS.rglob("*.in")
        if path.parent.name == "dependencies"
    }
    out: dict[TaskType, Path] = {}
    for name, txt_name in txt_by_task.items():
        in_path = in_files.get(txt_name)
        if in_path is None:
            continue
        out[TaskType[name]] = in_path
    return out


_LAUNCH_DEPS_BY_TASK = launch_deps_by_task_type()


@pytest.mark.parametrize(
    ("task_type", "in_path"),
    sorted(_LAUNCH_DEPS_BY_TASK.items(), key=lambda item: item[0].name),
)
def test_task_imports_with_only_its_launch_optional_packages(task_type: TaskType, in_path: Path):
    """Import task/config ClassRefs with optional packages outside this task's deps blocked."""
    spec = TASK_SPECS.get(task_type)
    if spec is None or spec.task_ref is None:
        pytest.skip(f"{task_type.name} has no TASK_SPECS task_ref")

    allowed = _parse_in_allowed_imports(in_path)
    blocked = sorted(_ALL_OPTIONAL_IMPORT_NAMES - allowed)
    refs = [ref for ref in (spec.task_ref, spec.single_config_ref, spec.scan_config_ref) if ref]
    ref_repr = ", ".join(repr(ref) for ref in refs)
    blocked_repr = repr(blocked)

    script = f"""
import sys

BLOCK = set({blocked_repr})

class BlockFinder:
    def find_spec(self, fullname, path, target=None):
        top = fullname.split(".", 1)[0]
        if top in BLOCK:
            raise ImportError(f"blocked optional package: {{fullname}}")
        return None

for name in list(sys.modules):
    if name.split(".", 1)[0] in BLOCK:
        del sys.modules[name]

sys.meta_path.insert(0, BlockFinder())

from obi_one.utils.lazy_import import import_class

for ref in ({ref_repr},):
    import_class(ref)

loaded = [m for m in sys.modules if m.split(".", 1)[0] in BLOCK]
assert not loaded, loaded
"""
    subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [sys.executable, "-c", script],
        check=True,
    )


def test_launch_deps_mapping_covers_obi_one_code_tasks():
    """Spot-check mappings → .in wiring and allowed optional packages."""
    assert TaskType.circuit_extraction in _LAUNCH_DEPS_BY_TASK
    assert TaskType.circuit_single_build in _LAUNCH_DEPS_BY_TASK
    assert TaskType.em_synapse_mapping in _LAUNCH_DEPS_BY_TASK
    assert TaskType.circuit_simulation_neurodamus_machine in _LAUNCH_DEPS_BY_TASK
    allowed = _parse_in_allowed_imports(_LAUNCH_DEPS_BY_TASK[TaskType.circuit_single_build])
    assert "conntility" not in allowed
    assert "connectome_manipulator" not in allowed
    em_allowed = _parse_in_allowed_imports(_LAUNCH_DEPS_BY_TASK[TaskType.em_synapse_mapping])
    assert "conntility" in em_allowed
    assert "connectome_manipulator" in em_allowed
