import pytest

from obi_one.utils import versions as test_module


@pytest.mark.parametrize(
    ("app_version", "expected"),
    [
        # Clean release tag -> tag:<version>.
        ("2026.9.1", "tag:2026.9.1"),
        ("2026.12.26", "tag:2026.12.26"),
        # Post-release / dirty git describe -> the describe suffix is stripped,
        # yielding the last-release tag (ref still resolves in git). The matching
        # constraint is empty for the same input (see divergence test below).
        ("2026.8.12-3-g49a16415-dirty", "tag:2026.8.12"),
        ("2026.9.1-dev3+g1234", "tag:2026.9.1"),
        # Unknown/empty version -> fallback tag.
        (None, "tag:0.0.0"),
        ("", "tag:0.0.0"),
    ],
)
def test_release_tag(app_version, expected):
    assert test_module.release_tag(app_version) == expected


@pytest.mark.parametrize(
    "app_version",
    [
        "2026.8.12-3-g49a16415-dirty",
        "2026.9.1-dev3+g1234",
    ],
)
def test_release_tag_and_constraint_diverge_for_dev_builds(app_version):
    # For a dev build the two derivations intentionally diverge: the checkout ref
    # still points at the last release tag, while no constraint is emitted because
    # there is no matching published wheel.
    assert test_module.release_tag(app_version).startswith("tag:")
    assert test_module._build_obi_one_constraint(app_version) == []


@pytest.mark.parametrize(
    ("app_version", "extras", "expected"),
    [
        ("2026.9.1", None, ["obi-one==2026.9.1"]),
        ("2026.9.1", [], ["obi-one==2026.9.1"]),
        ("2026.9.1", ["connectivity"], ["obi-one[connectivity]==2026.9.1"]),
        (
            "2026.9.1",
            ["connectivity", "emodel"],
            ["obi-one[connectivity,emodel]==2026.9.1"],
        ),
        # Two-digit month/day and optional ``v`` prefix are accepted; ``v`` is
        # stripped to match the published package version.
        ("2026.12.26", None, ["obi-one==2026.12.26"]),
        ("v2026.9.1", ["emodel"], ["obi-one[emodel]==2026.9.1"]),
    ],
)
def test_build_obi_one_constraint(app_version, extras, expected):
    assert test_module._build_obi_one_constraint(app_version, extras) == expected


@pytest.mark.parametrize(
    "app_version",
    [
        None,
        "",
        "0.0.0",
        # git describe post-release / dirty builds: not a published release.
        "2026.8.12-3-g49a16415-dirty",
        "2026.9.1-dev3+g1234",
        "2026.9.1.dev3",
        # not calver -> not an obi-one release tag.
        "1.2.3",
    ],
)
def test_build_obi_one_constraint_unknown_version(app_version):
    assert test_module._build_obi_one_constraint(app_version, ["connectivity"]) == []


def test_non_release_version_logs_warning(caplog):
    with caplog.at_level("WARNING"):
        assert test_module._build_obi_one_constraint("2026.8.12-3-gabc-dirty") == []
    assert "not a release tag" in caplog.text


@pytest.mark.parametrize("app_version", [None, ""])
def test_empty_version_does_not_log(caplog, app_version):
    # The normal "no version" path (dev/local) must not emit a warning.
    with caplog.at_level("WARNING"):
        assert test_module._build_obi_one_constraint(app_version) == []
    assert not caplog.text


def test_build_launch_code_deps_links_both_fields():
    result = test_module.build_launch_code_deps(
        "path/to/reqs.txt", "2026.9.1", extras=["connectivity"]
    )
    assert result["dependencies"] == "path/to/reqs.txt"
    assert result["dependency_constraints"] == ["obi-one[connectivity]==2026.9.1"]


def test_build_launch_code_deps_no_extras():
    result = test_module.build_launch_code_deps("path/to/reqs.txt", "2026.9.1")
    assert result["dependencies"] == "path/to/reqs.txt"
    assert result["dependency_constraints"] == ["obi-one==2026.9.1"]


def test_build_launch_code_deps_empty_constraint_for_dev_version():
    result = test_module.build_launch_code_deps("path/to/reqs.txt", None, extras=["connectivity"])
    assert result["dependencies"] == "path/to/reqs.txt"
    assert result["dependency_constraints"] == []
