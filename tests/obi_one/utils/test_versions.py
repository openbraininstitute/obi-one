import pytest

from obi_one.utils import versions as test_module


@pytest.mark.parametrize(
    ("app_version", "expected"),
    [
        # Clean release -> its launch tag.
        ("2026.9.1", "tag:launch-2026.9.1"),
        ("2026.12.26", "tag:launch-2026.12.26"),
        # Post-release / dirty git describe -> the describe suffix is stripped,
        # yielding the last release's launch tag.
        ("2026.8.12-3-g49a16415-dirty", "tag:launch-2026.8.12"),
        ("2026.9.1-dev3+g1234", "tag:launch-2026.9.1"),
        # Unknown/empty version -> fallback tag.
        (None, "tag:launch-0.0.0"),
        ("", "tag:launch-0.0.0"),
    ],
)
def test_launch_ref(app_version, expected):
    assert test_module.launch_ref(app_version) == expected
