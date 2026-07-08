"""Helpers for extracellular-electrode-location arrays."""

from dataclasses import dataclass
from typing import Any

import bluepysnap as snap
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

from obi_one.scientific.unions.unions_extracellular_locations import ExtracellularLocationsUnion

_SMALL_CIRCUIT = 500
_MEDIUM_CIRCUIT = 5000
_TICK_TOL = 1e-9
_ZERO_TOL = 1e-6


@dataclass
class _ArrayPlot:
    """An electrode-locations block paired with its plot colour and world-space positions."""

    name: str
    block: ExtracellularLocationsUnion
    color: str
    xyz: np.ndarray


def _soma_marker_style(n_somas: int) -> tuple[float, float]:
    """Soma marker (size, alpha), scaled so the cloud stays readable from ~10 to ~100k somas."""
    if n_somas <= _SMALL_CIRCUIT:
        return 60.0, 0.7
    if n_somas <= _MEDIUM_CIRCUIT:
        return 14.0, 0.35
    return 4.0, 0.12


def electrode_locations_summary_dict(
    electrode_locations: dict[str, ExtracellularLocationsUnion],
) -> dict[str, dict[str, Any]]:
    """Summarise a dict of extracellular-location blocks as JSON-serialisable data.

    Each block name maps to its world-space electrode ``locations`` (``[x, y, z]`` lists, with the
    block's origin and direction applied) followed by all of the block's properties (from
    ``model_dump``: ``type``, ``origin_*``/``direction_*`` and the subclass-specific parameters, so
    the key set varies by block type).

    Args:
        electrode_locations: mapping of block name to an extracellular-locations block.

    Returns:
        ``{block_name: {"locations": [[x, y, z], ...], **block_properties}}``.
    """
    return {
        name: {
            "locations": [list(xyz) for xyz in block.get_global_electrode_xyz_locations()],
            **block.model_dump(),
        }
        for name, block in electrode_locations.items()
    }


def plot_extracellular_arrays(  # noqa: C901, PLR0914, PLR0915
    circuit: snap.Circuit,
    electrode_locations: dict[str, ExtracellularLocationsUnion],
) -> Figure:
    """Plot a dictionary of extracellular-electrode arrays relative to a circuit's somas.

    Args:
        circuit: a bluepysnap ``Circuit``; its first biophysical population's somas are shown.
        electrode_locations: dict of ``{name: extracellular-locations block}`` with origin/direction
            already applied. Each entry contributes its global electrode positions (3D + the three
            axis-plane projections) and a local-frame layout panel.

    Returns:
        The matplotlib ``Figure``.
    """
    palette = ["tab:blue", "tab:red", "tab:green", "tab:purple", "tab:orange", "tab:brown"]
    axis_labels = ["X", "Y", "Z"]

    # Somas of the (non-virtual) biophysical population.
    biophysical_pops = [
        name for name in circuit.nodes.population_names if circuit.nodes[name].type != "virtual"
    ]
    soma_xyz = circuit.nodes[biophysical_pops[0]].get(properties=["x", "y", "z"]).to_numpy()

    # Global coordinates and a colour for each array.
    arrays = [
        _ArrayPlot(
            name=name,
            block=block,
            color=palette[k % len(palette)],
            xyz=np.asarray(block.get_global_electrode_xyz_locations(), dtype=float),
        )
        for k, (name, block) in enumerate(electrode_locations.items())
    ]
    electrode_xyz = np.vstack([a.xyz for a in arrays])

    # Subsampled/faint soma cloud so the electrodes stay visible for large circuits.
    max_somas = 4000
    rng = np.random.default_rng(0)
    soma_sample = soma_xyz
    if len(soma_xyz) > max_somas:
        soma_sample = soma_xyz[rng.choice(len(soma_xyz), max_somas, replace=False)]
    soma_size, soma_alpha = _soma_marker_style(len(soma_xyz))

    def set_extreme_ticks(ax, dims="xy", edges=False):  # noqa: ANN001, ANN202, FBT002
        """Label only the extreme ticks (and 0, in range); keep the regular gridline marks.

        ``edges=True`` adds the axis limits themselves as labelled ticks, so the extreme labels sit
        at the plot edges even when the auto-ticker is coarse (the small 3D panel); otherwise the
        outermost auto gridlines are labelled. Ticks come from the locator's ``tick_values`` so the
        result is draw-order independent (3D ticks are otherwise only finalised at draw time).
        """
        for d in dims:
            axis = getattr(ax, f"{d}axis")
            lo, hi = getattr(ax, f"get_{d}lim")()
            grid = [
                t
                for t in axis.get_major_locator().tick_values(lo, hi)
                if lo - _TICK_TOL <= t <= hi + _TICK_TOL
            ]
            if not grid:
                continue
            if edges:
                ticks = sorted({lo, hi, *grid} | ({0.0} if lo < 0.0 < hi else set()))
                keep = {lo, hi} | {t for t in ticks if abs(t) < _ZERO_TOL}
            else:
                ticks = list(grid)
                keep = {grid[0], grid[-1]} | {t for t in grid if abs(t) < _ZERO_TOL}
            getattr(ax, f"set_{d}ticks")(ticks)
            getattr(ax, f"set_{d}ticklabels")([f"{t:.0f}" if t in keep else "" for t in ticks])

    # Local-frame panels keep a fixed height; each panel's width follows its array's shape (a thin
    # column for linear/Neuropixels shanks, a square for the planar Utah grid). Panels flow across a
    # fine column grid, packing as many as fit per row before wrapping, so they never shrink. A
    # square panel spans square_cols columns; one of aspect r spans round(r * square_cols), floored
    # at min_cols so the 3-line title still fits.
    square_cols, min_cols, threed_cols, row_cols, gap = 5, 4, 10, 25, 2
    locals_ = []
    for a in arrays:
        local = np.asarray(a.block.get_local_electrode_xyz_locations(), dtype=float)
        spreads = np.ptp(local, axis=0)
        v_axis, h_axis = sorted(range(3), key=lambda k: (-spreads[k], k))[:2]
        h, v = local[:, h_axis], local[:, v_axis]
        h_half = max(0.55 * np.ptp(h), 45.0)
        v_pad = 0.04 * np.ptp(v) + 5.0
        aspect = 2 * h_half / (np.ptp(v) + 2 * v_pad)
        span = max(min_cols, round(aspect * square_cols))
        locals_.append((h, v, h_axis, v_axis, a, h_half, v_pad, span))

    # Flow the panels across rows (the first local row sits beside the 3D view), leaving a gap
    # between neighbours so their tick labels do not collide.
    placements = []
    grid_row, col, first_in_row = 1, threed_cols, True
    for *_, span in locals_:
        if col + span > row_cols:
            grid_row, col, first_in_row = grid_row + 1, 0, True
        placements.append((grid_row, col, first_in_row))
        col, first_in_row = col + span + gap, False
    n_rows = 1 + max(row for row, _, _ in placements)

    fig = plt.figure(figsize=(15, 5 * n_rows))
    gs = fig.add_gridspec(n_rows, row_cols)
    proj_gs = gs[0, :].subgridspec(1, 3)

    # Top row: the three axis-plane projections (whole circuit; shared square window).
    data_lo = np.minimum(soma_xyz.min(axis=0), electrode_xyz.min(axis=0))
    data_hi = np.maximum(soma_xyz.max(axis=0), electrode_xyz.max(axis=0))
    proj_centre = 0.5 * (data_lo + data_hi)
    proj_half = 0.5 * (data_hi - data_lo).max() * 1.05
    projections = {(0, 1): proj_gs[0, 0], (0, 2): proj_gs[0, 1], (1, 2): proj_gs[0, 2]}
    for (i, j), cell in projections.items():
        ax = fig.add_subplot(cell)
        ax.scatter(
            soma_sample[:, i],
            soma_sample[:, j],
            s=soma_size,
            c="tab:gray",
            alpha=soma_alpha,
            linewidths=0,
        )
        for a in arrays:
            ax.scatter(a.xyz[:, i], a.xyz[:, j], s=14, c=a.color, zorder=3)
        ax.set_xlim(proj_centre[i] - proj_half, proj_centre[i] + proj_half)
        ax.set_ylim(proj_centre[j] - proj_half, proj_centre[j] + proj_half)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
        set_extreme_ticks(ax, "xy")
        ax.set_xlabel(f"{axis_labels[i]} (μm)")
        ax.set_ylabel(f"{axis_labels[j]} (μm)")
        ax.set_title(f"{axis_labels[i]}{axis_labels[j]} plane")

    # Bottom row, left: 3D view (wider, left-aligned).
    ax3d = fig.add_subplot(gs[1, 0:threed_cols], projection="3d")
    ax3d.scatter(*soma_sample.T, s=soma_size, c="tab:gray", alpha=soma_alpha)
    for a in arrays:
        ax3d.scatter(*a.xyz.T, s=16, c=a.color, depthshade=False)
    shown_xyz = np.vstack([soma_sample, electrode_xyz])
    span = np.ptp(shown_xyz, axis=0)
    lo = np.floor((shown_xyz.min(axis=0) - 0.03 * span) / 100.0) * 100.0
    hi = np.ceil((shown_xyz.max(axis=0) + 0.03 * span) / 100.0) * 100.0
    ax3d.set_xlim(lo[0], hi[0])
    ax3d.set_ylim(lo[1], hi[1])
    ax3d.set_zlim(lo[2], hi[2])
    ax3d.set_box_aspect(hi - lo)
    ax3d.set_anchor("W")
    ax3d.view_init(elev=30, azim=-60)
    # Draw the Y axis on the top-left cube edge (matplotlib-internal axis placement).
    ax3d.yaxis._axinfo["juggled"] = (2, 1, 0)  # noqa: SLF001  # ty:ignore[unresolved-attribute]
    ax3d.set_xlabel("X (μm)")
    ax3d.set_ylabel("Y (μm)")
    ax3d.zaxis.set_rotate_label(False)
    ax3d.set_zlabel("Z (μm)", rotation=90)
    ax3d.tick_params(labelsize=8)
    set_extreme_ticks(ax3d, "xyz", edges=True)

    # Local-frame panels (packed above): show the two axes each array varies along most.
    for (grid_row, col_start, is_row_start), (h, v, h_axis, v_axis, a, h_half, v_pad, span) in zip(
        placements, locals_, strict=True
    ):
        ax = fig.add_subplot(gs[grid_row, col_start : col_start + span])
        ax.scatter(h, v, s=10, c=a.color)
        h_centre = 0.5 * (h.min() + h.max())
        ax.set_xlim(h_centre - h_half, h_centre + h_half)
        ax.set_ylim(v.min() - v_pad, v.max() + v_pad)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
        set_extreme_ticks(ax, "xy")
        ax.tick_params(labelsize=8)
        ax.tick_params(axis="x", labelrotation=90)
        ax.set_xlabel(f"local {axis_labels[h_axis]} (μm)")
        if is_row_start:
            ax.set_ylabel(f"local {axis_labels[v_axis]} (μm)")
        b = a.block
        ax.set_title(
            a.name
            + chr(10)
            + f"origin: {b.origin_x:.0f}, {b.origin_y:.0f}, {b.origin_z:.0f}"
            + chr(10)
            + f"dir: {b.direction_x:.2f}, {b.direction_y:.2f}, {b.direction_z:.2f}",
            fontsize=7,
        )

    fig.tight_layout()
    fig.subplots_adjust(hspace=0.3)
    return fig
