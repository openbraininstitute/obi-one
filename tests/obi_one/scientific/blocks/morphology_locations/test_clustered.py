from unittest.mock import patch

import pandas as pd
import pytest

from obi_one.scientific.blocks.morphology_locations.clustered import (
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
)
from obi_one.scientific.library.morphology_locations import _CEN_IDX

_MODULE = "obi_one.scientific.blocks.morphology_locations.clustered"


@pytest.mark.parametrize(
    ("block_type", "extra", "expected_sources", "drops_center"),
    [
        (ClusteredMorphologyLocations, {}, 1, True),
        (ClusteredGroupedMorphologyLocations, {"n_groups": 2}, 2, True),
        (
            ClusteredPathDistanceMorphologyLocations,
            {"path_dist_mean": 20.0, "path_dist_sd": 5.0, "n_groups_per_cluster": 3},
            3,
            False,
        ),
    ],
)
def test_clustered_placement_rounds_up_then_truncates(
    block_type, extra, expected_sources, drops_center
):
    generated = pd.DataFrame({_CEN_IDX: range(6), "value": range(6)})
    placement = block_type(
        number_of_locations=5,
        n_clusters=2,
        cluster_max_distance=10.0,
        section_types=(3,),
        random_seed=7,
        **extra,
    )

    with patch(f"{_MODULE}.generate_neurite_locations_on", return_value=generated) as generate:
        result = placement.points_on(object())

    assert len(result) == 5
    assert (_CEN_IDX not in result) is drops_center
    assert generate.call_args.kwargs["n_centers"] == 2
    assert generate.call_args.kwargs["n_per_center"] == 3
    assert generate.call_args.kwargs["srcs_per_center"] == expected_sources
