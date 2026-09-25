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
    assert test_module.build_obi_one_constraint(app_version) == []


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
    assert test_module.build_obi_one_constraint(app_version, extras) == expected


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
    assert test_module.build_obi_one_constraint(app_version, ["connectivity"]) == []


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("obi-one\n", []),
        ("obi-one[connectivity]\n", ["connectivity"]),
        ("obi-one[connectivity,emodel]\n", ["connectivity", "emodel"]),
        ("obi-one==2026.9.1\n", []),
        ("obi-one[emodel]==2026.9.1\n", ["emodel"]),
        # Other lines/comments are ignored; obi-one line is found.
        ("# a comment\nobi-one[bluerecording]\nultraliser==2.2.7\n", ["bluerecording"]),
        ("ultraliser==2.2.7\nobi-one\n", []),
        ("obi_one[connectivity]\n", ["connectivity"]),  # underscore variant
        # Dev-flow git reference (README): "@ git+..." must still match & yield extras.
        (
            "obi-one[connectivity] @ git+https://github.com/openbraininstitute/obi-one.git@abc123\n",
            ["connectivity"],
        ),
        ("obi-one@git+https://example.com/obi-one.git\n", []),  # no space, no extras
        # Environment marker.
        ('obi-one[emodel] ; python_version < "3.13"\n', ["emodel"]),
    ],
)
def test_extract_obi_one_extras(tmp_path, content, expected):
    f = tmp_path / "reqs.txt"
    f.write_text(content, encoding="utf-8")
    assert test_module.extract_obi_one_extras(f) == expected


@pytest.mark.parametrize(
    "content",
    [
        "obi-one-extra==1.0\n",  # different package with obi-one prefix
        "obi-onerous==1.0\n",  # prefix without a valid boundary
    ],
)
def test_extract_obi_one_extras_no_false_match(tmp_path, content):
    # A package that merely starts with "obi-one" must not match; with no real
    # obi-one line the extractor raises.
    f = tmp_path / "reqs.txt"
    f.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="No obi-one requirement found"):
        test_module.extract_obi_one_extras(f)


def test_extract_obi_one_extras_missing(tmp_path):
    f = tmp_path / "reqs.txt"
    f.write_text("numpy==2.0\n# no obi-one here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No obi-one requirement found"):
        test_module.extract_obi_one_extras(f)


def test_build_obi_one_constraint_from_file(tmp_path):
    f = tmp_path / "reqs.txt"
    f.write_text("obi-one[connectivity]\n", encoding="utf-8")
    assert test_module.build_obi_one_constraint_from_file("2026.9.1", f) == [
        "obi-one[connectivity]==2026.9.1"
    ]


def test_build_obi_one_constraint_from_file_dev_version(tmp_path):
    f = tmp_path / "reqs.txt"
    f.write_text("obi-one[connectivity]\n", encoding="utf-8")
    assert test_module.build_obi_one_constraint_from_file(None, f) == []


def test_build_obi_one_constraint_from_file_git_ref_dev_flow(tmp_path):
    # Dev flow: a hand-edited git-reference .txt with a dev version must not raise
    # (extras still extracted) and yields no constraint so the git ref installs.
    f = tmp_path / "reqs.txt"
    f.write_text(
        "obi-one[connectivity] @ git+https://github.com/openbraininstitute/obi-one.git@abc123\n",
        encoding="utf-8",
    )
    assert test_module.build_obi_one_constraint_from_file("2026.9.1-3-gabc123-dirty", f) == []
