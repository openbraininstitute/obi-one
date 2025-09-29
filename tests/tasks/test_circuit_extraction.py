import json
import re
from pathlib import Path

import numpy as np
import pytest
from bluepysnap import Circuit

import obi_one as obi

from tests.utils import CIRCUIT_DIR


def _is_virtual_epop(circuit, epop_name):
    c = circuit.sonata_circuit
    return c.edges[epop_name].source.type == "virtual"


def _update_ids(pop_dict, pop, ids):
    if len(ids) == 0:
        return
    if pop in pop_dict:
        pop_dict[pop] = np.union1d(pop_dict[pop], ids)
    else:
        pop_dict[pop] = np.unique(ids)


def _get_population_ids(circuit, neuron_set, with_virtual, with_external):
    c = circuit.sonata_circuit
    npop_dict = {}
    epop_dict = {}
    for epop_name in c.edges.population_names:
        edges = c.edges[epop_name]
        src = edges.source
        tgt = edges.target
        if _is_virtual_epop(circuit, epop_name):
            tgt_nids = neuron_set.get_neuron_ids(circuit, population=tgt.name)
            etab = edges.pathway_edges(target=tgt_nids, properties=["@source_node", "@target_node"])
            if with_virtual:
                _update_ids(npop_dict, src.name, etab["@source_node"].to_numpy())
                _update_ids(epop_dict, epop_name, etab.index.to_numpy())
            _update_ids(npop_dict, tgt.name, etab["@target_node"].to_numpy())
        else:
            src_nids = neuron_set.get_neuron_ids(circuit, population=src.name)
            tgt_nids = neuron_set.get_neuron_ids(circuit, population=tgt.name)
            etab = edges.pathway_edges(
                source=src_nids, target=tgt_nids, properties=["@source_node", "@target_node"]
            )
            _update_ids(npop_dict, src.name, etab["@source_node"].to_numpy())
            _update_ids(npop_dict, tgt.name, etab["@target_node"].to_numpy())
            _update_ids(epop_dict, epop_name, etab.index.to_numpy())

            if with_external:
                ext_src_nids = np.setdiff1d(c.nodes[src.name].ids(), src_nids)
                etab = edges.pathway_edges(
                    source=ext_src_nids,
                    target=tgt_nids,
                    properties=["@source_node", "@target_node"],
                )
                _update_ids(npop_dict, "external_" + src.name, etab["@source_node"].to_numpy())
                _update_ids(npop_dict, tgt.name, etab["@target_node"].to_numpy())
                _update_ids(epop_dict, "external_" + epop_name, etab.index.to_numpy())
    return npop_dict, epop_dict


def _check_nodes(npop_dict, c_orig, c_res, id_map):
    for npop_name, npop_ids in npop_dict.items():
        # Check nodes
        nids_res = c_res.nodes[npop_name].ids()
        assert len(nids_res) == len(npop_ids)
        # Check ID mapping
        if npop_name.startswith("external_"):
            assert id_map[npop_name]["parent_name"] == npop_name.replace("external_", "")
            assert id_map[npop_name]["original_name"] == npop_name.replace("external_", "")
        else:
            assert id_map[npop_name]["parent_name"] == npop_name
            assert id_map[npop_name]["original_name"] == npop_name
        np.testing.assert_array_equal(id_map[npop_name]["parent_id"], npop_ids)
        np.testing.assert_array_equal(id_map[npop_name]["original_id"], npop_ids)
        np.testing.assert_array_equal(id_map[npop_name]["new_id"], nids_res)
        # Check node properties
        if npop_name.startswith("external_"):
            np.testing.assert_array_equal(
                c_orig.nodes[npop_name.replace("external_", "")].property_names,
                c_res.nodes[npop_name].property_names,
            )
        else:
            np.testing.assert_array_equal(
                c_orig.nodes[npop_name].property_names, c_res.nodes[npop_name].property_names
            )


def _check_edges(epop_dict, c_orig, c_res, id_map):
    for epop_name, epop_ids in epop_dict.items():
        # Check edges
        eids_res = c_res.edges[epop_name].pathway_edges(
            source=id_map[c_res.edges[epop_name].source.name]["new_id"],
            target=id_map[c_res.edges[epop_name].target.name]["new_id"],
        )
        assert len(eids_res) == len(epop_ids)
        # Check properties
        if epop_name.startswith("external_"):
            np.testing.assert_array_equal(
                c_orig.edges[epop_name.replace("external_", "")].property_names,
                c_res.edges[epop_name].property_names,
            )
        else:
            np.testing.assert_array_equal(
                c_orig.edges[epop_name].property_names, c_res.edges[epop_name].property_names
            )


def _check_morph(npop_dict, c_res):
    for npop_name in npop_dict:
        nodes = c_res.nodes[npop_name]
        if nodes.type == "biophysical":
            # Check morphologies
            for nid in nodes.ids():
                morph = nodes.morph.get(
                    nid, transform=True, extension="h5"
                )  # Will throw an error if not accessible
                assert morph.n_points > 0


def _check_hoc(npop_dict, c_res):
    for npop_name in npop_dict:
        nodes = c_res.nodes[npop_name]
        if nodes.type == "biophysical":
            # Check HOC files
            hoc_files = [
                _hoc.split(":")[-1] + ".hoc"
                for _hoc in nodes.get(properties="model_template").unique()
            ]
            hoc_path = Path(nodes.config["biophysical_neuron_models_dir"])
            for hoc in hoc_files:
                assert (hoc_path / hoc).exists()


def test_circuit_extraction(tmp_path):
    """Test all combinations of 2 circuits, 2 neuron sets, virtual yes/no, external yes/no
    = 16 extracted circuits.
    """
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

    extraction_init = obi.CircuitExtractionScanConfig.Initialize(
        circuit=circuit_list,
        do_virtual=[False, True],
        create_external=[False, True],
        run_validation=False,
    )
    neuron_set = obi.PredefinedNeuronSet(node_set=["L6_IPC", "L6_TPC:A"])

    circuit_extractions_scan_config = obi.CircuitExtractionScanConfig(
        initialize=extraction_init, neuron_set=neuron_set
    )

    grid_scan = obi.GridScanGenerationTask(
        form=circuit_extractions_scan_config,
        output_root=tmp_path / "grid_scan",
        coordinate_directory_option="ZERO_INDEX",
    )
    grid_scan.execute()
    obi.run_tasks_for_generated_scan(grid_scan)

    # Rerun --> Error since output file already exists
    with pytest.raises(
        ValueError, match=re.escape("Unable to synchronously create group (name already exists)")
    ):
        obi.run_tasks_for_generated_scan(grid_scan)

    # Check extracted circuits
    for instance in grid_scan.single_configs:
        c_orig = instance.initialize.circuit.sonata_circuit
        c_res = Circuit(tmp_path / "grid_scan" / str(instance.idx) / "circuit_config.json")
        with (tmp_path / "grid_scan" / str(instance.idx) / "id_mapping.json").open(
            encoding="utf-8"
        ) as f:
            id_map = json.load(f)

        npop_dict, epop_dict = _get_population_ids(
            instance.initialize.circuit,
            instance.neuron_set,
            with_virtual=instance.initialize.do_virtual,
            with_external=instance.initialize.create_external,
        )

        # Check populations
        np.testing.assert_array_equal(
            sorted(c_res.nodes.population_names), sorted(npop_dict.keys())
        )
        np.testing.assert_array_equal(
            sorted(c_res.edges.population_names), sorted(epop_dict.keys())
        )

        # Check nodes (incl. ID mapping)
        _check_nodes(npop_dict, c_orig, c_res, id_map)

        # Check edges
        _check_edges(epop_dict, c_orig, c_res, id_map)

        # Check morphologies
        _check_morph(npop_dict, c_res)

        # Check HOC files
        _check_hoc(npop_dict, c_res)
