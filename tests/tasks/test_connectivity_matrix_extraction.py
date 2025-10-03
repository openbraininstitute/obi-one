import re

import numpy as np
import pytest
from conntility import ConnectivityMatrix

import obi_one as obi

from tests.utils import CIRCUIT_DIR, MATRIX_DIR


def test_connectivity_matrix_extraction(tmp_path):
    # (a) Matrix extraction with invalid edge population --> Error
    circuit_list = [
        obi.Circuit(
            name="N_10__top_nodes_dim6",
            path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
        ),
        obi.Circuit(
            name="N_10__top_rc_nodes_dim2_rc",
            path=str(CIRCUIT_DIR / "N_10__top_rc_nodes_dim2_rc" / "circuit_config.json"),
        ),
    ]
    extraction_init = obi.ConnectivityMatrixExtractionScanConfig.Initialize(
        circuit=circuit_list,
        edge_population="INVALID__S1nonbarrel_neurons__S1nonbarrel_neurons__chemical",
        node_attributes=("synapse_class", "layer", "mtype", "etype", "x", "y", "z"),
    )
    connectivity_matrix_extractions_form = obi.ConnectivityMatrixExtractionScanConfig(
        initialize=extraction_init
    )
    grid_scan = obi.GridScanGenerationTask(
        form=connectivity_matrix_extractions_form,
        output_root=tmp_path / "grid_scan_a",
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()

    with pytest.raises(
        ValueError,
        match=f"Edge population '{extraction_init.edge_population}' not found in circuit!",
    ):
        obi.run_tasks_for_generated_scan(grid_scan)

    # (b) Matrix extraction with invalid node attribute --> Error
    circuit_list = [
        obi.Circuit(
            name="N_10__top_nodes_dim6",
            path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
        ),
        obi.Circuit(
            name="N_10__top_rc_nodes_dim2_rc",
            path=str(CIRCUIT_DIR / "N_10__top_rc_nodes_dim2_rc" / "circuit_config.json"),
        ),
    ]
    extraction_init = obi.ConnectivityMatrixExtractionScanConfig.Initialize(
        circuit=circuit_list,
        edge_population="S1nonbarrel_neurons__S1nonbarrel_neurons__chemical",
        node_attributes=("synapse_class", "layer", "mtype", "etype", "x", "y", "z", "INVALID"),
    )
    connectivity_matrix_extractions_form = obi.ConnectivityMatrixExtractionScanConfig(
        initialize=extraction_init
    )
    grid_scan = obi.GridScanGenerationTask(
        form=connectivity_matrix_extractions_form,
        output_root=tmp_path / "grid_scan_b",
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()

    with pytest.raises(ValueError, match=re.escape("Unknown properties: ['INVALID']")):
        obi.run_tasks_for_generated_scan(grid_scan)

    # (c) Matrix extraction from two circuits through grid scan
    circuit_list = [
        obi.Circuit(
            name="N_10__top_nodes_dim6",
            path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
        ),
        obi.Circuit(
            name="N_10__top_rc_nodes_dim2_rc",
            path=str(CIRCUIT_DIR / "N_10__top_rc_nodes_dim2_rc" / "circuit_config.json"),
        ),
    ]

    extraction_init = obi.ConnectivityMatrixExtractionScanConfig.Initialize(
        circuit=circuit_list,
        edge_population="S1nonbarrel_neurons__S1nonbarrel_neurons__chemical",
        node_attributes=("synapse_class", "layer", "mtype", "etype", "x", "y", "z"),
    )

    connectivity_matrix_extractions_form = obi.ConnectivityMatrixExtractionScanConfig(
        initialize=extraction_init
    )

    grid_scan = obi.GridScanGenerationTask(
        form=connectivity_matrix_extractions_form,
        output_root=tmp_path / "grid_scan_c",
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()
    obi.run_tasks_for_generated_scan(grid_scan)

    # Rerun --> Error since output file already exists
    with pytest.raises(
        ValueError,
        match=(
            f"Output file '{
                tmp_path / 'grid_scan_c' / circuit_list[0].name / 'connectivity_matrix.h5'
            }' already exists!"
        ),
    ):
        obi.run_tasks_for_generated_scan(grid_scan)

    # Check extracted matrices
    for circuit in circuit_list:
        cmat = ConnectivityMatrix.from_h5(
            tmp_path / "grid_scan_c" / circuit.name / "connectivity_matrix.h5"
        )
        np.testing.assert_array_equal(
            sorted(cmat.vertex_properties), sorted(extraction_init.node_attributes)
        )
        assert (
            circuit.sonata_circuit.edges[extraction_init.edge_population].size == cmat.matrix.sum()
        )

        # Compare with reference matrix
        cmat_ref = ConnectivityMatrix.from_h5(MATRIX_DIR / circuit.name / "connectivity_matrix.h5")
        np.testing.assert_array_equal(cmat_ref.matrix.toarray(), cmat.matrix.toarray())
        assert cmat.vertices.equals(cmat_ref.vertices)
        assert cmat.edges.equals(cmat_ref.edges)
