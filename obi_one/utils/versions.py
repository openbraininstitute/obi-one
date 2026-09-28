"""Version helpers for launch-system jobs: checkout ref and dependency constraint.

From the service version a launch job derives the git **checkout ref**
(``tag:<version>``, which obi-one *source* to check out) and the obi-one
**dependency constraint** (``obi-one[extras]==<version>``, which published
*wheel* to install). These answer different questions and coincide only for a
clean release tag -- see :func:`release_tag` vs :func:`_build_obi_one_constraint`.
"""

import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

L = logging.getLogger(__name__)

# Matches a top-level ``obi-one`` / ``obi_one`` requirement line, capturing extras.
# ``@`` accepts the dev-flow git reference in a hand-edited ``.txt`` (see README).
# Shared with launch_scripts/compile_launch_deps.py.
OBI_ONE_LINE_REGEX = re.compile(
    r"^\s*obi[-_]one"  # package name (obi-one / obi_one)
    r"(?:\[(?P<extras>[A-Za-z0-9._,\s-]+)\])?"  # optional extras group
    r"\s*(?:[<>=!~;@].*)?$"  # optional version specifier / marker / @ url
)


# A clean release version: calver ``YYYY.M.D`` with an optional ``v`` prefix and
# nothing else, mirroring the setuptools_scm ``tag_regex`` in pyproject.toml. Any
# ``git describe`` / scm dev suffix means a post-release build (treated as dev).
_RELEASE_VERSION_REGEX = re.compile(r"^v?(?P<version>\d{4}\.\d{1,2}\.\d+)$")

# ``obi_one/utils/versions.py`` -> parents[2] is the project root; used to resolve
# the repo-relative ``dependencies`` path when reading extras.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class LaunchCodeDeps(TypedDict):
    """Linked launch-job code fields: ``dependencies`` and its obi-one constraint."""

    dependencies: str
    dependency_constraints: list[str]


def _normalize_version(app_version: str | None) -> str | None:
    """Return the release version to pin, or None if it is unknown/dev.

    Only a clean calver tag (e.g. ``2026.8.12``) is pinned. A missing/empty or
    post-release/dirty version (e.g. ``2026.8.12-3-g49a1641-dirty``) returns None:
    no matching published wheel exists, so no constraint is sent.
    """
    if not app_version:
        return None
    m = _RELEASE_VERSION_REGEX.match(app_version.strip())
    if not m:
        L.warning(
            "obi-one version %r is not a release tag; no version constraint applied.", app_version
        )
        return None
    return m.group("version")


def _build_obi_one_constraint(
    app_version: str | None,
    extras: Sequence[str] | None = None,
) -> list[str]:
    """Build the dynamic dependency constraint pinning ``obi-one``.

    Args:
        app_version: The submitting service version (e.g. ``settings.APP_VERSION``).
        extras: obi-one extras to include; must match the requirements file so the
            constraint resolves the same optional dependencies.

    Returns:
        ``["obi-one[extras]==<version>"]`` for a release version, else ``[]``.
    """
    version = _normalize_version(app_version)
    if version is None:
        return []
    extras_suffix = f"[{','.join(extras)}]" if extras else ""
    return [f"obi-one{extras_suffix}=={version}"]


def _extract_obi_one_extras(requirements_file: Path | str) -> list[str]:
    """Extract the obi-one extras declared in a requirements file.

    Scans the file for the ``obi-one`` requirement line and returns its extras
    (e.g. ``["connectivity"]`` for ``obi-one[connectivity]``). Returns an empty
    list if obi-one is listed without extras. Raises ValueError if no obi-one
    line is found (every launch-script requirements file must reference obi-one).
    """
    path = Path(requirements_file)
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = OBI_ONE_LINE_REGEX.match(line)
        if m:
            extras = m.group("extras")
            if not extras:
                return []
            return [e.strip() for e in extras.split(",") if e.strip()]
    msg = f"No obi-one requirement found in {path}"
    raise ValueError(msg)


def _build_obi_one_constraint_from_file(
    app_version: str | None,
    requirements_file: Path | str,
) -> list[str]:
    """Build the obi-one constraint using extras read from a requirements file.

    Convenience wrapper combining :func:`_extract_obi_one_extras` and
    :func:`_build_obi_one_constraint`, keeping the extras in sync with the
    requirements file (the single source of truth) rather than duplicating them.
    """
    extras = _extract_obi_one_extras(requirements_file)
    return _build_obi_one_constraint(app_version, extras)


def build_launch_code_deps(dependencies: str, version: str | None) -> LaunchCodeDeps:
    """Return the linked ``dependencies`` + ``dependency_constraints`` for a launch job.

    Both are derived from the same requirements file, so a job cannot declare
    ``dependencies`` without the matching obi-one constraint (or let the two
    drift). ``dependencies`` is the repo-relative path stored in the job;
    ``version`` is the obi-one version to pin (empty constraint if unreleased).

    Spread the result into a ``PythonRepositoryCode(...)`` or the job ``code`` dict.
    """
    constraint = _build_obi_one_constraint_from_file(version, _REPO_ROOT / dependencies)
    return {"dependencies": dependencies, "dependency_constraints": constraint}


def release_tag(app_version: str | None) -> str:
    """Return the git ``tag:<version>`` checkout ref for a launch job.

    Strips any ``git describe`` suffix (so a post-release/dev build resolves to
    the last release tag) and falls back to ``0.0.0`` when unknown. Deliberately
    more lenient than :func:`_build_obi_one_constraint`, which is empty for a
    non-release build; in a dev/branch workflow the caller overrides ``ref`` with
    an explicit ``commit:<sha>`` at submission time.
    """
    return f"tag:{(app_version or '0.0.0').split('-')[0]}"
