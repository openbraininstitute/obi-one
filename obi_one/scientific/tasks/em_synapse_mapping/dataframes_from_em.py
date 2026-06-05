import logging

import pandas  # NOQA: ICN001
from entitysdk import Client
from voxcell import CellCollection

from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID
from obi_one.scientific.library.map_em_synapses._defaults import (
    default_node_spec_for,
)
from obi_one.scientific.library.map_em_synapses.write_sonata_nodes_file import (
    assemble_collection_from_specs,
)

L = logging.getLogger(__name__)


def synapses_and_nodes_dataframes_from_EM(
    em_dataset: EMDataSetFromID, pt_root_id: int, db_client: Client, cave_version: int
) -> tuple[pandas.DataFrame, CellCollection, CellCollection, list]:
    # SYNAPSES
    syns, syns_notice = em_dataset.synapse_info_df(
        pt_root_id, cave_version, col_location="post_pt_position", db_client=db_client
    )
    # NODES
    pre_pt_root_to_sonata = (
        syns["pre_pt_root_id"]
        .drop_duplicates()
        .reset_index(drop=True)
        .reset_index()
        .set_index("pre_pt_root_id")
    )
    post_pt_root_to_sonata = (
        syns["post_pt_root_id"]
        .drop_duplicates()
        .reset_index(drop=True)
        .reset_index()
        .set_index("post_pt_root_id")
    )
    node_spec = default_node_spec_for(em_dataset, db_client)
    coll_pre, nodes_notice = assemble_collection_from_specs(
        em_dataset, db_client, cave_version, node_spec, pre_pt_root_to_sonata
    )  # ty:ignore[not-iterable]
    coll_post, _ = assemble_collection_from_specs(
        em_dataset, db_client, cave_version, node_spec, post_pt_root_to_sonata
    )  # ty:ignore[not-iterable]

    return syns, coll_pre, coll_post, [syns_notice, *nodes_notice]
