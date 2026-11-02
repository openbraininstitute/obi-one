"""Test functionality used to map synapse locations to morphologies"""

import neurom
import numpy as np
import pandas as pd

from obi_one.scientific.library.map_em_synapses.map_synapse_locations import (
    add_competing_mesh_distances,
    calc_section_offset,
)

from tests.utils import DATA_DIR

RNG_ = np.random.default_rng()


def test_calc_section_offset_normalizes_within_section():
    morph = neurom.load_morphology(str(DATA_DIR / "cell_morphology.swc"))
    section_length = morph.sections[0].length  # section id 1 (base-1) in the synapse frame

    syns = pd.DataFrame(
        {
            "section_id": [1, 1, 0],  # start of section 1, 10 um into it, and a soma location
            "segment_id": [0, 0, 0],
            "segment_offset": [0.0, 10.0, 5.0],
        }
    )
    result = calc_section_offset(syns, morph)

    # Start of the section -> 0; 10 um in -> 10 / section_length; soma (section_id 0) -> 0.
    np.testing.assert_allclose(result, [0.0, 10.0 / section_length, 0.0], atol=1e-6)


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
