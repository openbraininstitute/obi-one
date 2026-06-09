from typing import Annotated

import pandas as pd
from connectome_manipulator.connectome_comparison import connectivity
from entitysdk.client import Client
from pydantic import BaseModel, Field
from pydantic.types import PositiveFloat

import obi_one as obi
from obi_one.scientific.library.sonata_circuit_assets import TemporarySonataCircuit


class ConnectivityMetricsRequest(BaseModel):
    circuit_id: str
    edge_population: Annotated[
        str, Field(description="Name of the edge population to extract connectivity metrics from")
    ]
    pre_selection: Annotated[
        dict[str, str | list[str]] | None,
        Field(description="Property/value pairs for pre-synaptic neuron selection"),
    ] = None
    pre_node_set: Annotated[
        str | None, Field(description="Existing node set to apply pre-synaptic neuron selection in")
    ] = None
    post_selection: Annotated[
        dict[str, str | list[str]] | None,
        Field(description="Property/value pairs for post-synaptic neuron selection"),
    ] = None
    post_node_set: Annotated[
        str | None,
        Field(description="Existing node set to apply post-synaptic neuron selection in"),
    ] = None
    group_by: Annotated[str | None, Field(description="Property name to group connectivity by")] = (
        None
    )
    max_distance: Annotated[
        PositiveFloat | None,
        Field(description="Maximum distance (in um) to take connectivity into account"),
    ] = None


class ConnectivityMetricsOutput(BaseModel):
    connection_probability: (
        Annotated[
            dict,
            Field(
                description="Connection probabilities (in percent) between pre- and"
                " post-synaptic types as dict representation of a dataframe"
            ),
        ]
        | None
    ) = None
    mean_number_of_synapses: (
        Annotated[
            dict,
            Field(
                description="Mean numbers of synapses per connection between pre- and"
                " post-synaptic types as dict representation of a dataframe"
            ),
        ]
        | None
    ) = None


def _get_stacked_dataframe(conn_dict: dict, data_sel: str) -> pd.DataFrame:
    df = pd.DataFrame(conn_dict[data_sel]["data"], columns=conn_dict["common"]["tgt_group_values"])
    df["pre"] = conn_dict["common"]["src_group_values"]
    df = df.melt("pre", var_name="post", value_name="data")
    return df


def get_connectivity_metrics(
    circuit_id: str,
    db_client: Client,
    edge_population: str,
    pre_selection: dict | None = None,
    pre_node_set: str | None = None,
    post_selection: dict | None = None,
    post_node_set: str | None = None,
    group_by: str | None = None,
    max_distance: float | None = None,
) -> ConnectivityMetricsOutput:
    # Acces mounted circuit if possible, or download partial circuit otherwise
    # (incl. config, node sets, selected edges, src/tgt nodes of selected edges)
    with TemporarySonataCircuit(
        db_client, circuit_id, edge_population=edge_population
    ) as cfg_path:
        # Load circuit
        circuit = obi.Circuit(name=circuit_id, path=str(cfg_path))
        c = circuit.sonata_circuit

        # Check inputs
        if not pre_selection:
            pre_selection = None
        if not post_selection:
            post_selection = None

        if not pre_node_set:
            pre_node_set = None
        if not post_node_set:
            post_node_set = None

        if pre_node_set is None:
            pre_dict = pre_selection
        else:
            node_set_dict = {"node_set": pre_node_set}
            pre_dict = node_set_dict if pre_selection is None else pre_selection | node_set_dict
        if post_node_set is None:
            post_dict = post_selection
        else:
            node_set_dict = {"node_set": post_node_set}
            post_dict = node_set_dict if post_selection is None else post_selection | node_set_dict
        dist_props = None if max_distance is None else ["x", "y", "z"]

        if not group_by:
            group_by = None

        # Compute connection probability
        conn_dict = connectivity.compute(
            c,
            sel_src=pre_dict,
            sel_dest=post_dict,
            edges_popul_name=edge_population,
            group_by=group_by,
            max_distance=max_distance,
            props_for_distance=dist_props,
            skip_empty_groups=True,
        )

    # Return results
    df_prob = _get_stacked_dataframe(conn_dict, "conn_prob")
    df_nsyn = _get_stacked_dataframe(conn_dict, "nsyn_conn")
    conn_output = ConnectivityMetricsOutput(
        connection_probability=df_prob.to_dict(),
        mean_number_of_synapses=df_nsyn.to_dict(),
    )
    return conn_output
