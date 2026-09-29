#!/usr/bin/env python3
"""Pin obi-one to a release version in the launch-script requirements.

Rewrites every bare ``obi-one[extras]`` line of the compiled
``launch_scripts/*/dependencies/*.txt`` files to ``obi-one[extras]==<version>``,
leaving every other byte untouched. Run by ``.github/workflows/launch-tag.yml`` on
a checkout of release ``<version>`` to build the ``launch-<version>`` tag that
launch jobs check out. The transitive closure in those files was already compiled
against that release's source, so pinning the obi-one line alone is consistent.

Any obi-one line that is already pinned, has a marker or a git reference (e.g. a
leftover dev-flow edit) is an error, as is finding no obi-one line at all: nothing
is written in either case.

Stdlib only (no ``obi_one`` import), so it runs without installing the project.
"""

import argparse
import re
import sys
from pathlib import Path

from launch_deps_common import LAUNCH_SCRIPTS_DIR, OBI_ONE_LINE_REGEX, RELEASE_VERSION_REGEX

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


def pin_text(text: str, version: str) -> tuple[str, int]:
    """Return ``text`` with bare obi-one lines pinned to ``version``, and their count.

    Line endings and all non-obi-one lines are preserved exactly. Raises PinError
    for an obi-one line that is not bare (specifier, marker, ``@`` reference or
    otherwise unparsable).
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
        if not m or m.group("spec"):
            msg = f"obi-one line is not a bare requirement, refusing to pin: {body.strip()!r}"
            raise PinError(msg)
        out.append(f"{body.rstrip()}=={version}{ending}")
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
        # newline="" keeps the original line endings (read_text translates them).
        with path.open(encoding="utf-8", newline="") as f:
            text = f.read()
        try:
            content, count = pin_text(text, version)
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
    for path, content in pinned.items():
        # newline="" keeps the original line endings verbatim.
        path.write_text(content, encoding="utf-8", newline="")
        print(f"pinned obi-one=={args.version}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
