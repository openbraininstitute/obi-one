"""Version helpers for launch-system jobs: checkout ref and dependency constraint.

A launch job derives two things from the service version (``settings.APP_VERSION``,
itself produced by ``git describe``):

- the git **checkout ref** (``tag:<version>``) that selects which obi-one
  *source* the executor checks out, and
- the obi-one **dependency constraint** (``obi-one[extras]==<version>``) that
  selects which published obi-one *wheel* uv installs.

These answer different questions and are intentionally *not* interchangeable
(see :func:`release_tag` vs :func:`build_obi_one_constraint`). They coincide
only for a clean release tag; for any post-release/dev build they diverge by
design, so the two derivations are kept here, side by side, in one place.

The launch-scripts' frozen requirements files leave ``obi-one`` itself unpinned
(they only pin the transitive dependency closure). The exact ``obi-one`` version
to install is only known at task-submission time -- it must match the version of
the service submitting the job, which is not necessarily the latest published
release (staging and production deploy at different times while new versions may
be released in between). The dynamic constraint is passed alongside the job; the
launch-system wrapper applies it via ``uv pip install --constraint``, so it takes
priority over the (unpinned) matching entry in the requirements file while the
resolver still runs normally.
"""

import re
from collections.abc import Sequence
from pathlib import Path

# Matches a top-level ``obi-one`` requirement line with optional extras, e.g.
# ``obi-one`` or ``obi-one[connectivity,emodel]`` (optionally followed by a
# version specifier, an environment marker, or an ``@ git+...`` direct reference,
# all ignored here). ``@`` supports the dev-flow git reference in a hand-edited
# ``.txt`` (see README). Shared with launch_scripts/compile_launch_deps.py.
OBI_ONE_LINE_REGEX = re.compile(
    r"^\s*obi[-_]one"  # package name (obi-one / obi_one)
    r"(?:\[(?P<extras>[A-Za-z0-9._,\s-]+)\])?"  # optional extras group
    r"\s*(?:[<>=!~;@].*)?$"  # optional version specifier / marker / @ url
)


# Matches a clean release version: calver ``YYYY.M.D`` with an optional ``v``
# prefix, and nothing else. This mirrors the setuptools_scm ``tag_regex`` in
# pyproject.toml. Any ``git describe`` suffix (e.g. ``-3-g49a1641``, ``-dirty``)
# or scm dev suffix (e.g. ``.dev3``, ``+local``) means the build is *after* a
# release and does not correspond to a published wheel, so it is treated as dev.
_RELEASE_VERSION_REGEX = re.compile(r"^v?(?P<version>\d{4}\.\d{1,2}\.\d+)$")


def release_tag(app_version: str | None) -> str:
    """Return the git ``tag:<version>`` checkout ref for a launch job.

    This selects which obi-one *source* the launch-system executor checks out.
    It is deliberately more lenient than :func:`build_obi_one_constraint`: it
    strips any ``git describe`` suffix (``-N-g<sha>[-dirty]``) and always yields
    a tag-shaped string, because for a released service the code lives at that
    tag, and falls back to ``0.0.0`` when the version is unknown.

    It answers a *different* question than the dependency constraint and the two
    are not interchangeable:

    - ``ref`` selects obi-one *source* from git. It can point at a tag that
      exists even for a post-release/dev build (``git describe`` resolves it to
      the most recent tag). In a dev/branch workflow the caller overrides it with
      an explicit ``commit:<sha>`` at submission time, since the derived tag would
      be the last release, not the branch under test.
    - the constraint (:func:`build_obi_one_constraint`) selects which published
      obi-one *wheel* to install, and is empty for any non-release build because
      no matching wheel exists.

    So for a dev build ``release_tag`` still yields a (last-release) tag while the
    constraint is empty -- the divergence is intentional.
    """
    return f"tag:{(app_version or '0.0.0').split('-')[0]}"


def _normalize_version(app_version: str | None) -> str | None:
    """Return the release version to pin, or None if it is unknown/dev.

    Only a *clean* release version (an exact calver tag such as ``2026.8.12``)
    is pinned. A missing/empty version, or any post-release / dirty build (e.g.
    ``2026.8.12-3-g49a1641-dirty``), returns None: there is no matching published
    obi-one wheel to constrain to, so no constraint is sent. This also lets local
    dev builds install obi-one from a git reference in the requirements file
    without a conflicting version constraint.
    """
    if not app_version:
        return None
    m = _RELEASE_VERSION_REGEX.match(app_version.strip())
    if not m:
        return None
    return m.group("version")


def _format_extras(extras: Sequence[str] | None) -> str:
    """Format an optional list of extras as ``[a,b]`` or ``""``."""
    if not extras:
        return ""
    return "[" + ",".join(extras) + "]"


def build_obi_one_constraint(
    app_version: str | None,
    extras: Sequence[str] | None = None,
) -> list[str]:
    """Build the dynamic dependency constraint pinning ``obi-one``.

    Args:
        app_version: The submitting service version (e.g. ``settings.APP_VERSION``).
        extras: Optional obi-one extras to include in the constraint (e.g.
            ``["connectivity"]``). The extras must match the ones used by the
            corresponding requirements file so the constraint resolves the same
            optional dependencies.

    Returns:
        A single-element list ``["obi-one[extras]==<version>"]`` when the version
        is a known release, otherwise an empty list (no constraint applied).
    """
    version = _normalize_version(app_version)
    if version is None:
        return []
    return [f"obi-one{_format_extras(extras)}=={version}"]


def extract_obi_one_extras(requirements_file: Path | str) -> list[str]:
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


def build_obi_one_constraint_from_file(
    app_version: str | None,
    requirements_file: Path | str,
) -> list[str]:
    """Build the obi-one constraint using extras read from a requirements file.

    Convenience wrapper combining :func:`extract_obi_one_extras` and
    :func:`build_obi_one_constraint`, keeping the extras in sync with the
    requirements file (the single source of truth) rather than duplicating them.
    """
    extras = extract_obi_one_extras(requirements_file)
    return build_obi_one_constraint(app_version, extras)
