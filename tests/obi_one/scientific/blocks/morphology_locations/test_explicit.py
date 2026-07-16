import morphio
import numpy as np
import pandas as pd
import pytest
from obi_one.scientific.unions.unions_morphology_locations import MorphologyLocationUnion
from pydantic import TypeAdapter, ValidationError

from obi_one.scientific.blocks.morphology_locations.explicit import (
    ExplicitMorphologyLocations,
    MorphologyLocationPoint,
)
from obi_one.scientific.blocks.morphology_locations.random import RandomMorphologyLocations
from obi_one.scientific.library.morphology_locations import MorphologyPathDistanceCalculator

from tests.utils import DATA_DIR

_EXPECTED_COLUMNS = [
    "segment_id",
    "section_id",
    "section_type",
    "segment_offset",
    "path_distance",
    "source_index",
    "normalized_section_offset",
]


@pytest.fixture
def morphology():
    return morphio.Morphology(
        DATA_DIR / "cell_morphology.swc",
        options=morphio.Option.nrn_order,
    )


def test_single_explicit_location_returns_expected_neurite_point(morphology):
    offset = 0.25
    section_id = 1
    locations = ExplicitMorphologyLocations(
        locations=(MorphologyLocationPoint(section_id=section_id, offset=offset),)
    )
    dataframe = locations.points_on(morphology)

    section = morphology.section(section_id - 1)
    segment_lengths = np.linalg.norm(np.diff(section.points, axis=0), axis=1)
    expected_distance = offset * segment_lengths.sum()
    expected_segment_id = int(
        np.searchsorted(np.cumsum(segment_lengths), expected_distance, side="right")
    )
    expected_segment_start = segment_lengths[:expected_segment_id].sum()

    assert dataframe.columns.tolist() == _EXPECTED_COLUMNS
    assert len(dataframe) == 1
    assert section.id == 0
    assert dataframe.loc[0, "section_id"] == section_id
    assert dataframe.loc[0, "section_type"] == int(section.type)
    assert dataframe.loc[0, "segment_id"] == expected_segment_id
    assert dataframe.loc[0, "segment_offset"] == pytest.approx(
        expected_distance - expected_segment_start
    )
    assert dataframe.loc[0, "source_index"] == 0
    assert dataframe.loc[0, "normalized_section_offset"] == offset


def test_explicit_location_path_distance_matches_calculator(morphology):
    locations = ExplicitMorphologyLocations(
        locations=(MorphologyLocationPoint(section_id=6, offset=0.75),)
    )

    dataframe = locations.points_on(morphology)
    soma = pd.DataFrame({"section_id": [0], "segment_id": [0], "segment_offset": [0.0]})
    expected = MorphologyPathDistanceCalculator(morphology).path_distances(
        soma,
        dataframe,
        str_section_id="section_id",
        str_segment_id="segment_id",
        str_offset="segment_offset",
    )[0, 0]

    assert dataframe.loc[0, "path_distance"] == pytest.approx(expected)


def test_single_explicit_location_returns_expected_soma_point(morphology):
    offset = 0.75

    locations = ExplicitMorphologyLocations(
        locations=(MorphologyLocationPoint(section_id=0, offset=offset),)
    )
    dataframe = locations.points_on(morphology)

    assert dataframe.to_dict(orient="records") == [
        {
            "segment_id": 0,
            "section_id": 0,
            "section_type": int(morphio.SectionType.soma),
            "segment_offset": 0.0,
            "path_distance": 0.0,
            "source_index": 0,
            "normalized_section_offset": offset,
        }
    ]


def test_explicit_morphology_locations_returns_expected_rows(morphology):
    locations = ExplicitMorphologyLocations(
        locations=(
            MorphologyLocationPoint(section_id=0, offset=0.0),
            MorphologyLocationPoint(section_id=2, offset=1.0),
        )
    )

    dataframe = locations.points_on(morphology)

    assert dataframe.columns.tolist() == _EXPECTED_COLUMNS
    assert dataframe["section_id"].tolist() == [0, 2]
    assert dataframe["normalized_section_offset"].tolist() == [0.0, 1.0]
    assert dataframe.loc[1, "section_type"] == int(morphology.section(1).type)


def test_explicit_locations_reconstruct_random_locations(morphology):
    random_locations = RandomMorphologyLocations(
        random_seed=17,
        number_of_locations=20,
    ).points_on(morphology)
    explicit_locations = ExplicitMorphologyLocations(
        locations=[
            {
                "section_id": int(row.section_id),
                "offset": float(row.normalized_section_offset),
            }
            for row in random_locations.itertuples()
        ]
    ).points_on(morphology)

    pd.testing.assert_frame_equal(
        explicit_locations,
        random_locations,
        check_exact=False,
        atol=1e-4,
        rtol=1e-7,
    )


def test_segment_offset_is_absolute_distance(morphology):
    locations = ExplicitMorphologyLocations(
        locations=(MorphologyLocationPoint(section_id=6, offset=0.75),)
    )
    dataframe = locations.points_on(morphology)

    assert dataframe.loc[0, "segment_offset"] > 1.0
    assert dataframe.loc[0, "normalized_section_offset"] == pytest.approx(0.75)


@pytest.mark.parametrize("offset", [-0.01, 1.01])
def test_invalid_offset_is_rejected(offset):
    with pytest.raises(ValidationError, match="offset"):
        ExplicitMorphologyLocations(locations=({"section_id": 1, "offset": offset},))


@pytest.mark.parametrize("section_id", [-1, 1.5])
def test_invalid_section_id_is_rejected(section_id):
    with pytest.raises(ValidationError, match="section_id"):
        ExplicitMorphologyLocations(locations=({"section_id": section_id, "offset": 0.5},))


def test_empty_explicit_locations_are_rejected():
    with pytest.raises(ValidationError, match="locations"):
        ExplicitMorphologyLocations(locations=())


def test_explicit_locations_use_compact_point_models():
    locations = ExplicitMorphologyLocations(locations=({"section_id": 1, "offset": 0.5},))

    point_dump = locations.model_dump()["locations"][0]

    assert point_dump == {
        "section_id": 1,
        "offset": 0.5,
    }
    assert "random_seed" not in point_dump
    assert "number_of_locations" not in point_dump
    assert "section_types" not in point_dump


def test_explicit_locations_accept_viewer_style_list_payload():
    locations = ExplicitMorphologyLocations(
        locations=[
            {"section_id": 1, "offset": 0.5},
            {"section_id": 2, "offset": 0.25},
        ]
    )

    assert isinstance(locations.locations, tuple)
    assert locations.model_dump(mode="json")["locations"] == [
        {"section_id": 1, "offset": 0.5},
        {"section_id": 2, "offset": 0.25},
    ]


def test_missing_section_id_raises_clear_error(morphology):
    missing_section_id = len(morphology.sections) + 1
    locations = ExplicitMorphologyLocations(
        locations=(MorphologyLocationPoint(section_id=missing_section_id, offset=0.5),)
    )

    with pytest.raises(
        ValueError,
        match=f"Section ID {missing_section_id} does not exist in the provided morphology",
    ):
        locations.points_on(morphology)


def test_morphology_location_union_round_trip():
    original = ExplicitMorphologyLocations(
        locations=(MorphologyLocationPoint(section_id=1, offset=0.5),)
    )

    restored = TypeAdapter(MorphologyLocationUnion).validate_python(original.model_dump())

    assert isinstance(restored, ExplicitMorphologyLocations)
    assert restored == original
