import pytest
from pydantic import TypeAdapter, ValidationError

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


@pytest.mark.parametrize("version", ["2026.9.15", "2026.12.1"])
def test_release_version_regex_accepts_releases(version):
    assert test_module.RELEASE_VERSION_REGEX.match(version)


@pytest.mark.parametrize("version", ["v2026.9.1", "2026.9.1-3-gabc", "2026.9", "", "0.0.0"])
def test_release_version_regex_rejects_non_releases(version):
    assert not test_module.RELEASE_VERSION_REGEX.match(version)


class TestReleaseVersion:
    adapter = TypeAdapter(test_module.ReleaseVersion)

    @pytest.mark.parametrize("version", ["2026.9.15", "2026.12.1"])
    def test_accepts_releases(self, version):
        assert self.adapter.validate_python(version) == version

    @pytest.mark.parametrize(
        "version", ["v2026.9.1", "2026.9.1-3-gabc", "2026.9", "launch-2026.9.1", ""]
    )
    def test_rejects_non_releases(self, version):
        with pytest.raises(ValidationError, match="should match pattern"):
            self.adapter.validate_python(version)
