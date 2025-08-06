"""Helper function to extract nodes in simplices in a matrix
Author: Daniela Egas Santander
Last updated: 06.2024.
"""

import logging

import numpy as np
import pandas as pd
from connalysis.network.topology import list_simplices_by_dimension
from scipy import sparse

L = logging.getLogger(__name__)


def determine_selection(
    sl: pd.Series,
    v: int,
    dim: int,
    *,
    subsample: bool,
    n_count_max: int,
    subsample_method: str,
    seed: int,
) -> np.ndarray:
    # Get nodes
    selection_test = np.unique(sl.loc[dim])
    if not subsample:
        return selection_test
    if selection_test.shape[0] <= n_count_max:
        L.info("No subselection required")
        selection = selection_test
    # Sub-sampling if there are too many neurons
    elif subsample_method == "random":
        selection = subsample_random(v, selection_test, n_count_max, seed)
    elif subsample_method == "node_participation":
        selection = subsample_by_node_participation(sl, n_count_max, dim)
    elif subsample_method == "sample_simplices":
        selection = subsample_simplices(sl, n_count_max, dim)
    return selection


def simplex_submat(
    adj: sparse.coo_matrix,
    v: int,
    dim: int,
    *,
    v_position: str = "source",
    subsample: bool = False,
    n_count_max: int | None = None,
    subsample_method: str = "node_participation",
    simplex_type: str = "directed",
    seed: int | None = None,
) -> np.ndarray:
    """Extracts the indices of nodes in the adjacency matrix that participate in simplices of
    dimension dim with v as a source or target.

    Parameters
    ----------
    adj : scipy sparse matrix
        Adjacency matrix of the network (square, is converted to binary if not already binary).
    v : int
        Index of the node of interest (source or target).
    dim : int
        Dimension of the simplex to extract.
    v_position : {'source', 'target'}, optional
        Whether the node `v` is considered as a source or target in the
        simplices (default: 'source').
    subsample : bool, optional
        Whether to subsample the nodes if there are too many (default: False).
    n_count_max : int, optional
        Maximum number of nodes to return if subsampling (required if subsample=True).
    subsample_method : {'node_participation', 'random', 'sample_simplices'}, optional
        Method for subsampling nodes if needed (default: 'node_participation').
    simplex_type : {'directed', 'reciprocal', 'undirected'}, optional
        Type of simplex to extract (default: 'directed').
    seed : int, optional
        Random seed for reproducibility for random subsampling.

    Returns:
    -------
    np.ndarray or tuple of np.ndarrays
        If `nodes` is False, returns the nodes in simplices of dimension `dim` with `v` as source
        or target
        If `subsample` is True, returns a tuple (`selection`, `nodes`), where `nodes` is as above
        and`selection` is the subsampled set.

    Notes:
    -----
    - Subsampling methods:
        - 'random': randomly selects nodes from all nodes.
        - 'node_participation': selects nodes with highest node participation in dimension dim in
            the submatrix on the nodes in `nodes`.
        - 'sample_simplices': samples simplices while the number of nodes on them is still smaller
            or equal than the required size.
    - If the number of candidate nodes is less than or equal to `n_count_max`,
        no subsampling is performed.
    - If the number of sampled nodes is smaller than the nodes in a simplex of dimension `dim`
        there is no possible solution.

    """
    # Basic checks
    if adj.shape[0] != adj.shape[1]:
        msg = "Adjacency matrix must be square"
        raise ValueError(msg)
    if v < 0 or v >= adj.shape[0]:
        msg = f"v must be between 0 and {adj.shape[0] - 1} since its a node in adj"
        raise ValueError(msg)
    if subsample and not isinstance(n_count_max, int):
        msg = "n_count_max must be an integer when subsampling"
        raise ValueError(msg)
    if v_position == "target":
        adj = adj.transpose()
    adj = adj.astype(bool).astype(int).tocsr()

    # Get simplex list on v
    sl = list_simplices_by_dimension(
        adj, max_dim=dim, nodes=np.array([v]), simplex_type=simplex_type
    )
    # Check if dimension and n_count_max are valid
    if dim > sl.index.max():
        dim = sl.index.max()
        L.info(f"> Dimension not attained using dimension {dim} instead.")
    if subsample and (n_count_max < dim + 1):
        n_count_max = dim + 1
        L.info(
            f"> n_count_max is too small to form a single {dim}-simplex, sampling n_count_max = \
                {n_count_max} neurons instead."
        )

    return determine_selection(
        sl,
        v,
        dim,
        subsample=subsample,
        n_count_max=n_count_max,
        subsample_method=subsample_method,
        seed=seed,
    )


def subsample_random(v: int, selection_test: np.ndarray, n_count_max: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    subsample = rng.choice(selection_test[selection_test != v], size=n_count_max - 1, replace=False)
    return np.append(v, subsample)


def subsample_by_node_participation(sl: pd.Series, n_count_max: int, dim: int) -> pd.Series:
    node, par = np.unique(sl.loc[dim], return_counts=True)
    node_par = pd.Series(par, index=node, name=dim).sort_values(ascending=False)
    selection = node_par.index[:n_count_max]
    return selection


def subsample_simplices(sl: pd.Series, n_count_max: int, dim: int) -> np.ndarray:
    n_simplices = len(sl.loc[dim])
    selection = np.unique(sl.loc[dim][n_simplices - 1 :])
    i = 2
    while i < sl.loc[dim].shape[0]:
        temp = np.unique(sl.loc[dim][n_simplices - i :])
        if temp.shape[0] <= n_count_max:
            i += 1
            selection = temp
        else:
            break
    return selection
