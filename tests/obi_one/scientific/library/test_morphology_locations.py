"""Tests for morphology location generation."""

import re

import morphio
import pandas as pd
import pytest
from conntility.subcellular import MorphologyPathDistanceCalculator

from obi_one.scientific.library.morphology_locations import path_distance_all_segments_from

from tests.utils import DATA_DIR


@pytest.fixture
def morphology():
    return morphio.Morphology(DATA_DIR / "cell_morphology.swc")


@pytest.fixture
def soma():
    return pd.DataFrame(
        {
            "section_id": [0],
            "segment_id": [0],
            "segment_offset": [0],
        }
    )


def test_path_distance_all_segments_from_matching_section_types(morphology, soma):
    calculator = MorphologyPathDistanceCalculator(morphology)

    result = path_distance_all_segments_from(
        soma,
        morphology,
        calculator,
        lst_sec_types=[3, 4],
    )

    assert not result.empty
    assert set(result["section_type"]).issubset({3, 4})


def test_path_distance_all_segments_from_no_matching_section_types(morphology, soma):
    calculator = MorphologyPathDistanceCalculator(morphology)

    with pytest.raises(
        ValueError,
        match=re.escape("No morphology segments match the selected section types."),
    ):
        path_distance_all_segments_from(
            soma,
            morphology,
            calculator,
            lst_sec_types=[5],
        )
