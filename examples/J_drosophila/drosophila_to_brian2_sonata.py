import itertools as it
import json
from pathlib import Path
from textwrap import dedent

import h5py
import numpy as np
import pandas as pd
from brainbuilder.utils.sonata.split_population import _write_indexes  # noqa: PLC2701
from brian2 import Hz, ms, mV
from voxcell import CellCollection

POPULATION = "drosophila"


def _create_nodes(output: Path, path_comp: Path) -> tuple[Path, pd.DataFrame]:
    df_comp = pd.read_csv(path_comp, index_col=0)
    assert df_comp.Completed.all()

    nodes = pd.DataFrame(
        index=np.arange(0, len(df_comp)),
        data={
            "model_type": "brian2_point",
            "model_template": "json:drosophila",
            "flywire_id": df_comp.index,
        },
    )

    cc = CellCollection.from_dataframe(nodes, index_offset=0)
    cc.population_name = POPULATION
    path = output / "nodes.h5"
    cc.save_sonata(path)
    return path, nodes


def _create_edges(
    output: Path,
    path_connnections: Path,
    nodes: pd.DataFrame,
    default_params: dict,
    *,
    repack_indices: bool = False
) -> Path:
    df_con = pd.read_parquet(path_connnections).sort_values("Postsynaptic_ID")

    fly_wire_idx = nodes.reset_index(names=["id"]).set_index("flywire_id").id
    src = np.asarray(
        df_con.join(fly_wire_idx, on="Presynaptic_ID").id.to_numpy(), dtype=np.uint32
    )
    tgt = np.asarray(
        df_con.join(fly_wire_idx, on="Postsynaptic_ID").id.to_numpy(), dtype=np.uint32
    )

    weight = float(default_params["w_syn"]) * 1000
    # Note: to get the same results, we need to use float64
    w = df_con["Excitatory x Connectivity"].to_numpy(dtype=np.float64) * weight

    path = output / "edges.h5"

    name = f"{POPULATION}__{POPULATION}__brian2_synapse"
    with h5py.File(path, "w") as h5:
        pop = h5.create_group(f"edges/{name}")
        src_ds = pop.create_dataset("source_node_id", data=src)
        src_ds.attrs["node_population"] = POPULATION
        tgt_ds = pop.create_dataset("target_node_id", data=tgt)
        tgt_ds.attrs["node_population"] = POPULATION
        pop.create_dataset("edge_type_id", data=np.full(len(src), -1, dtype=np.int8))

        g0 = pop.create_group("0")
        g0.create_dataset("w", data=w)  # in mV
        g0.create_dataset("@library/model_template", data=["json:synapse"])
        g0.create_dataset("model_template", data=np.zeros(len(src), dtype=np.uint8))
        # g0.create_dataset("delay", data=delays)

    _write_indexes(str(path), name, source_node_count=len(nodes), target_node_count=len(nodes))

    if repack_indices:
        with h5py.File(path, "r+") as h5:
            indices = h5[f"edges/{name}/indices/"]
            for p0, p1 in it.product(("source_to_target", "target_to_source"),
                                     ("node_id_to_ranges", "range_to_edge_id")):
                data = indices[p0][p1][:]
                dgroup = indices[p0][p1].name
                dtype = np.min_scalar_type(np.max(data))
                del h5[dgroup]
                h5.create_dataset(dgroup, data=data.astype(dtype))

    return path


def _create_models(output: Path, default_params: dict) -> Path:
    path = output / "models"
    path.mkdir(exist_ok=True)

    def get_value_unit(name: str) -> list:
        param = default_params[name]
        best_unit = param.get_best_unit()
        return [param / best_unit, str(param.get_best_unit())]

    bio = {
        "params": {
            "model": list(default_params["eqs"].split("\n")),
            "method": "linear",
            "threshold": default_params["eq_th"],
            "reset": default_params["eq_rst"],
            "refractory": "rfc",
            },
        "namespace": {
            "t_mbr": get_value_unit("t_mbr"),  # [20, "ms"],
            "tau": get_value_unit("tau"),  # [5, "ms"],          # time constant
            "v_0": get_value_unit("v_0"),  # [-52, "mV"],        # resting potential
            "v_th": get_value_unit("v_th"),  # [-45, "mV"],       # threshold for spiking
            "v_rst": get_value_unit("v_rst"),  # [-52, "mV"],      # reset potential after spike
            },
        "initial": {
            "v": get_value_unit("v_rst"),
            "g": [0, "mV"],
            "rfc": [2.2, "ms"],
            }
        }
    with (path / "drosophila.json").open("w") as fd:
        json.dump(bio, fd, indent=2)

    synapse = {
        "params": {
            "model": "w : volt",
            "on_pre": "g += w",
            "delay": [1.8, "ms"],
            },
        "dynamics": {
            "w": "mV",
            },
        }
    with (path / "synapse.json").open("w") as fd:
        json.dump(synapse, fd, indent=2)

    return path


def _create_nodesets(output: Path, nodes: pd.DataFrame, sugar_nodes: list[int]) -> Path:
    path = output / "node_sets.json"
    node_sets = {
        "All": {"population": POPULATION},
        "sugar": {
            "population": POPULATION,
            "node_id": nodes[np.isin(nodes.flywire_id, sugar_nodes)].index.to_list(),
        },
    }
    with path.open("w") as fd:
        json.dump(node_sets, fd)
    return path


def _create_config(
    output: Path, models_path: Path, nodes_path: Path, edges_path: Path, node_sets_path: Path
) -> Path:
    def strip_output(p: Path) -> str:
        return p.name

    path = output / "circuit_config.json"
    config = {
        "components": {
            "point_neuron_models_dir": strip_output(models_path),
        },
        "node_sets_file": strip_output(node_sets_path),
        "target_simulator": "Brian2",
        "networks": {
            "nodes": [
                {
                    "nodes_file": strip_output(nodes_path),
                    "populations": {
                        POPULATION: {"type": "brian2_point"},
                    },
                }
            ],
            "edges": [
                {
                    "edges_file": strip_output(edges_path),
                    "populations": {
                        f"{POPULATION}__{POPULATION}__brian2_synapse": {"type": "brian2_synapse"}
                    },
                }
            ],
        },
    }

    with path.open("w") as fd:
        json.dump(config, fd)

    return path


def convert(
    output: Path,
    path_comp: Path,
    path_connnections: Path,
    sugar_nodes: list[int],
    default_params: dict,
) -> Path:
    output.mkdir(parents=True, exist_ok=True)

    models_path = _create_models(output, default_params)
    nodes_path, nodes = _create_nodes(output, path_comp)
    edges_path = _create_edges(output, path_connnections, nodes, default_params)
    node_sets_path = _create_nodesets(output, nodes, sugar_nodes)
    return _create_config(output, models_path, nodes_path, edges_path, node_sets_path)


if __name__ == "__main__":
    output = Path("output")
    output.mkdir(exist_ok=True)
    DROSOPHILA_REPO = Path()
    PATH_COMP = DROSOPHILA_REPO / "2023_03_23_completeness_630_final.csv"
    PATH_CON = DROSOPHILA_REPO / "2023_03_23_connectivity_630_final.parquet"

    SUGAR_NODES = [
            720575940611875570,
            720575940612670570,
            720575940616885538,
            720575940617000768,
            720575940617937543,
            720575940620900446,
            720575940621502051,
            720575940621754367,
            720575940624963786,
            720575940628853239,
            720575940629176663,
            720575940630233916,
            720575940630797113,
            720575940632425919,
            720575940632889389,
            720575940633143833,
            720575940637568838,
            720575940638202345,
            720575940639198653,
            720575940639332736,
            720575940640649691,
        ]

    default_params = {
        # trials
        "t_run": 1000 * ms,  # duration of trial
        # network constants
        # Kakaria and de Bivort 2017 https://doi.org/10.3389/fnbeh.2017.00008
        "v_0": -52 * mV,  # resting potential
        "v_rst": -52 * mV,  # reset potential after spike
        "v_th": -45 * mV,  # threshold for spiking
        "t_mbr": 20 * ms,  # membrane time scale (capacitance * resistance = .002 * uF * 10. * Mohm)
        # Jürgensen et al https://doi.org/10.1088/2634-4386/ac3ba6
        "tau": 5 * ms,  # time constant
        # Lazar et al https://doi.org/10.7554/eLife.62362
        "t_rfc": 2.2 * ms,  # refractory period
        # Paul et al 2015 doi: 10.3389/fncel.2015.00029
        "t_dly": 1.8 * ms,  # delay for changes in post-synaptic neuron
        # Free parameter
        "w_syn": 0.275 * mV,  # weight per synapse (note: modulated by exponential decay)
        # Default activation rates
        "r_poi": 150 * Hz,  # default rate of the Poisson inputs
        "r_poi2": 0 * Hz,  # default rate of a 2nd class of Poisson inputs
        "f_poi": 250,  # scaling factor for Poisson synapse; 250 is sufficient to cause spiking
        # equations for neurons
        # alpha synapse https://doi.org/10.1017/CBO9780511815706; See https://brian2.readthedocs.io/en/stable/user/converting_from_integrated_form.html
        "eqs": dedent("""
                             dv/dt = (v_0 - v + g) / t_mbr : volt (unless refractory)
                             dg/dt = -g / tau               : volt (unless refractory)
                             rfc                            : second
                             """),
        # condition for spike
        "eq_th": "v > v_th",
        # rules for spike
        "eq_rst": "v = v_rst; w = 0; g = 0 * mV",
    }

    convert(
        output,
        path_comp=PATH_COMP,
        path_connnections=PATH_CON,
        sugar_nodes=SUGAR_NODES,
        default_params=default_params,
    )

    sim_config = {
        "run": {
            "tstop": 1000,
            "dt": 0.1,
            "random_seed": 42
            },
        "target_simulator": "Brian2",
        "network": "circuit_config.json",
        "inputs": {
            "poisson": {
                "input_type": "spikes",
                "module": "poisson",
                "node_set": "sugar",
                "delay": 0,
                "duration": 1000,
                "rate": 150,
                "weight": 68.75
                }
            }
        }

    with (output / "simulation_config.json").open("w") as fd:
        json.dump(sim_config, fd)
