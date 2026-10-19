#!/usr/bin/env python3
"""Pin obi-one to a release version in the launch-script requirements.

Rewrites every obi-one line of the compiled ``launch_scripts/*/dependencies/*.txt``
files to ``obi-one[extras]==<version>``, leaving every other byte untouched. Lines
may be bare (before the first release) or pinned to a previous release. Run by
``.github/workflows/release-pin.yml`` on ``main`` for each release: the transitive
closure in those files was compiled against ``main``'s source, so re-pinning the
obi-one line alone is consistent.

With ``--check`` nothing is written: the tool fails unless every obi-one line is
already pinned to ``<version>``. The publish workflows run it on the release tag.

An obi-one line with any other specifier, a marker or a git reference (e.g. a
leftover dev-flow edit) is an error, as is finding no obi-one line at all: nothing
is written in either case.

Stdlib only (no ``obi_one`` import), so it runs without installing the project.
"""

import argparse
import re
import sys
from pathlib import Path

from launch_deps_common import (
    LAUNCH_SCRIPTS_DIR,
    OBI_ONE_LINE_REGEX,
    RELEASE_PIN_REGEX,
    RELEASE_VERSION_REGEX,
)

# Any requirement line naming obi-one, recognised or not: catches lines the strict
# OBI_ONE_LINE_REGEX does not parse (e.g. an inline comment) so they are not
# silently left unpinned.
OBI_ONE_NAME_REGEX = re.compile(r"^\s*obi[-_]one(?![A-Za-z0-9._-])")


class PinError(ValueError):
    """An obi-one requirement line that cannot be pinned."""


def resolve_txt_files(paths: list[str]) -> list[Path]:
    """Resolve CLI ``paths`` to a sorted, de-duplicated list of ``.txt`` files.

    Each entry may be a ``.txt`` file or a directory (searched recursively). With
    no paths, every ``launch_scripts/*/dependencies/*.txt`` file is used. Raises
    SystemExit if a path is neither.
    """
    if not paths:
        return sorted(LAUNCH_SCRIPTS_DIR.glob("*/dependencies/*.txt"))

    found: set[Path] = set()
    for raw in paths:
        path = Path(raw).resolve()
        if path.is_dir():
            found.update(path.glob("**/*.txt"))
        elif path.is_file() and path.suffix == ".txt":
            found.add(path)
        else:
            msg = f"Not a .txt file or directory: {path}"
            raise SystemExit(msg)
    return sorted(found)


def read_text_verbatim(path: Path) -> str:
    """Return the content of ``path`` with its original line endings."""
    # newline="" disables the translation that Path.read_text applies.
    with path.open(encoding="utf-8", newline="") as f:
        return f.read()


def pin_text(text: str, version: str) -> tuple[str, int]:
    """Return ``text`` with its obi-one lines pinned to ``version``, and their count.

    Line endings and all non-obi-one lines are preserved exactly. Raises PinError
    for an obi-one line that is neither bare nor pinned to a release.
    """
    out: list[str] = []
    count = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        if not OBI_ONE_NAME_REGEX.match(body):
            out.append(line)
            continue
        m = OBI_ONE_LINE_REGEX.match(body)
        spec = m.group("spec").rstrip() if m and m.group("spec") else None
        if not m or (spec is not None and not RELEASE_PIN_REGEX.match(spec)):
            msg = (
                "obi-one line is neither bare nor pinned to a release, refusing to pin: "
                f"{body.strip()!r}"
            )
            raise PinError(msg)
        requirement = body[: m.start("spec")] if spec is not None else body
        out.append(f"{requirement.rstrip()}=={version}{ending}")
        count += 1
    return "".join(out), count


def pin_files(files: list[Path], version: str) -> dict[Path, str]:
    """Return the pinned content of each file that has an obi-one line.

    Validates every file before returning, so the caller writes all or nothing.
    Raises SystemExit on an invalid version, an unpinnable line, or when no file
    contains an obi-one line.
    """
    if not RELEASE_VERSION_REGEX.match(version):
        msg = f"Invalid release version {version!r}: expected calver YYYY.M.N (e.g. 2026.9.15)"
        raise SystemExit(msg)

    pinned: dict[Path, str] = {}
    errors: list[str] = []
    for path in files:
        try:
            content, count = pin_text(read_text_verbatim(path), version)
        except PinError as e:
            errors.append(f"{path}: {e}")
            continue
        if count:
            pinned[path] = content
    if errors:
        raise SystemExit("\n".join(errors))
    if not pinned:
        msg = "No obi-one requirement line found in any file; nothing to pin."
        raise SystemExit(msg)
    return pinned


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        required=True,
        help="obi-one release version to pin (calver YYYY.M.N, no prefix)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; fail unless every obi-one line is already pinned to VERSION",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=(
            "Paths to pin: .txt files and/or directories (searched recursively). "
            "Defaults to all launch-script dependencies/*.txt files."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    pinned = pin_files(resolve_txt_files(args.paths), args.version)
    changed = {
        path: content for path, content in pinned.items() if read_text_verbatim(path) != content
    }

    if args.check:
        for path in changed:
            print(f"NOT PINNED to obi-one=={args.version}: {path}", file=sys.stderr)
        return 1 if changed else 0

    for path, content in changed.items():
        # newline="" keeps the original line endings verbatim.
        path.write_text(content, encoding="utf-8", newline="")
        print(f"pinned obi-one=={args.version}: {path}")
    for path in sorted(pinned.keys() - changed.keys()):
        print(f"already pinned: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
