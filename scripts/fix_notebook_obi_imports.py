"""Update notebook imports after slimming obi_one.__init__ without reformatting cells."""

import ast
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Symbols used as obi.X but not exported from main obi_one.__init__ (never were on root).
EXTRA_SYMBOL_MODULES: dict[str, str] = {
    "AllNeurons": "obi_one.scientific.blocks.neuron_sets.deprecated",
    "PairMotifNeuronSet": "obi_one.scientific.blocks.neuron_sets.old.pair",
    "SimplexNeuronSet": "obi_one.scientific.blocks.neuron_sets.old.simplex",
    "VolumetricCountNeuronSet": "obi_one.scientific.blocks.neuron_sets.old.volumetric",
}

OBI_IMPORT_LINE = re.compile(r"^\s*import obi_one as obi\s*$")
FROM_OBI_ONE_LINE = re.compile(r"^\s*from obi_one import (.+)\s*$")
OBI_SYMBOL = re.compile(r"\bobi\.([A-Z][A-Za-z0-9_]*)")


def load_symbol_map() -> dict[str, str]:
    main_init = subprocess.check_output(
        ["git", "show", "origin/main:obi_one/__init__.py"],
        cwd=REPO,
        text=True,
    )
    symbol_to_module: dict[str, str] = {}
    for node in ast.parse(main_init).body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or not node.module.startswith("obi_one"):
            continue
        for alias in node.names:
            symbol_to_module[alias.asname or alias.name] = node.module
    symbol_to_module.update(EXTRA_SYMBOL_MODULES)
    return symbol_to_module


def load_root_names() -> set[str]:
    current_init = (REPO / "obi_one" / "__init__.py").read_text()
    match = re.search(r"__all__\s*=\s*(\[[^\]]+\])", current_init, re.S)
    if not match:
        msg = "Could not parse obi_one.__init__.__all__"
        raise RuntimeError(msg)
    names = set(ast.literal_eval(match.group(1)))
    return names | {"LAB_ID_STAGING_TEST", "PROJECT_ID_STAGING_TEST"}


def source_to_text(source: list[str] | str) -> str:
    if isinstance(source, str):
        return source
    return "".join(source)


def text_to_source(text: str, template: list[str] | str) -> list[str] | str:
    if isinstance(template, str):
        return text
    if not text:
        return []
    lines = text.splitlines(keepends=True)
    if isinstance(template, list) and template and not template[-1].endswith("\n"):
        if lines and lines[-1].endswith("\n"):
            lines[-1] = lines[-1][:-1]
    return lines


def format_imports(module_to_symbols: dict[str, set[str]]) -> list[str]:
    lines: list[str] = []
    for module in sorted(module_to_symbols):
        symbols = sorted(module_to_symbols[module])
        if module == "obi_one":
            lines.append(f"from obi_one import {', '.join(symbols)}\n")
            continue
        if len(symbols) == 1:
            lines.append(f"from {module} import {symbols[0]}\n")
            continue
        lines.append(f"from {module} import (\n")
        for sym in symbols:
            lines.append(f"    {sym},\n")
        lines.append(")\n")
    return lines


def existing_imported_symbols(text: str) -> set[str]:
    found: set[str] = set()
    for line in text.splitlines():
        m = FROM_OBI_ONE_LINE.match(line)
        if m:
            part = m.group(1).strip()
            if part.startswith("("):
                continue
            for chunk in part.split(","):
                name = chunk.strip().split(" as ")[0].strip()
                if name:
                    found.add(name)
    return found


def process_notebook(
    path: Path,
    symbol_to_module: dict[str, str],
    root_names: set[str],
) -> bool:
    raw = path.read_text(encoding="utf-8")
    nb = json.loads(raw)
    changed = False

    used: set[str] = set()
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        text = source_to_text(cell.get("source", []))
        used.update(OBI_SYMBOL.findall(text))
        m = FROM_OBI_ONE_LINE.search(text)
        if m:
            part = m.group(1).strip()
            if not part.startswith("("):
                for chunk in part.split(","):
                    name = chunk.strip().split(" as ")[0].strip()
                    if name:
                        used.add(name)

    if not used and "import obi_one as obi" not in raw:
        return False

    module_to_symbols: dict[str, set[str]] = defaultdict(set)
    for sym in sorted(used):
        if sym in root_names:
            module_to_symbols["obi_one"].add(sym)
            continue
        mod = symbol_to_module.get(sym)
        if mod is None:
            print(f"{path}: unknown symbol {sym!r}", file=sys.stderr)
            continue
        module_to_symbols[mod].add(sym)

    import_lines = format_imports(module_to_symbols)
    obi_import_inserted = False

    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", [])
        text = source_to_text(source)
        needs_import_cell = (
            "obi." in text
            or "import obi_one as obi" in text
            or FROM_OBI_ONE_LINE.search(text) is not None
        )
        if not needs_import_cell:
            continue

        new_text = re.sub(r"\bobi\.", "", text)

        out_lines: list[str] = []
        for line in new_text.splitlines(keepends=True):
            if OBI_IMPORT_LINE.match(line.rstrip("\n")):
                if not obi_import_inserted and import_lines:
                    out_lines.extend(import_lines)
                    obi_import_inserted = True
                changed = True
                continue
            stripped = line.rstrip("\n")
            m = FROM_OBI_ONE_LINE.match(stripped)
            if m:
                names = {
                    chunk.strip().split(" as ")[0].strip()
                    for chunk in m.group(1).split(",")
                    if chunk.strip() and not chunk.strip().startswith("(")
                }
                if names & used and not names <= root_names:
                    if not obi_import_inserted and import_lines:
                        out_lines.extend(import_lines)
                        obi_import_inserted = True
                    changed = True
                    continue
            out_lines.append(line)

        new_text = "".join(out_lines)
        if new_text != text:
            changed = True
        cell["source"] = text_to_source(new_text, source)

    if import_lines and not obi_import_inserted:
        for cell in nb.get("cells", []):
            if cell.get("cell_type") != "code":
                continue
            source = cell.get("source", [])
            text = source_to_text(source)
            if not text.strip():
                continue
            already = existing_imported_symbols(text)
            missing = [ln for ln in import_lines if not any(s in already for s in used)]
            if missing:
                cell["source"] = text_to_source("".join(missing) + text, source)
                changed = True
            break

    if not changed:
        return False

    path.write_text(
        json.dumps(nb, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    return True


def main(argv: list[str]) -> int:
    symbol_to_module = load_symbol_map()
    root_names = load_root_names()
    paths = [Path(p) for p in argv] if argv else []
    if not paths:
        list_file = Path("/tmp/pr_ipynb.txt")
        if list_file.is_file():
            paths = [REPO / line for line in list_file.read_text().splitlines() if line.strip()]
    updated = 0
    for path in paths:
        if process_notebook(path, symbol_to_module, root_names):
            updated += 1
            print(path)
    print(f"Updated {updated} notebook(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
