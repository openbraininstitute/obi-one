import pytest

from obi_one.utils import versions as test_module


@pytest.mark.parametrize(
    ("app_version", "expected"),
    [
        # Clean release -> its release tag.
        ("2026.9.1", "tag:2026.9.1"),
        ("2026.12.26", "tag:2026.12.26"),
        # Post-release / dirty git describe -> the describe suffix is stripped,
        # yielding the last release's tag.
        ("2026.8.12-3-g49a16415-dirty", "tag:2026.8.12"),
        ("2026.9.1-dev3+g1234", "tag:2026.9.1"),
        # Unknown/empty version -> fallback tag.
        (None, "tag:0.0.0"),
        ("", "tag:0.0.0"),
    ],
)
def test_release_tag_ref(app_version, expected):
    assert test_module.release_tag_ref(app_version) == expected
