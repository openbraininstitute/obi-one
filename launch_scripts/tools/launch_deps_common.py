"""Shared definitions for the launch-script dependency tools (stdlib only).

Imported as a sibling top-level module by ``launch_deps_compile.py`` and
``launch_deps_pin.py``; it must not import ``obi_one`` so that the pin tool runs
with a bare Python interpreter (see ``.github/workflows/launch-tag.yml``).
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCH_SCRIPTS_DIR = REPO_ROOT / "launch_scripts"

# Matches a top-level ``obi-one`` / ``obi_one`` requirement line, capturing extras
# and whatever follows the name. ``@`` accepts the dev-flow git reference in a
# hand-edited ``.txt`` (see docs/internal/launch-script-dependencies.md).
OBI_ONE_LINE_REGEX = re.compile(
    r"^\s*(?P<name>obi[-_]one)"  # package name (obi-one / obi_one)
    r"(?:\[(?P<extras>[A-Za-z0-9._,\s-]+)\])?"  # optional extras group
    r"\s*(?P<spec>[<>=!~;@].*)?$"  # optional version specifier / marker / @ url
)

# A clean obi-one release version: calver ``YYYY.M.N`` with nothing else, matching
# the setuptools_scm ``tag_regex`` in pyproject.toml (without the ``v`` prefix,
# which obi-one releases do not use).
RELEASE_VERSION_REGEX = re.compile(r"^\d{4}\.\d{1,2}\.\d+$")
