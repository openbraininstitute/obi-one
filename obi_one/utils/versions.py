"""Version helpers for launch-system jobs.

Launch jobs check out the release tag of the obi-one repository. At each release,
``.github/workflows/release-pin.yml`` moves the tag to a commit whose launch-script
requirements pin obi-one to ``==<version>``, so the tag selects the task code, the
obi-one wheel and the frozen transitive closure at once.
"""


def release_tag_ref(app_version: str | None) -> str:
    """Return the git ``tag:<version>`` checkout ref for a launch job.

    Strips any ``git describe`` suffix, so a post-release/dev build (e.g.
    ``2026.8.12-3-g49a1641-dirty``) resolves to the last release, and falls back to
    ``0.0.0`` when unknown. In a dev/branch workflow the caller overrides ``ref``
    with an explicit ``commit:<sha>`` at submission time.
    """
    return f"tag:{(app_version or '0.0.0').split('-')[0]}"
