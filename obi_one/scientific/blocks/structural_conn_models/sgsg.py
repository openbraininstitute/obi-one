"""Spatial-geometric / stochastic-spread-graph (SGSG) structural connectivity model."""

from typing import ClassVar

import numpy as np
import scipy.sparse as sp
from pydantic import Field, NonNegativeInt, PositiveInt

from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.structural_conn_models.base import (
    PathwayConnContext,
    PathwayStructuralConnModel,
)

_CONNALYSIS_INSTALL_HINT = (
    "The SGSG connectivity model requires connectome-analysis (connalysis). "
    "Install with: pip install obi-one[connectivity]"
)


class SgsgConnModel(PathwayStructuralConnModel):
    """Spatial-geometric / stochastic-spread-graph connectivity model (connalysis).

    Connections are drawn in two stages using the Connectome-Analysis package (``connalysis``):

    1. ``connalysis.randomization.random_geometric_model`` builds an intermediate directed
       adjacency matrix from the neuron positions, using the ``n_neighbors`` nearest neighbours
       as connection candidates and picking ``n_pick`` of them per node.
    2. ``connalysis.randomization.stochastic_spread_model`` spreads over that intermediate graph
       (parameterized by ``n_protected``, ``q`` and ``decay``) to produce the final adjacency
       matrix, whose non-zero entries determine which source/target neuron pairs are connected.

    All other parameters of the two functions are left at their defaults. The model requires
    x/y/z positions for the involved populations.
    """

    title: ClassVar[str] = "SGSG (geometric + stochastic spread)"
    description: ClassVar[str] = (
        "Connects neurons using a random geometric graph refined by a stochastic spread process"
        " (Connectome-Analysis). Requires the optional 'connectivity' dependency."
    )

    n_neighbors: PositiveInt = Field(
        title="Number of neighbours",
        description="Number of nearest neighbours considered as connection candidates for each"
        " node in the intermediate random geometric graph (random_geometric_model n_neighbors).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    n_pick: PositiveInt = Field(
        title="Number picked",
        description="Number of candidate neighbours actually connected from each node in the"
        " intermediate random geometric graph (random_geometric_model n_pick).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    n_protected: NonNegativeInt = Field(
        default=0,
        title="Protected steps",
        description="Number of initial spread steps taken with reduced stochasticity"
        " (stochastic_spread_model n_protected). Set to 0 to disable.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    q: float = Field(
        default=10.0,
        gt=0.0,
        title="Expected spread (q)",
        description="Expected number of nodes spread to in each step of the stochastic spread"
        " process (stochastic_spread_model q).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT,
        },
    )
    decay: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        title="Decay",
        description="Multiplicative decay applied to q after each spread step"
        " (stochastic_spread_model decay); must be between 0 and 1.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT,
        },
    )

    @staticmethod
    def _assemble_cross_population_matrix(
        source_positions: np.ndarray,
        target_positions: np.ndarray,
        *,
        n_neighbors: int,
        n_pick: int,
    ) -> "sp.csr_matrix":
        """Assemble the square N x N adjacency matrix for a cross-population pathway.

        ``stochastic_spread_model`` needs a single square matrix, so an ``N x N`` matrix
        (``N = n_source + n_target``) is built with the source block first and the target block
        last. ``random_geometric_model`` returns matrices in the ``M[from, to]`` convention
        (row = source, column = target), and the blocks are placed to keep that convention for
        the combined matrix:

        - top-right ``[0:n_source, n_source:N]`` (rows = source, cols = target):
          ``random_geometric_model(target_positions, pts_x=source_positions)`` -- the
          source -> target geometric graph (its row sums equal ``n_pick``, i.e. rows are the
          "from"/source nodes);
        - bottom-right ``[n_source:N, n_source:N]`` (rows = target, cols = target):
          ``random_geometric_model(target_positions)`` so the spread can propagate within the
          target population;
        - the left quadrants (source columns) are zero.

        The caller transposes this ``M[from, to]`` matrix to ``M[to, from]`` before passing it to
        ``stochastic_spread_model`` (see ``draw_connections``).
        """
        from connalysis.randomization import (  # ruff: ignore[import-outside-top-level]
            random_geometric_model,
        )

        n_source = source_positions.shape[0]
        n_target = target_positions.shape[0]
        total = n_source + n_target

        top_right = random_geometric_model(
            target_positions, pts_x=source_positions, n_neighbors=n_neighbors, n_pick=n_pick
        )
        bottom_right = random_geometric_model(
            target_positions, n_neighbors=n_neighbors, n_pick=n_pick
        )

        combined = sp.lil_matrix((total, total), dtype=float)
        combined[0:n_source, n_source:total] = top_right
        combined[n_source:total, n_source:total] = bottom_right
        return combined.tocsr()

    def draw_connections(  # ruff: ignore[too-many-locals]
        self,
        context: PathwayConnContext,
        rng: np.random.Generator,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Draw connections via a random geometric graph refined by stochastic spread.

        The connalysis functions draw from NumPy's legacy global RNG rather than an explicit
        generator, so the global RNG is seeded here from a value drawn from ``rng``. This keeps
        the result reproducible for a given task seed and threaded through the same generator as
        the other models, without coupling to connalysis's internal randomness source.

        The connalysis conventions are subtle. ``random_geometric_model`` returns matrices in the
        ``M[from, to]`` convention (row = source, column = target). ``stochastic_spread_model``,
        due to a known bug, reads its *input* as ``M[to, from]`` but returns its *output* as
        ``M[from, to]``. The intermediate (``M[from, to]``) is therefore transposed to
        ``M[to, from]`` before spreading, and the output (``M[from, to]``) is read directly as
        ``source = row``, ``target = column``.
        """
        try:
            from connalysis.randomization import (  # ruff: ignore[import-outside-top-level]
                random_geometric_model,
                stochastic_spread_model,
            )
        except ImportError as e:  # pragma: no cover
            raise OBIONEError(_CONNALYSIS_INSTALL_HINT) from e

        source_positions = context.source_positions
        target_positions = context.target_positions
        if source_positions is None or target_positions is None:
            msg = (
                "The SGSG connectivity model requires x/y/z positions for both the source and"
                " target populations, but at least one population exposes none."
            )
            raise OBIONEError(msg)

        source_ids = context.source_ids
        target_ids = context.target_ids
        if source_ids.size == 0 or target_ids.size == 0:
            return self._empty()

        # connalysis uses NumPy's legacy global RNG; seed it from the task-provided generator so
        # results are reproducible and driven by the same seed as the other models.
        np.random.seed(int(rng.integers(0, 2**32 - 1)))  # ruff: ignore[numpy-legacy-random]

        same = context.same_population and np.array_equal(source_ids, target_ids)
        if same:
            intermediate = random_geometric_model(
                source_positions, n_neighbors=self.n_neighbors, n_pick=self.n_pick
            )
        else:
            intermediate = self._assemble_cross_population_matrix(
                source_positions,
                target_positions,
                n_neighbors=self.n_neighbors,
                n_pick=self.n_pick,
            )

        result = stochastic_spread_model(
            intermediate.T.tocsr(), n_protected=self.n_protected, q=self.q, decay=self.decay
        )
        coo = result.tocoo()
        # The intermediate is M[from, to] (random_geometric_model's convention); transposing it
        # yields M[to, from], which is what stochastic_spread_model's (buggy) input expects. Its
        # output is M[from, to], so it is read directly as source = row, target = column.
        src_idx = coo.row.astype(np.int64, copy=False)
        tgt_idx = coo.col.astype(np.int64, copy=False)

        if same:
            pre_local = src_idx
            post_local = tgt_idx
            if not self.allow_self_connections:
                non_self = pre_local != post_local
                pre_local = pre_local[non_self]
                post_local = post_local[non_self]
        else:
            # Keep only source -> target edges: source row in the source block, target column in
            # the target block; then remap the combined indices to local source/target indices.
            n_source = source_positions.shape[0]
            keep = (src_idx < n_source) & (tgt_idx >= n_source)
            pre_local = src_idx[keep]
            post_local = tgt_idx[keep] - n_source

        if pre_local.size == 0:
            return self._empty()

        return (
            source_ids[pre_local].astype(np.int64, copy=False),
            target_ids[post_local].astype(np.int64, copy=False),
        )
