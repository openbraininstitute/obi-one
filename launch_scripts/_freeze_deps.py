#!/usr/bin/env python3
"""Freeze launch-script requirements: compile ``*.in`` sources into pinned ``*.txt``.

For each ``launch_scripts/*/dependencies/*.in`` source file this script runs
``uv pip compile`` to produce a fully-pinned sibling ``*.txt`` file, resolved for
the runtime platform (linux/amd64, Python 3.12).

The ``obi-one`` package itself is intentionally left *unpinned* in the output:
its version is pinned dynamically at task-submission time via the launch-system
``dependency_constraints`` mechanism (see ``app/dependencies/constraints.py``).
Accordingly, the ``obi-one[...]`` requirement line(s) from the ``.in`` file are
copied verbatim to the top of the generated ``.txt`` and excluded from the
resolver output (``uv pip compile --no-emit-package obi-one``), while the
transitive dependency closure is fully pinned.

``.in`` files that do not reference ``obi-one`` (e.g. the slim ``minimal.in``
alternative) are compiled normally, pinning every listed package.

Usage:
    python launch_scripts/_freeze_deps.py [--task <launch_dir_name>] [--check]

Options:
    --task   Restrict to a single ``launch_scripts/<task>`` directory.
    --check  Do not write; exit non-zero if any generated output would differ
             from the committed ``.txt`` (used by CI to detect stale files).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

# Resolution target for the runtime executors (linux/amd64). The Python version
# is derived from the project's ``requires-python`` lower bound (see
# ``_python_floor_version``) so the local project resolves and the pins stay
# installable across the whole supported range.
PYTHON_PLATFORM = "x86_64-unknown-linux-gnu"
OBI_ONE_PACKAGE = "obi-one"

# Private OBI package index (AWS CodeArtifact). Some launch tasks depend on
# packages published only here (e.g. ``ultraliser``, ``neuromorphomesh``).
# Authentication is provided via the ``UV_INDEX_OBI_CODEARTIFACT_USERNAME`` /
# ``UV_INDEX_OBI_CODEARTIFACT_PASSWORD`` environment variables (the obi-one
# Makefile exports these using ``aws codeartifact get-authorization-token``).
OBI_CODEARTIFACT_INDEX = (
    "https://openbraininstitute-985539765147.d.codeartifact."
    "us-east-1.amazonaws.com/pypi/pypi-prod/simple/"
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCH_SCRIPTS_DIR = REPO_ROOT / "launch_scripts"

# Matches a top-level ``obi-one`` / ``obi_one`` requirement line (with optional
# extras and/or version specifier). Kept in sync with
# ``app/dependencies/constraints.py``.
_OBI_ONE_LINE_REGEX = re.compile(
    r"^\s*obi[-_]one(?:\[(?P<extras>[A-Za-z0-9._,\s-]+)\])?\s*(?:[<>=!~;].*)?$"
)


def discover_in_files(task: str | None) -> list[Path]:
    """Return the sorted list of ``.in`` files to compile."""
    if task:
        base = LAUNCH_SCRIPTS_DIR / task / "dependencies"
        if not base.is_dir():
            msg = f"No dependencies directory found for task {task!r}: {base}"
            raise SystemExit(msg)
        return sorted(base.glob("*.in"))
    return sorted(LAUNCH_SCRIPTS_DIR.glob("*/dependencies/*.in"))


def _python_floor_version() -> str:
    """Return the lower bound of the project's ``requires-python`` (e.g. "3.12.2").

    Resolving at the lowest supported version keeps the frozen pins installable
    across the whole supported range, rather than pinning packages that need a
    newer patch release than some executor provides.
    """
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requires_python = pyproject["project"]["requires-python"]  # e.g. ">=3.12.2,<3.13"
    m = re.search(r">=\s*([0-9]+(?:\.[0-9]+)*)", requires_python)
    if not m:
        msg = f"Could not parse a '>=' lower bound from requires-python={requires_python!r}"
        raise SystemExit(msg)
    return m.group(1)


def _codeartifact_index_url() -> str | None:
    """Return the CodeArtifact index URL with credentials, or None if unauthed.

    Credentials come from the ``UV_INDEX_OBI_CODEARTIFACT_USERNAME`` /
    ``UV_INDEX_OBI_CODEARTIFACT_PASSWORD`` environment variables (set by the
    Makefile via ``aws codeartifact get-authorization-token``). If no
    password/token is available we return None so that tasks needing only public
    packages still resolve without the private index.
    """
    password = os.environ.get("UV_INDEX_OBI_CODEARTIFACT_PASSWORD", "").strip()
    if not password:
        return None
    username = os.environ.get("UV_INDEX_OBI_CODEARTIFACT_USERNAME", "aws").strip() or "aws"
    parts = urlsplit(OBI_CODEARTIFACT_INDEX)
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{parts.netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _build_resolve_input(in_file: Path) -> tuple[str, list[str]]:
    """Build the resolver input, rewriting obi-one -> local project path.
    The named ``obi-one[extras]`` requirement is replaced with the local project
    path (``<repo>[extras]``) so the resolver uses the *current checkout* and its
    optional dependencies, rather than a published release. Non-obi-one lines are
    passed through unchanged. Returns the rewritten input text and the list of
    verbatim obi-one lines to preserve in the output.
    """
    obi_one_lines: list[str] = []
    resolved_lines: list[str] = []
    for raw in in_file.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            resolved_lines.append(raw)
            continue
        m = _OBI_ONE_LINE_REGEX.match(stripped)
        if m:
            obi_one_lines.append(stripped)
            extras = m.group("extras")
            extras_suffix = f"[{extras.strip()}]" if extras else ""
            # Resolve obi-one from the local project checkout, with the extras.
            resolved_lines.append(f"{REPO_ROOT.as_posix()}{extras_suffix}")
        else:
            resolved_lines.append(raw)
    return "\n".join(resolved_lines) + "\n", obi_one_lines


def compile_in_file(in_file: Path) -> str:
    """Compile a single ``.in`` file and return the frozen ``.txt`` content."""
    resolve_input, obi_one_lines = _build_resolve_input(in_file)

    out_fd, out_name = tempfile.mkstemp(suffix=".txt")
    os.close(out_fd)
    tmp_out = Path(out_name)
    in_fd, in_name = tempfile.mkstemp(suffix=".in")
    tmp_in = Path(in_name)
    with os.fdopen(in_fd, "w", encoding="utf-8") as tmp_in_f:
        tmp_in_f.write(resolve_input)
    try:
        cmd = [
            "uv",
            "pip",
            "compile",
            str(tmp_in),
            "--output-file",
            str(tmp_out),
            "--python-platform",
            PYTHON_PLATFORM,
            "--python-version",
            _python_floor_version(),
            "--no-header",  # we write our own header
            # Drop "# via" annotations: they would reference the temporary input
            # file path (non-reproducible) and are not needed in a pinned lock.
            "--no-annotate",
        ]
        # Make the private OBI index available for packages published only there
        # (e.g. ultraliser, neuromorphomesh) when credentials are present. The
        # obi-one Makefile exports UV_INDEX_OBI_CODEARTIFACT_{USERNAME,PASSWORD}
        # using ``aws codeartifact get-authorization-token``. Without a token we
        # skip the index so tasks that only need public packages still resolve.
        extra_index = _codeartifact_index_url()
        if extra_index is not None:
            cmd += ["--extra-index-url", extra_index]
        # Resolve obi-one (from the local project) to discover the transitive
        # closure, but do not emit an obi-one== pin: the version is applied
        # dynamically at submission time.
        if obi_one_lines:
            cmd += ["--no-emit-package", OBI_ONE_PACKAGE]

        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
        compiled = tmp_out.read_text(encoding="utf-8")
    finally:
        tmp_out.unlink(missing_ok=True)
        tmp_in.unlink(missing_ok=True)

    header = (
        f"# This file was autogenerated from {in_file.name} by "
        "launch_scripts/_freeze_deps.py.\n"
        "# To update, run: make freeze-launch-deps\n"
    )
    if obi_one_lines:
        header += (
            "# obi-one is intentionally left unpinned here; its version is pinned\n"
            "# dynamically at task-submission time (dependency_constraints).\n"
        )
    obi_one_block = ("\n".join(obi_one_lines) + "\n") if obi_one_lines else ""
    return header + obi_one_block + compiled


def _check_in_txt_pairing(task: str | None) -> bool:
    """Warn about unpaired .in/.txt files. Returns True if any mismatch is found."""
    if task:
        dirs = [LAUNCH_SCRIPTS_DIR / task / "dependencies"]
    else:
        dirs = sorted({p.parent for p in LAUNCH_SCRIPTS_DIR.glob("*/dependencies/*.in")})
        dirs += sorted({p.parent for p in LAUNCH_SCRIPTS_DIR.glob("*/dependencies/*.txt")})
    mismatch = False
    for deps_dir in sorted(set(dirs)):
        if not deps_dir.is_dir():
            continue
        in_stems = {p.stem for p in deps_dir.glob("*.in")}
        txt_stems = {p.stem for p in deps_dir.glob("*.txt")}
        for stem in sorted(in_stems - txt_stems):
            mismatch = True
            print(f"MISSING .txt for {deps_dir.relative_to(REPO_ROOT)}/{stem}.in", file=sys.stderr)
        for stem in sorted(txt_stems - in_stems):
            mismatch = True
            print(f"MISSING .in for {deps_dir.relative_to(REPO_ROOT)}/{stem}.txt", file=sys.stderr)
    return mismatch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default=None, help="Restrict to one launch_scripts/<task> dir")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; fail if any committed .txt is stale",
    )
    parser.add_argument(
        "--skip-unresolvable",
        action="store_true",
        help=(
            "Skip (with a warning) any .in whose dependencies cannot be resolved "
            "instead of failing. Useful when private packages are unavailable."
        ),
    )
    args = parser.parse_args()

    pairing_error = _check_in_txt_pairing(args.task)

    in_files = discover_in_files(args.task)
    if not in_files:
        print("No .in files found.", file=sys.stderr)
        return 1 if pairing_error else 0

    stale: list[Path] = []
    skipped: list[Path] = []
    for in_file in in_files:
        out_file = in_file.with_suffix(".txt")
        try:
            content = compile_in_file(in_file)
        except subprocess.CalledProcessError:
            if args.skip_unresolvable:
                skipped.append(in_file)
                print(
                    f"SKIP (unresolvable): {in_file.relative_to(REPO_ROOT)}",
                    file=sys.stderr,
                )
                continue
            raise
        if args.check:
            existing = out_file.read_text(encoding="utf-8") if out_file.exists() else ""
            if existing != content:
                stale.append(out_file)
                print(f"STALE: {out_file.relative_to(REPO_ROOT)}", file=sys.stderr)
            else:
                print(f"ok: {out_file.relative_to(REPO_ROOT)}")
        else:
            out_file.write_text(content, encoding="utf-8")
            print(f"wrote: {out_file.relative_to(REPO_ROOT)}")

    if skipped:
        print(
            f"\nSkipped {len(skipped)} file(s) with unresolvable dependencies "
            "(e.g. private packages needing CodeArtifact auth). "
            "Regenerate them in an authenticated environment.",
            file=sys.stderr,
        )
    if args.check and stale:
        print(
            f"\n{len(stale)} frozen requirements file(s) are out of date. "
            "Run `make freeze-launch-deps` and commit the result.",
            file=sys.stderr,
        )
        return 1
    if pairing_error:
        print(
            "\nEvery .in must have a matching .txt and vice versa.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
