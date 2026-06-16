"""Resolve afferent connectivity between EM cell meshes directly from the EM reconstruction."""

import logging
from dataclasses import dataclass

import numpy  # NOQA: ICN001
import pandas  # NOQA: ICN001
from entitysdk import Client

from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID

L = logging.getLogger(__name__)

# Synapse table column used to (re)locate synapses; mirrors the EM synapse mapping task.
_SYN_LOCATION_COLUMN = "post_pt_position"


@dataclass
class EdgeSet:
    """Aggregated synaptic connections between two node populations.

    Node ids are 0-based indices into the respective node populations and ``synapse_count`` is
    the number of EM synapses for each (source, target) connection.
    """

    source_node_id: numpy.ndarray
    target_node_id: numpy.ndarray
    synapse_count: numpy.ndarray


@dataclass
class ResolvedConnectivity:
    """Connectivity resolved among a set of EM neurons.

    Attributes:
        point_pt_root_ids: pt_root_ids of the modelled (internal) neurons, in circuit order.
        virtual_pt_root_ids: pt_root_ids of the external presynaptic neurons (virtual nodes).
        internal_edges: connections among the modelled neurons.
        external_edges: connections from virtual neurons onto the modelled neurons.
        internal_matrix: internal synapse-count matrix (rows = pre, cols = post).
        neuron_summary: per-neuron afferent synapse summary.
    """

    point_pt_root_ids: list[int]
    virtual_pt_root_ids: list[int]
    internal_edges: EdgeSet
    external_edges: EdgeSet
    internal_matrix: pandas.DataFrame
    neuron_summary: pandas.DataFrame


def _record_pre_counts(
    pre_counts: pandas.Series,
    point_set: set[int],
    point_index: dict[int, int],
    post_idx: int,
    internal_counts: numpy.ndarray,
    external_counts: dict[tuple[int, int], int],
) -> int:
    """Record one neuron's afferents into the internal matrix / external dict; return # internal."""
    internal_total = 0
    for pre_pt_root_id, count in pre_counts.items():
        if pre_pt_root_id in point_set:
            internal_counts[point_index[pre_pt_root_id], post_idx] = count
            internal_total += int(count)
        else:
            external_counts[int(pre_pt_root_id), post_idx] = int(count)
    return internal_total


def _accumulate_counts(
    em_dataset: EMDataSetFromID,
    pt_root_ids: list[int],
    cave_version: int,
    db_client: Client,
) -> tuple[numpy.ndarray, dict[tuple[int, int], int], list[dict]]:
    """Query afferent synapses per neuron and aggregate internal/external synapse counts."""
    point_index = {pt_root_id: idx for idx, pt_root_id in enumerate(pt_root_ids)}
    point_set = set(pt_root_ids)
    internal_counts = numpy.zeros((len(pt_root_ids), len(pt_root_ids)), dtype=numpy.int64)
    external_counts: dict[tuple[int, int], int] = {}
    summary_rows = []

    for post_pt_root_id in pt_root_ids:
        syns, _notice = em_dataset.synapse_info_df(
            post_pt_root_id, cave_version, col_location=_SYN_LOCATION_COLUMN, db_client=db_client
        )
        post_idx = point_index[post_pt_root_id]
        pre_counts = syns["pre_pt_root_id"].value_counts()
        internal_total = _record_pre_counts(
            pre_counts, point_set, point_index, post_idx, internal_counts, external_counts
        )
        summary_rows.append(
            {
                "pt_root_id": post_pt_root_id,
                "total_afferent_synapses": len(syns),
                "internal_afferent_synapses": internal_total,
                "external_afferent_synapses": len(syns) - internal_total,
                "external_presynaptic_partners": int((~pre_counts.index.isin(point_set)).sum()),
            }
        )

    return internal_counts, external_counts, summary_rows


def _build_edge_sets(
    internal_counts: numpy.ndarray,
    external_counts: dict[tuple[int, int], int],
    virtual_index: dict[int, int],
) -> tuple[EdgeSet, EdgeSet]:
    """Turn the aggregated counts into internal and external edge sets (0-based node indices)."""
    internal_pre, internal_post = numpy.nonzero(internal_counts)
    internal_edges = EdgeSet(
        source_node_id=internal_pre.astype(numpy.uint32),
        target_node_id=internal_post.astype(numpy.uint32),
        synapse_count=internal_counts[internal_pre, internal_post].astype(numpy.int64),
    )

    external_items = sorted(
        external_counts.items(), key=lambda item: (virtual_index[item[0][0]], item[0][1])
    )
    external_edges = EdgeSet(
        source_node_id=numpy.array(
            [virtual_index[ext] for (ext, _post), _count in external_items], dtype=numpy.uint32
        ),
        target_node_id=numpy.array(
            [post for (_ext, post), _count in external_items], dtype=numpy.uint32
        ),
        synapse_count=numpy.array([count for _pair, count in external_items], dtype=numpy.int64),
    )
    return internal_edges, external_edges


def resolve_connectivity(
    em_dataset: EMDataSetFromID,
    pt_root_ids: list[int],
    cave_version: int,
    db_client: Client,
) -> ResolvedConnectivity:
    """Resolve the afferent connectivity among a set of EM neurons.

    For each neuron (identified by its pt_root_id) all afferent synapses are queried from the EM
    dense reconstruction. Synapses whose presynaptic neuron is also part of the set form the
    internal connectivity; the remainder come from external (virtual) presynaptic neurons.

    Args:
        em_dataset: The EM dense reconstruction dataset wrapper.
        pt_root_ids: The pt_root_ids of the modelled neurons, in circuit order.
        cave_version: The CAVE materialization version to query.
        db_client: Entity SDK client.

    Returns:
        A ResolvedConnectivity holding the modelled and virtual neurons, the internal and
        external edge sets, and a synapse-count matrix / per-neuron summary for reporting.
    """
    internal_counts, external_counts, summary_rows = _accumulate_counts(
        em_dataset, pt_root_ids, cave_version, db_client
    )

    virtual_pt_root_ids = sorted({ext for (ext, _post) in external_counts})
    virtual_index = {pt_root_id: idx for idx, pt_root_id in enumerate(virtual_pt_root_ids)}
    internal_edges, external_edges = _build_edge_sets(
        internal_counts, external_counts, virtual_index
    )

    internal_matrix = pandas.DataFrame(
        internal_counts,
        index=pandas.Index(pt_root_ids, name="pre_pt_root_id"),
        columns=pandas.Index(pt_root_ids, name="post_pt_root_id"),
    )
    neuron_summary = pandas.DataFrame(summary_rows).set_index("pt_root_id")

    return ResolvedConnectivity(
        point_pt_root_ids=list(pt_root_ids),
        virtual_pt_root_ids=virtual_pt_root_ids,
        internal_edges=internal_edges,
        external_edges=external_edges,
        internal_matrix=internal_matrix,
        neuron_summary=neuron_summary,
    )
