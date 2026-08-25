"""Test functionality used to map synapse locations to morphologies"""

import numpy as np
import pandas as pd

from obi_one.scientific.library.map_em_synapses.map_synapse_locations import (
    add_competing_mesh_distances,
)

RNG_ = np.random.default_rng()


def test_competing_distances_no_solution():
    mesh_pt_df = pd.DataFrame(
        [[0.0, 0.0, 0.0, 0], [0.0, 1.0, 0.0, 0], [0.0, 2.0, 0.0, 0]],
        columns=["x", "y", "z", "spine_sharing_id"],
    )
    pts = pd.DataFrame(RNG_.random(size=(10, 3)), columns=["x", "y", "z"])
    # Must be all -1 because all spine_sharing_ids are the same
    competitors = add_competing_mesh_distances(mesh_pt_df, pts)
    assert (competitors == -1).all()


def test_competing_distances_good_solution():
    mesh_pt_df = pd.DataFrame(
        [[0.0, 0.0, 0.0, 1], [0.0, 1.0, 0.0, 2], [0.0, 2.0, 0.0, 3]],
        columns=["x", "y", "z", "spine_sharing_id"],
    )
    pts = pd.DataFrame(RNG_.random(size=(10, 3)), columns=["x", "y", "z"])
    # Must be all -1 because all spine_sharing_ids are the same
    competitors = add_competing_mesh_distances(mesh_pt_df, pts)
    assert not (competitors == -1).any()
