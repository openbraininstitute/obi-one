"""Version helpers for launch-system jobs.

Launch jobs check out the ``launch-<version>`` tag of the obi-one repository: the
release ``<version>`` plus its launch-script requirements with obi-one pinned to
``==<version>`` (created by ``.github/workflows/launch-tag.yml``). The tag thus
selects the task code, the obi-one wheel and the frozen transitive closure at once.
"""

import re
from typing import Annotated

from pydantic import StringConstraints

# A clean obi-one release version (calver ``YYYY.M.N``, no prefix or suffix): the
# only versions that have a ``launch-<version>`` tag. Mirrors the pattern in
# launch_scripts/tools/launch_deps_common.py (which must not import obi_one).
RELEASE_VERSION_REGEX = re.compile(r"^\d{4}\.\d{1,2}\.\d+$")
ReleaseVersion = Annotated[str, StringConstraints(pattern=RELEASE_VERSION_REGEX.pattern)]


def launch_ref(app_version: str | None) -> str:
    """Return the git ``tag:launch-<version>`` checkout ref for a launch job.

    Strips any ``git describe`` suffix, so a post-release/dev build (e.g.
    ``2026.8.12-3-g49a1641-dirty``) resolves to the last release, and falls back to
    ``0.0.0`` when unknown. In a dev/branch workflow the caller overrides ``ref``
    with an explicit ``commit:<sha>`` at submission time.
    """
    return f"tag:launch-{(app_version or '0.0.0').split('-')[0]}"
