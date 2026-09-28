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


def build_launch_code_deps(
    dependencies: str,
    version: str | None,
    *,
    extras: Sequence[str] | None = None,
) -> LaunchCodeDeps:
    """Return the linked ``dependencies`` + ``dependency_constraints`` for a launch job.

    ``dependencies`` is the repo-relative requirements-file path, stored verbatim so
    the executor can ``uv pip install -r`` it. ``dependency_constraints`` pins
    ``obi-one[extras]`` to ``version`` (empty for a dev build).

    ``extras`` are declared by the caller next to the task, not parsed from the file:
    the service must not depend on the launch-script ``*.txt`` being on disk (they
    are not in the installed ``obi_one`` package). ``tests/launch_scripts/
    test_launch_deps_extras.py`` guards that they stay consistent with the files.
    """
    return {
        "dependencies": dependencies,
        "dependency_constraints": _build_obi_one_constraint(version, extras),
    }


def release_tag(app_version: str | None) -> str:
    """Return the git ``tag:<version>`` checkout ref for a launch job.

    Strips any ``git describe`` suffix (so a post-release/dev build resolves to
    the last release tag) and falls back to ``0.0.0`` when unknown. Deliberately
    more lenient than :func:`_build_obi_one_constraint`, which is empty for a
    non-release build; in a dev/branch workflow the caller overrides ``ref`` with
    an explicit ``commit:<sha>`` at submission time.
    """
    return f"tag:{(app_version or '0.0.0').split('-')[0]}"
