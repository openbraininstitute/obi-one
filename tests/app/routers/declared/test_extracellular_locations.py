import pytest

BLOCK_ROUTE = "/declared/extracellular-locations/block_summary"
DICT_ROUTE = "/declared/extracellular-locations/block_dictionary_summary"

_NEUROPIXELS = {
    "type": "Neuropixels1ExtracellularLocations",
    "origin_x": 3695.0,
    "origin_y": -1089.0,
    "origin_z": -2797.0,
    "direction_x": 0.0,
    "direction_y": 1.0,
    "direction_z": 0.0,
    "n_electrodes": 96,
    "axial_rotation": 30.0,
}
_GRID = {
    "type": "GridExtracellularLocations",
    "direction_y": 1.0,
    "grid_rows": 2,
    "grid_columns": 2,
}


def test_block_summary(client):
    response = client.post(BLOCK_ROUTE, json=_NEUROPIXELS)
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "Neuropixels1ExtracellularLocations"
    assert body["axial_rotation"] == pytest.approx(30.0)
    assert len(body["locations"]) == 96
    assert all(len(position) == 3 for position in body["locations"])


def test_block_dictionary_summary(client):
    response = client.post(DICT_ROUTE, json={"NP": _NEUROPIXELS, "Grid": _GRID})
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"NP", "Grid"}
    assert len(result["NP"]["locations"]) == 96
    assert result["NP"]["type"] == "Neuropixels1ExtracellularLocations"
    assert len(result["Grid"]["locations"]) == 4
    assert result["Grid"]["type"] == "GridExtracellularLocations"


def test_block_summary_rejects_parameter_sweep_list(client):
    # A sweep list is a valid block, but global coordinates need single values -> 422.
    response = client.post(BLOCK_ROUTE, json={**_NEUROPIXELS, "n_electrodes": [8, 16]})
    assert response.status_code == 422


def test_block_summary_rejects_zero_direction(client):
    response = client.post(
        BLOCK_ROUTE,
        json={**_NEUROPIXELS, "direction_x": 0.0, "direction_y": 0.0, "direction_z": 0.0},
    )
    assert response.status_code == 422
