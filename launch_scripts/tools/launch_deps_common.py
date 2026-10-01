"""Shared definitions for the launch-script dependency tools (stdlib only).

Imported as a sibling top-level module by ``launch_deps_compile.py`` and
``launch_deps_pin.py``; it must not import ``obi_one`` so that the pin tool runs
with a bare Python interpreter (see ``.github/workflows/release-pin.yml``).
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

# Marks a requirement whose version comes from the task's runtime image and is not
# published on an index (e.g. a NEURON dev build baked into the neurodamus image).
# Such a line is kept out of resolution and written verbatim into the compiled
# ``.txt``. Syntax: ``<requirement>  # image-local``.
IMAGE_LOCAL_COMMENT = "# image-local"
IMAGE_LOCAL_LINE_REGEX = re.compile(
    rf"^(?P<requirement>[A-Za-z0-9][^#]*?)\s*{re.escape(IMAGE_LOCAL_COMMENT)}$"
)

# A clean obi-one release version: calver ``YYYY.M.N`` with nothing else, matching
# the setuptools_scm ``tag_regex`` in pyproject.toml (without the ``v`` prefix,
# which obi-one releases do not use).
RELEASE_VERSION_PATTERN = r"\d{4}\.\d{1,2}\.\d+"
RELEASE_VERSION_REGEX = re.compile(rf"^{RELEASE_VERSION_PATTERN}$")

# The ``spec`` of an obi-one line pinned to a release by ``launch_deps_pin.py``.
RELEASE_PIN_REGEX = re.compile(rf"^==(?P<version>{RELEASE_VERSION_PATTERN})$")
