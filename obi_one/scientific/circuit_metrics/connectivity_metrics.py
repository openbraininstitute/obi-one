import numpy as np
import obi_one as obi
import pandas as pd
from entitysdk.client import Client
from entitysdk.models.circuit import Circuit
from pydantic import BaseModel
from connectome_manipulator.connectome_comparison import connectivity


class ConnectivityMetricsOutput(BaseModel):
    pre_type: list[str | None] = [None]
    post_type: list[str | None] = [None]
    connection_probability: list[float] = [np.nan]
    mean_number_of_synapses: list[float] = [np.nan]


def _get_neuron_selection(circuit: obi.Circuit, node_population: str, neuron_set: obi.NeuronSet | None = None) -> list | None:
    if neuron_set is None:
        nrn_sel = None
    else:
        nrn_sel = neuron_set.get_neuron_ids(circuit, node_population)
    return nrn_sel


def _get_stacked_dataframe(conn_dict: dict, data_sel: str) -> pd.DataFrame:
    df = pd.DataFrame(conn_dict[data_sel]["data"], index=conn_dict["common"]["src_group_values"], columns=conn_dict["common"]["tgt_group_values"])
    df.index.name = "pre"
    df.columns.name = "post"
    return df.stack()


def get_connectivity_metrics(circuit_id: str, db_client: Client, edge_population: str | None = None, pre_neuron_set: obi.NeuronSet | None = None, post_neuron_set: obi.NeuronSet | None = None, group_by: str | None = None, max_distance: float | None = None) -> ConnectionProbabilityOutput:
    # Download circuit
    # circuit = ... ==> obi.Circuit
    # c = circuit.sonata_circuit

    # Compute connection probability
    if edge_population is None:
        edge_population = circuit.default_edge_population_name

    if edge_population not in c.edges.population_names:
        msg = f"Edge population '{edge_population}' not found in circuit!"
        raise ValueError(msg)

    edges = c.edges[edge_population]
    src_sel = _get_neuron_selection(circuit, edges.source.name)
    tgt_sel = _get_neuron_selection(circuit, edges.target.name)

    if max_distance is not None:
        dist_props = ["x", "y", "z"]
    else:
        dist_props = None

    conn_dict = connectivity.compute(c, sel_src=src_sel, sel_dest=tgt_sel, edges_popul_name=edge_population, group_by=group_by, max_distance=max_distance, props_for_distance=dist_props)

    # Return results
    df_prob = _get_stacked_dataframe(conn_dict, "conn_prob")
    df_nsyn = _get_stacked_dataframe(conn_dict, "nsyn_conn")
    conn_output = ConnectivityMetricsOutput(
        pre_type=df_prob.index.get_level_values("pre"),
        post_type=df_prob.index.get_level_values("post"),
        connection_probability=df_prob.to_numpy(),
        mean_number_of_synapses=df_nsyn.to_numpy()
    )

    return conn_output