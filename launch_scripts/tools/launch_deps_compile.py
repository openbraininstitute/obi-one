#!/usr/bin/env python3
"""Compile launch-script requirements: resolve ``*.in`` sources into pinned ``*.txt``.

Runs ``uv pip compile`` for each ``launch_scripts/*/dependencies/*.in`` file,
resolved for the runtime platform (linux/amd64, Python 3.12).

Like ``make compile-deps`` for the project lock file, a plain compile preserves
the versions already pinned in the committed ``*.txt`` and only repins what the
``*.in`` (or obi-one's closure) forces; ``--upgrade`` bumps everything to latest.
``entitysdk`` is always upgraded, mirroring ``make compile-deps``.

``obi-one`` is left unpinned on branches: it is pinned to ``==<version>`` only in
the ``launch-<version>`` tag created for each release (``launch_deps_pin.py``, run
by ``.github/workflows/launch-tag.yml``). Its ``*.in`` line is copied verbatim to
the top of the ``*.txt`` and excluded from the resolver output
(``--no-emit-package obi-one``), while its transitive closure is pinned.

Run ``launch_deps_compile.py --help`` for the arguments.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from launch_deps_common import LAUNCH_SCRIPTS_DIR, OBI_ONE_LINE_REGEX, REPO_ROOT

# Resolution target for the runtime executors. The Python version is derived from
# the ``requires-python`` floor (see ``_python_floor_version``).
PYTHON_PLATFORM = "x86_64-unknown-linux-gnu"
OBI_ONE_PACKAGE = "obi-one"

# Always kept at latest, mirroring the project lock file (``make compile-deps``).
ALWAYS_LATEST_PACKAGE = "entitysdk"

# Default cap on parallel compiles: each one is a network-bound ``uv pip compile``, and
# a handful already reaches roughly the duration of the slowest file.
DEFAULT_MAX_JOBS = 8

# Private OBI package index for packages published only there (e.g. ``ultraliser``,
# ``neuromorphomesh``). Credentials: ``UV_INDEX_OBI_CODEARTIFACT_{USERNAME,PASSWORD}``.
OBI_CODEARTIFACT_INDEX = (
    "https://openbraininstitute-985539765147.d.codeartifact."
    "us-east-1.amazonaws.com/pypi/pypi-prod/simple/"
)


def resolve_in_files(paths: list[str]) -> list[Path]:
    """Resolve CLI ``paths`` to a sorted, de-duplicated list of ``.in`` files.

    Each entry may be an ``.in`` file (compiled directly) or a directory (all
    ``.in`` files found recursively beneath it). With no paths, every
    ``launch_scripts/*/dependencies/*.in`` file is discovered. Raises SystemExit
    if a path does not exist or is not an ``.in`` file / directory.
    """
    if not paths:
        return sorted(LAUNCH_SCRIPTS_DIR.glob("*/dependencies/*.in"))

    found: set[Path] = set()
    for raw in paths:
        path = Path(raw).resolve()
        if path.is_dir():
            found.update(path.glob("**/*.in"))
        elif path.is_file() and path.suffix == ".in":
            found.add(path)
        else:
            msg = f"Not an .in file or directory: {path}"
            raise SystemExit(msg)
    return sorted(found)


def _python_floor_version() -> str:
    """Return the ``requires-python`` lower bound (e.g. "3.12.2").

    Resolving at the lowest supported version keeps the pins installable across
    the whole supported range.
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

    Returning None lets tasks needing only public packages resolve without the
    private index.
    """
    password = os.environ.get("UV_INDEX_OBI_CODEARTIFACT_PASSWORD", "").strip()
    if not password:
        return None
    username = os.environ.get("UV_INDEX_OBI_CODEARTIFACT_USERNAME", "aws").strip() or "aws"
    parts = urlsplit(OBI_CODEARTIFACT_INDEX)
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{parts.netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _build_resolve_input(in_file: Path) -> tuple[str, list[str]]:
    """Build the resolver input, rewriting the obi-one line to the local checkout.

    Replacing ``obi-one[extras]`` with the local project path resolves obi-one's
    closure from the current checkout rather than a published release. Returns the
    rewritten input and the verbatim obi-one lines (to preserve in the output).
    """
    obi_one_lines: list[str] = []
    resolved_lines: list[str] = []
    for raw in in_file.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            resolved_lines.append(raw)
            continue
        m = OBI_ONE_LINE_REGEX.match(stripped)
        if m:
            obi_one_lines.append(stripped)
            extras = m.group("extras")
            extras_suffix = f"[{extras.strip()}]" if extras else ""
            resolved_lines.append(f"{REPO_ROOT.as_posix()}{extras_suffix}")
        else:
            resolved_lines.append(raw)
    return "\n".join(resolved_lines) + "\n", obi_one_lines


def _existing_pins(out_file: Path) -> str:
    """Return the committed ``.txt`` pins (header/obi-one/comments stripped).

    uv preserves the pins from an existing output file unless a change is forced;
    seeding a compile with these gives the pin-preservation behavior.
    """
    if not out_file.exists():
        return ""
    kept: list[str] = []
    for raw in out_file.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if OBI_ONE_LINE_REGEX.match(stripped):
            continue
        kept.append(stripped)
    return ("\n".join(kept) + "\n") if kept else ""


def compile_in_file(in_file: Path, *, upgrade: bool = False) -> str:
    """Compile a single ``.in`` file and return the frozen ``.txt`` content.

    Unless ``upgrade`` is set, versions already pinned in the committed ``.txt``
    are preserved (uv only changes what the ``.in`` / obi-one closure forces).
    ``entitysdk`` is always upgraded to its latest version regardless.
    """
    resolve_input, obi_one_lines = _build_resolve_input(in_file)
    out_file = in_file.with_suffix(".txt")

    out_fd, out_name = tempfile.mkstemp(suffix=".txt")
    os.close(out_fd)
    tmp_out = Path(out_name)
    in_fd, in_name = tempfile.mkstemp(suffix=".in")
    tmp_in = Path(in_name)
    with os.fdopen(in_fd, "w", encoding="utf-8") as tmp_in_f:
        tmp_in_f.write(resolve_input)
    try:
        # Seed the output with the current pins so uv preserves them, unless
        # upgrading everything.
        if not upgrade:
            seed = _existing_pins(out_file)
            if seed:
                tmp_out.write_text(seed, encoding="utf-8")

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
            # "# via" annotations reference the temporary input path (non-reproducible).
            "--no-annotate",
            "--upgrade-package",
            ALWAYS_LATEST_PACKAGE,
        ]
        if upgrade:
            cmd.append("--upgrade")
        extra_index = _codeartifact_index_url()
        if extra_index is not None:
            cmd += ["--extra-index-url", extra_index]
        # Discover obi-one's closure from the local project but do not pin obi-one
        # itself: it is pinned only in the release's launch tag.
        if obi_one_lines:
            cmd += ["--no-emit-package", OBI_ONE_PACKAGE]

        # Output is captured so that parallel compiles do not interleave; on failure
        # it is available as CalledProcessError.stderr.
        subprocess.run(cmd, check=True, cwd=REPO_ROOT, capture_output=True, text=True)
        compiled = tmp_out.read_text(encoding="utf-8")
    finally:
        tmp_out.unlink(missing_ok=True)
        tmp_in.unlink(missing_ok=True)

    header = (
        f"# This file was autogenerated from {in_file.name} by "
        "launch_scripts/tools/launch_deps_compile.py.\n"
        "# To update, run: make compile-launch-deps or make upgrade-launch-deps\n"
    )
    if obi_one_lines:
        header += (
            "# obi-one is intentionally left unpinned here; it is pinned to the release\n"
            "# version in the launch-<version> tag created at release time.\n"
        )
    obi_one_block = ("\n".join(obi_one_lines) + "\n") if obi_one_lines else ""
    return header + obi_one_block + compiled


def check_in_txt_pairing(in_files: list[Path]) -> bool:
    """Warn about unpaired .in/.txt files. Returns True if any mismatch is found.

    Checks the ``dependencies`` directories that contain the resolved ``in_files``
    (so selecting a subset only checks the relevant directories). When ``in_files``
    is empty, all launch-script dependencies directories are checked so that a
    directory holding only orphan ``.txt`` files is still caught.
    """
    if in_files:
        dirs = {p.parent for p in in_files}
    else:
        dirs = {p.parent for p in LAUNCH_SCRIPTS_DIR.glob("*/dependencies/*.in")}
        dirs |= {p.parent for p in LAUNCH_SCRIPTS_DIR.glob("*/dependencies/*.txt")}
    mismatch = False
    for deps_dir in sorted(dirs):
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


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        msg = f"must be >= 1, got {n}"
        raise argparse.ArgumentTypeError(msg)
    return n


def _compile_or_error(in_file: Path, *, upgrade: bool) -> str | subprocess.CalledProcessError:
    """Compile ``in_file``, returning the uv failure instead of raising it."""
    try:
        return compile_in_file(in_file, upgrade=upgrade)
    except subprocess.CalledProcessError as e:
        return e


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help=(
            "Paths to compile: individual .in files and/or directories (searched "
            "recursively for .in files). Defaults to all launch-script .in files."
        ),
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Upgrade the whole transitive closure to the latest versions",
    )
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
    parser.add_argument(
        "--jobs",
        type=_positive_int,
        default=min(DEFAULT_MAX_JOBS, os.cpu_count() or 1),
        help="Number of files compiled in parallel (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    in_files = resolve_in_files(args.paths)
    pairing_error = check_in_txt_pairing(in_files)

    if not in_files:
        print("No .in files found.", file=sys.stderr)
        return 1 if pairing_error else 0

    # Each compile is an independent, network-bound uv subprocess, so threads suffice.
    # Results are then handled in file order, keeping the output deterministic.
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        results = list(executor.map(lambda f: _compile_or_error(f, upgrade=args.upgrade), in_files))

    stale: list[Path] = []
    skipped: list[Path] = []
    for in_file, content in zip(in_files, results, strict=True):
        out_file = in_file.with_suffix(".txt")
        if isinstance(content, subprocess.CalledProcessError):
            print(content.stderr or "", end="", file=sys.stderr)
            if args.skip_unresolvable:
                skipped.append(in_file)
                print(
                    f"SKIP (unresolvable): {in_file.relative_to(REPO_ROOT)}",
                    file=sys.stderr,
                )
                continue
            raise content
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
            "Run `make compile-launch-deps` and commit the result.",
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
