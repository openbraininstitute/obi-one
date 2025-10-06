"""Basic functions to compute network stats and for plotting
Last modified 08.2025
Author: Daniela Egas Santander.
"""

import contextlib
import logging
from operator import itemgetter

import matplotlib.patches as mpatches

# Matplotlib imports
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from conntility import ConnectivityMatrix
from matplotlib import gridspec
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Ellipse, FancyArrow
from matplotlib.ticker import FuncFormatter
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

with contextlib.suppress(ImportError):  # Try to import connalysis
    from connalysis.network.classic import connection_probability_within, density
    from connalysis.network.topology import node_degree, rc_submatrix

L = logging.getLogger(__name__)

# Stats functions


def connection_probability_pathway(
    conn: ConnectivityMatrix, grouping_prop: str
) -> pd.DataFrame:  # TODO: Add directly to connalysis?
    """Compute the connection probability of the matrix for a given grouping of the nodes."""

    def count_connections(mat: np.ndarray, *args) -> int:  # noqa: ARG001
        return mat.nnz

    def count_nodes(mat: np.ndarray, *args) -> tuple[int, ...]:  # noqa: ARG001
        return mat.shape

    # Setup analysis config per pathway
    analysis_specs = {
        "analyses": {
            "connection_counts": {
                "source": count_connections,
                "output": "scalar",
                "decorators": [
                    {
                        "name": "pathways_by_grouping_config",
                        "args": [{"columns": [grouping_prop], "method": "group_by_properties"}],
                    }
                ],
            },
            "node_counts": {
                "source": count_nodes,
                "output": "scalar",
                "decorators": [
                    {
                        "name": "pathways_by_grouping_config",
                        "args": [{"columns": [grouping_prop], "method": "group_by_properties"}],
                    }
                ],
            },
        }
    }
    out = conn.analyze(analysis_specs)

    # Compute connection probability
    df = out["node_counts"].unstack(f"idx-{grouping_prop}_post")  # noqa: PD010
    diag_values = np.diag(df.map(itemgetter(0)).to_numpy())
    diag = np.diag(diag_values)
    possible_connections = (df.map(lambda x: x[0] * x[1]) - diag).astype(int)
    connections = out["connection_counts"].unstack(f"idx-{grouping_prop}_post")  # noqa: PD010
    connection_prob = connections / possible_connections
    return connection_prob


def connection_probability_within_pathway(
    conn: ConnectivityMatrix, grouping_prop: str, max_dist: int = 100
) -> pd.DataFrame:
    """Compute the connection probability within `max_dist`
    and for a given grouping of the nodes.
    """
    # Setup analysis config per pathway
    analysis_specs = {
        "analyses": {
            "probability_within": {
                "source": connection_probability_within,
                "args": [
                    ["x", "y", "z"],
                    max_dist,
                    "directed",
                ],  # [["x_um", "y_um", "z_um"], max_dist, "directed"],
                "output": "scalar",
                "decorators": [
                    {
                        "name": "pathways_by_grouping_config",
                        "args": [{"columns": [grouping_prop], "method": "group_by_properties"}],
                    }
                ],
            }
        }
    }
    out = conn.analyze(analysis_specs)
    return out["probability_within"].unstack(f"idx-{grouping_prop}_post")  # noqa: PD010


def compute_global_connectivity(
    m: np.ndarray,
    m_er: np.ndarray,
    v: pd.DataFrame | None = None,
    connection_type: str = "full",
    max_dist: int = 100,
    cols: list[str] | None = None,
) -> np.ndarray:
    """Compute connection probabilities for the full network of with max_dist,
    and similarly for the control.
    """
    if "rc_submatrix" not in globals():
        msg = "Import of 'rc_submatrix' failed. You probably need to install connalysis locally."
        raise ValueError(msg)
    if cols is None:
        cols = ["x", "y"]
    if connection_type == "full":  # Compute on the entire network
        if "density" not in globals():
            msg = "Import of 'density' failed. You probably need to install connalysis locally."
            raise ValueError(msg)
        return np.array(
            [density(m), density(m_er), density(rc_submatrix(m)), density(rc_submatrix(m_er))]
        )
    if connection_type == "within":
        if "connection_probability_within" not in globals():
            msg = (
                "Import of 'connection_probability_within' failed. You probably need to install"
                " connalysis locally."
            )
            raise ValueError(msg)
        return np.array(
            [
                connection_probability_within(
                    m, v, max_dist=max_dist, cols=cols, type="directed", skip_symmetry_check=True
                ),
                connection_probability_within(
                    m_er, v, max_dist=max_dist, cols=cols, type="directed", skip_symmetry_check=True
                ),
                connection_probability_within(
                    rc_submatrix(m),
                    v,
                    max_dist=max_dist,
                    cols=cols,
                    type="directed",
                    skip_symmetry_check=True,
                ),
                connection_probability_within(
                    rc_submatrix(m_er),
                    v,
                    max_dist=max_dist,
                    cols=cols,
                    type="directed",
                    skip_symmetry_check=True,
                ),
            ]
        )
    msg = "Connection type not supported"
    raise ValueError(msg)


# Plotting functions


# Nodes
def make_pie_plot(  # noqa: PLR0914
    ax: plt.Axes, conn: ConnectivityMatrix, grouping_prop: str, cmaps: dict[str, plt.Colormap]
) -> plt.Axes:
    category_counts = conn.vertices[grouping_prop].value_counts()
    category_counts = category_counts[category_counts > 0]

    # Group categories with percentages ≤ 2% into "Other"
    total = category_counts.sum()
    percentages = (category_counts / total) * 100
    small_categories_threshold = 2
    small_categories = percentages[percentages <= small_categories_threshold].index
    if len(small_categories) > 1:
        other_count = category_counts[small_categories].sum()
        category_counts = category_counts.drop(small_categories)
        category_counts["Other"] = other_count

    # Define colors
    cmap = cmaps[grouping_prop]
    if grouping_prop == "synapse_class":
        # Fix red/blue for EXC/INH, if NA make it gray
        color_map = {"EXC": cmap(cmap.N), "INH": cmap(0), "NA": "gray"}
        colors = [color_map.get(key, cmap(i)) for i, key in enumerate(category_counts.index)]
    else:
        colors = [cmap(i) for i in range(len(category_counts))[::-1]]

    # Create the pie chart without percentages inside
    wedges, _ = ax.pie(category_counts, startangle=140, colors=colors, textprops={"fontsize": 8})

    # Add annotations outside the pie chart to avoid overlapping
    for i, wedge in enumerate(wedges):
        angle = (wedge.theta2 + wedge.theta1) / 2  # Midpoint angle of the wedge
        x = np.cos(np.radians(angle))  # X-coordinate for the label
        y = np.sin(np.radians(angle))  # Y-coordinate for the label
        extent = 1.4
        label_x = extent * x  # Position the label farther out
        label_y = extent * y
        ax.text(
            label_x,
            label_y,
            f"{category_counts.index[i]}: {percentages.iloc[i]:.1f}%",
            fontsize=8,
            ha="center",
            va="center",
        )

    # Adjust limits to ensure all labels are visible
    ax.set_xlim(-extent - 0.1, extent + 0.1)
    ax.set_ylim(-extent - 0.1, extent + 0.1)

    return ax


def plot_node_stats(
    conn: ConnectivityMatrix, cmaps: dict[str, plt.Colormap], full_width: int = 17
) -> plt.Figure:
    fig = plt.figure(figsize=(full_width, full_width // 3))
    gs = gridspec.GridSpec(2, 2, width_ratios=[1, 2.75])

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[:, 1])

    """Make plot of synapse class and mtype counts."""

    ax1.set_title("EI cell distribution")
    make_pie_plot(ax1, conn, "synapse_class", cmaps)
    ax2.set_title("Layer cell distribution")
    make_pie_plot(ax2, conn, "layer", cmaps)

    # mtype classes
    grouping_prop = "mtype"
    category_counts = conn.vertices[grouping_prop].value_counts()
    category_counts = category_counts[category_counts > 0]
    # Make bar chart
    cmap = cmaps[grouping_prop]
    category_counts.plot(kind="bar", color=cmap(cmap.N))
    ax3.set_xlabel("m-type")
    ax3.set_ylabel("Counts")
    ax3.set_title("m-type cell distribution")
    ax3.tick_params(axis="x", rotation=90)
    ax3.spines[["top", "right"]].set_visible(False)

    return fig


# Networks


def plot_degree(
    ax: plt.Axes, deg: pd.DataFrame, deg_er: pd.DataFrame, direction: str, hist_type: str = "full"
) -> plt.Axes:
    colors = ["teal", "lightgray"]
    for df, label, color in zip([deg, deg_er], ["Connectome", "ER control"], colors, strict=False):
        df_plot = df["IN"] + df["OUT"] if direction == "TOTAL" else df[direction]
        if hist_type == "full":
            ax.plot(df_plot.value_counts().sort_index(), label=label, color=color)
        elif hist_type == "hist":
            ax.hist(df_plot, alpha=0.5, label=label, color=color)
    return ax


def plot_global_connection_probability(
    ax1: plt.Axes, densities: np.ndarray
) -> tuple[plt.Axes, list[plt.Artist], list[str]]:
    # Connection probabilities
    colors = ["teal", "lightgrey", "teal", "lightgrey"]
    labels = ["Connectome", "ER control"]
    connectivity_label = ["Fulll", "Full", "Reciprocal", "Reciprocal"]
    hatches = ["", "", "//", "//"]  # Add stripes reciprocal connectivity

    # Plot full connectivity the primary y-axis
    bars1 = ax1.bar([0, 1], densities[:2], width=0.4, color=colors[:2])

    # Create a secondary y-axis
    ax2 = ax1.twinx()
    # Plot reciprocal connectivity on the secondary y-axis
    bars2 = ax2.bar([2, 3], densities[2:], width=0.4, color=colors[2:])
    # Add hatches to reicprocal connectivity
    for bar, hatch in zip(bars2, hatches[2:], strict=False):
        bar.set_hatch(hatch)

    # Add labels to each bar
    ax1.set_xticks([0, 1, 2, 3], labels=connectivity_label)
    ax1.set_frame_on(False)
    ax2.set_frame_on(False)
    for bar, label in zip(bars1 + bars2, labels, strict=False):
        height = bar.get_height()
        ax = ax1 if bar in bars1 else ax2
        ax.text(bar.get_x() + bar.get_width() / 2, height, label, ha="center", va="bottom")

    # Set labels and title
    ax1.set_ylabel("Connection probability")
    ax2.set_ylabel("Reciprocal connection probability", rotation=270, labelpad=20)
    ax1.ticklabel_format(style="scientific", axis="y", scilimits=(0, 0), useMathText=False)
    ax2.ticklabel_format(style="scientific", axis="y", scilimits=(0, 0), useMathText=False)
    ax1.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.1e}"))
    return ax1, bars1, labels


def plot_rc_connection(ax: plt.Axes, arrowsize: int = 20, node_size: int = 100) -> plt.Axes:
    # Create a directed graph
    g = nx.DiGraph()
    g.add_node(1)
    g.add_node(2)
    g.add_edge(1, 2)
    g.add_edge(2, 1)

    # Draw the graph with curved edges
    pos = nx.circular_layout(g)
    nx.draw(
        g,
        pos,
        with_labels=False,
        node_color="black",
        edge_color="black",
        arrows=True,
        arrowsize=arrowsize,
        node_size=node_size,
        connectionstyle="arc3,rad=0.2",
        ax=ax,
    )
    return ax


def plot_in_out_deg(
    ax: plt.Axes,
    direction: str,
    node_size: int = 10,
    head_width: float = 0.1,
    head_length: float = 0.1,
    buffer: float = 0.85,
) -> plt.Axes:
    # Plot the central node
    ax.plot(0, 0, "ko", markersize=node_size)

    # Plot the arrows
    for i in range(5):
        angle = i * (360 / 5)
        x = 1.5 * np.cos(np.radians(angle))
        y = 1.5 * np.sin(np.radians(angle))
        if direction == "in":
            ax.arrow(
                x,
                y,
                -buffer * x,
                -buffer * y,
                head_width=head_width,
                head_length=head_length,
                fc="k",
                ec="k",
            )
        elif direction == "out":
            ax.arrow(
                0,
                0,
                buffer * x,
                buffer * y,
                head_width=head_width,
                head_length=head_length,
                fc="k",
                ec="k",
            )

    # Set the limits and aspect ratio
    ax.set_xlim(-2, 2)
    ax.set_ylim(-2, 2)
    ax.set_aspect("equal")
    ax.set_axis_off()
    return ax


def imshow_wrapper(
    ax: plt.Axes, img: np.ndarray, cutoff: int = 225, perc: float = 97.5, **kwargs
) -> tuple[plt.Axes, plt.Axes]:
    if np.prod(img.shape) > cutoff:
        kwargs.update(
            {
                "clim": [
                    0.0,
                    np.percentile(img.to_numpy().ravel()[~np.isnan(img.to_numpy().ravel())], perc),
                ]
            }
        )
    plot = ax.imshow(img, **kwargs)
    return ax, plot


def plot_connection_probability_pathway(
    ax: plt.Axes,
    connection_prob: pd.DataFrame,
    cmap: str,
    cutoff: int = 15 * 15,
    perc: float = 97.5,
    **kwargs,
) -> tuple[plt.Axes, plt.Axes]:
    ax, plot = imshow_wrapper(ax, connection_prob, cutoff=cutoff, perc=perc, cmap=cmap, **kwargs)
    ax.set_yticks(range(len(connection_prob)), labels=connection_prob.index)
    ax.set_xticks(range(len(connection_prob)), labels=connection_prob.index)
    return ax, plot


def plot_connection_probability_stats(
    full_width: int, global_conn_probs: dict[str, np.ndarray]
) -> plt.Figure:
    fig, axs = plt.subplots(
        1,
        5,
        figsize=(full_width, full_width // 3),
        gridspec_kw={"width_ratios": [1, 0.2, 1, 0.2, 0.6]},
    )
    axs[0].set_title("Connection probabilities overall", y=1.1, fontsize=14)
    axs[2].set_title("Connection probabilities within 100um", y=1.1, fontsize=14)

    # Global connection probabilities
    axs[0], bars, labels = plot_global_connection_probability(axs[0], global_conn_probs["full"])
    axs[2], bars, labels = plot_global_connection_probability(axs[2], global_conn_probs["widthin"])

    # Cartoons and labels
    ax = axs[4]
    inset_ax1 = inset_axes(ax, width="100%", height="20%", loc="upper left")
    inset_ax2 = inset_axes(
        ax,
        width="100%",
        height="40%",
        loc="center",
        bbox_to_anchor=(0.2, 0.2, 0.6, 0.8),
        bbox_transform=ax.transAxes,
    )
    inset_ax3 = inset_axes(ax, width="50%", height="50%", loc="lower left")
    inset_ax4 = inset_axes(ax, width="50%", height="50%", loc="lower right")

    ax.set_axis_off()  # Axis created just for white space

    inset_ax1.legend(
        bars, labels, frameon=False, ncol=2, loc="center"
    )  # , bbox_to_anchor=(0.25,1))
    inset_ax1.set_axis_off()  # Axis created just for white space

    plot_rc_connection(inset_ax2, arrowsize=20, node_size=60)
    inset_ax2.set_title("Reciprocal \nconnection", fontsize=10, y=0.7)

    plot_in_out_deg(
        inset_ax3, direction="in", node_size=10, head_width=0.3, head_length=0.3, buffer=0.6
    )
    inset_ax3.set_title("In-degree", fontsize=10, y=0.8)

    plot_in_out_deg(
        inset_ax4, direction="out", node_size=10, head_width=0.3, head_length=0.3, buffer=0.6
    )
    inset_ax4.set_title("Out-degree", fontsize=10, y=0.8)

    for ax in [axs[1], axs[3]]:
        ax.set_axis_off()  # Axes created just for white space

    return fig


def plot_connection_probability_pathway_stats(
    full_width: int,
    conn_probs: dict[str, dict[str, pd.DataFrame]],
    deg: pd.DataFrame,
    deg_er: pd.DataFrame,
) -> plt.Figure:
    fig, axs = plt.subplots(3, 3, figsize=(full_width, full_width))

    for j, connection_type in enumerate(["full", "within"]):
        title = (
            "Connection probabilty \nper pathway overall"
            if connection_type == "full"
            else "Connection probabilty \nper pathway within 100um"
        )
        axs[0, j].text(
            0.5, 1.2, title, fontsize=14, ha="center", va="bottom", transform=axs[0, j].transAxes
        )

        # Connection probability
        for i, grouping_prop in enumerate(["synapse_class", "layer", "mtype"]):
            plotme = conn_probs[connection_type][grouping_prop]
            axs[i, j], plot = plot_connection_probability_pathway(axs[i, j], plotme, cmap="viridis")
            cbar = plt.colorbar(
                plot, ax=axs[i, j], orientation="vertical", shrink=0.85, label="Probability"
            )
            cbar.ax.ticklabel_format(style="scientific", axis="y", scilimits=(0, 0))
            axs[i, j].set_xlabel("Post-synaptic cell")
            axs[i, j].set_ylabel("Pre-synaptic cell")
        axs[2, j].set_title("Pathway: m-type")
        axs[2, j].tick_params(labelbottom=False, labelleft=False)
        axs[1, j].set_title("Pathway: layer")
        axs[0, j].set_title("Pathway: synapse class")

    # Plot degree distributions
    axs[0, 2].text(
        0.5,
        1.1,
        "Degree distributions",
        fontsize=14,
        ha="center",
        va="bottom",
        transform=axs[0, 2].transAxes,
    )
    for i, direction in enumerate(["IN", "OUT", "TOTAL"], start=0):
        axs[i, 2] = plot_degree(axs[i, 2], deg, deg_er, direction, hist_type="full")
        axs[i, 2].set_xlabel(f"{direction.capitalize()}-degree")
        axs[i, 2].spines[["top", "right"]].set_visible(False)
        axs[i, 2].set_frame_on(False)
        axs[i, 2].set_ylabel("Count")
        axs[i, 2].legend(frameon=False)

    fig.subplots_adjust(wspace=0.3)
    return fig


# Plotting function for small microcircuits


def plot_smallMC_network_stats(  # noqa: PLR0914, PLR0915
    conn: ConnectivityMatrix,
    full_width: int,
    color_indeg: tuple | None = None,
    color_outdeg: tuple | None = None,
    color_strength: tuple | None = None,
    cmap_adj: plt.Colormap | None = None,
) -> plt.Figure:
    if "node_degree" not in globals():
        msg = "Import of 'node_degree' failed. You probably need to install connalysis locally."
        raise ValueError(msg)

    if color_indeg is None:
        color_indeg = plt.get_cmap("Set2")(0)
    if color_outdeg is None:
        color_outdeg = plt.get_cmap("Set2")(2)
    if color_strength is None:
        color_strength = plt.get_cmap("Set2")(1)
    if cmap_adj is None:
        cmap_adj = plt.get_cmap("viridis")
    fig, axs = plt.subplots(
        1, 3, figsize=(full_width, full_width // 3)
    )  # , gridspec_kw={"width_ratios": [1, 2]})
    adj = conn.matrix
    adj_plot = adj.toarray().astype(float)
    adj_plot[adj_plot == 0] = np.nan
    # Connectivity matrix
    min_val = int(np.nanmin(adj_plot[adj_plot > 0]))
    max_val = int(np.nanmax(adj_plot))
    plot = axs[0].imshow(
        adj_plot, cmap=cmap_adj, interpolation="nearest", aspect="auto", vmin=min_val, vmax=max_val
    )
    axs[0].xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    axs[0].yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    axs[0].set_xlabel("Target neuron ID")
    axs[0].set_ylabel("Source neuron ID")
    axs[0].set_title("Connectivity matrix")
    bbox = axs[0].get_position()
    cbar_height = 0.03  # Height of colorbar axis
    cbar_pad = 0.125  # Padding below the main axis (fraction of figure height)
    cbar_y = bbox.y0 - cbar_pad - cbar_height
    cax = fig.add_axes([bbox.x0, cbar_y, bbox.width, cbar_height])
    cbar = plt.colorbar(plot, cax=cax, orientation="horizontal", label="Synapse count")
    cbar.ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))

    # Synapse per connection
    unique_weights, counts = np.unique(adj.toarray(), return_counts=True)
    mask = unique_weights != 0
    unique_weights, counts = unique_weights[mask], counts[mask]
    axs[1].bar(unique_weights.astype(int), counts, color=color_strength)
    axs[1].xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    if unique_weights.size == 1:
        axs[1].set_xticks(unique_weights)  # Otherwise it gives non-integer x-ticks
    axs[1].set_xlabel("Synapses per connection")
    axs[1].set_ylabel("Count")
    axs[1].set_title("Connection strength")

    # Plot degrees
    degree = node_degree(adj, direction=("IN", "OUT"))
    bar_width = 0.4
    df = degree["IN"].value_counts().sort_index()
    axs[2].bar(
        df.index - bar_width / 2, df, width=bar_width, alpha=1, label="In degree", color=color_indeg
    )
    df = degree["OUT"].value_counts().sort_index()
    axs[2].bar(
        df.index + bar_width / 2,
        df,
        width=bar_width,
        alpha=1,
        label="Out degree",
        color=color_outdeg,
    )

    axs[2].xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    unique_degrees = np.unique(degree)
    unique_degrees = unique_degrees[unique_degrees != 0]
    if unique_degrees.size == 1:
        axs[2].set_xticks(unique_degrees)  # Otherwise it gives non-integer x-ticks

    axs[2].set_xlabel("Degree")
    axs[2].set_ylabel("Count")
    axs[2].set_title("Node degrees")

    # Put legend below, otherwise sometimes it's over the bars
    bbox = axs[2].get_position()
    legend_height = 0.03  # Matching more or less the cbar options
    legend_y = bbox.y0 - cbar_pad - cbar_height
    legend_ax = fig.add_axes([bbox.x0, legend_y, bbox.width, legend_height])
    handles, labels = axs[2].get_legend_handles_labels()
    legend_ax.legend(handles, labels, loc="center", frameon=False, ncol=2)
    legend_ax.axis("off")

    # Make axs[1] square
    axs[0].set_box_aspect(1)
    axs[1].set_box_aspect(1)

    for ax in axs[1:]:
        ax.spines[["top", "right"]].set_visible(False)

    return fig


def plot_growing_circles(
    fig: plt.Figure, ax: plt.Axes, radii: list[float], y1: float = 0.5, color: str = "black"
) -> plt.Axes:
    # Get axis aspect ratio to make circles instead of ellipses
    bbox = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
    width, height = bbox.width, bbox.height
    aspect = width / height

    # Make even spacing between circles
    total_circle_width = sum(2 * r for r in radii)
    n = len(radii)
    gap = (1 - total_circle_width) / (n + 1)
    # Compute x positions
    x1s = []
    x = gap + radii[0]
    for i in range(n):
        if i > 0:
            x += radii[i - 1] + radii[i] + gap
        x1s.append(x)

    # Plot circles
    for i in range(n):
        radius = radii[i]
        x1 = x1s[i]
        radius_x = radius
        radius_y = radius * aspect
        ellipse = Ellipse(
            (x1, y1), width=2 * radius_x, height=2 * radius_y, color=color, zorder=10, clip_on=False
        )
        ax.add_patch(ellipse)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_axis_off()

    return ax


def plot_growing_arrows(
    ax: plt.Axes,
    widths: list[float],
    head_widths: list[float],
    y1: float = 0.5,
    color: str = "black",
    length: float = 0.2,
    gap: float = 0.05,
) -> plt.Axes:
    n = len(widths)
    total_arrow_width = sum(length for _ in widths)
    total_gap = gap * (n + 1)
    total_width = total_arrow_width + total_gap
    start_x = (1 - total_width) / 2 + gap

    x1s = []
    x = start_x
    for _ in range(n):
        x1s.append(x)
        x += length + gap

    for i in range(n):
        ax.add_patch(
            FancyArrow(
                x1s[i],
                y1,
                length,
                0,
                width=widths[i] / 100,
                head_width=head_widths[i],
                head_length=length / 3,
                length_includes_head=True,
                color=color,
                zorder=10,
                clip_on=False,
            )
        )

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_axis_off()
    return ax


def plot_rc(ax: plt.Axes, arrowsize: int = 20, node_size: int = 100) -> plt.Axes:
    # Create graph
    g = nx.DiGraph()
    g.add_node(0)
    g.add_node(1)
    g.add_edge(0, 1)
    g.add_edge(1, 0)

    # Draw the graph with curved edges
    pos = y = 0.5
    x = 0.1
    pos = {0: (x, y), 1: (x + 0.5, y)}

    nx.draw(
        g,
        pos,
        with_labels=False,
        node_color="black",
        edge_color="black",
        arrows=True,
        arrowsize=arrowsize,
        node_size=node_size,
        connectionstyle="arc3,rad=0.2",
        ax=ax,
    )
    ax.set_box_aspect(1)
    return ax


def plot_small_network(  # noqa: C901, PLR0912, PLR0913, PLR0914
    ax: plt.Axes,
    conn: ConnectivityMatrix,
    node_color: str | list | None = None,
    edge_color: str | list | None = None,  # To choose color of nodes and edges
    # To choose colors of nodes and edges by property, overrides node_color and edge_color
    *,
    color_nodes_by_prop: bool = False,
    color_map_nodes: dict | None = None,
    color_property_nodes: str = "synapse_class",
    color_edges_by_prop: bool = False,
    color_map_edges: dict | None = None,
    color_property_edges: str = "synapse_class",
    color_edges_by: str = "pre",
    edge_weight_scale: int = 3,
    min_size: int = 300,
    max_size: int = 1500,
    title: str = "Title!",
    title_fontsize: int | None = None,
    projection: str = "xy",
    coord_names: list[str] | None = None,
    axis_fontsize: int | None = None,
) -> plt.Axes:
    if "node_degree" not in globals():
        msg = "Import of 'node_degree' failed. You probably need to install connalysis locally."
        raise ValueError(msg)

    if coord_names is None:
        coord_names = ["x", "y"]
    ax.set_title(title, fontsize=title_fontsize)

    g = nx.from_numpy_array(conn.matrix.toarray(), create_using=nx.DiGraph)

    # Choose position of neurons in 2D
    if projection == "xy":
        df = conn.vertices[coord_names]
        df["xy"] = df[coord_names].to_numpy().tolist()
        df = df.drop(columns=coord_names)
        pos = df.to_dict()["xy"]
    elif projection == "circular":  # Nodes in a circle
        pos = nx.circular_layout(g)
    elif projection == "shell":
        pos = nx.shell_layout(g)  # Nodes in concentric circles
    else:
        msg = (
            f"Projection type: {projection} not implemented. "
            "Choose from 'xy', 'circular', or 'shell'."
        )
        raise ValueError(msg)

    # Make edges proportional to weights
    weights = [g[u][v]["weight"] for u, v in g.edges()]
    widths = [w / max(weights) * edge_weight_scale for w in weights]  # normalize for plotting

    # Make nodes proportional to total degree
    total_degree = node_degree(conn.matrix.astype(bool).astype(int), direction=("IN", "OUT")).sum(
        axis=1
    )
    min_deg, max_deg = min(total_degree), max(total_degree)
    if max_deg > min_deg:
        node_sizes = [
            min_size + (deg - min_deg) / (max_deg - min_deg) * (max_size - min_size)
            for deg in total_degree
        ]
    else:
        node_sizes = [min_size for _ in total_degree]

    # Color nodes and edges (possibly by property type)
    if color_nodes_by_prop:
        node_colors = [
            color_map_nodes.get(key) for key in conn.vertices[color_property_nodes].to_numpy()
        ]
    else:
        node_colors = node_color
    if color_edges_by_prop:
        defining_colors = [
            color_map_edges.get(key) for key in conn.vertices[color_property_edges].to_numpy()
        ]
        if color_edges_by == "pre":
            edge_colors = [defining_colors[u] for u, v in g.edges()]
        elif color_edges_by == "post":
            edge_colors = [defining_colors[v] for u, v in g.edges()]
        else:
            msg = f"color_edges_by must be 'pre' or 'post', got {color_edges_by}."
            raise ValueError(msg)
    else:
        edge_colors = edge_color

    # Plot network
    nx.draw(
        g,
        pos,
        with_labels=True,
        node_color=node_colors,
        edge_color=edge_colors,
        arrows=True,
        width=widths,
        node_size=node_sizes,
        ax=ax,
    )

    if projection == "xy":
        # Add small axis to show it's a projection
        # Coordinates for the mini-axis (in axes fraction of full axis)
        x0, y0 = 0.0, 0.0
        dx, dy = 0.1, 0.1

        # X axis
        ax.annotate(
            "",
            xy=(x0 + dx, y0),
            xytext=(x0, y0),
            arrowprops={"arrowstyle": "->", "lw": 1, "color": "k"},
            xycoords="axes fraction",
        )
        ax.annotate(
            coord_names[0], xy=(x0 + dx, y0), xycoords="axes fraction", fontsize=axis_fontsize
        )

        # Y arrow
        ax.annotate(
            "",
            xy=(x0, y0 + dy),
            xytext=(x0, y0),
            arrowprops={"arrowstyle": "->", "lw": 1, "color": "black"},
            xycoords="axes fraction",
        )

        ax.annotate(
            coord_names[1], xy=(x0, y0 + dy), xycoords="axes fraction", fontsize=axis_fontsize
        )
    return ax


def make_MC_fig_template(  # noqa: PLR0914
    figsize: tuple[float, float],
    height_ratios: list[float] | None = None,
    width_ratios: list[float] | None = None,
    hspace_row1: float = 0.05,
    hspace_row2: float = 0.15,
    hspace_row3: float = 0.02,
    cartoon_gaps: float = 0.1,
    ax1_ratio: float = 0.5,
) -> tuple[plt.Figure, tuple[plt.Axes, ...]]:
    if height_ratios is None:
        height_ratios: list[float] = [1, 2, 1]
    if width_ratios is None:
        width_ratios: list[float] = [1, 1, 1]

    # Make template for figure of small MC network properties
    fig = plt.figure(figsize=figsize)

    # Define grid
    gs = GridSpec(
        3,
        3,  # rows, columns
        height_ratios=height_ratios,  # row heights
        width_ratios=width_ratios,  # columns, will be used per row
        figure=fig,
    )

    # First row, connectivity and cartoons
    row1_bottom = gs[0, 0].get_position(fig).y0
    row1_top = gs[0, 0].get_position(fig).y1
    row1_height = row1_top - row1_bottom
    row1_left = gs[0, 0].get_position(fig).x0
    row1_right = gs[0, 2].get_position(fig).x1
    row1_width = row1_right - row1_left

    # ax1: left part, connectivity values
    col_width = (row1_width - hspace_row1) * ax1_ratio

    ax1 = fig.add_axes([row1_left, row1_bottom, row1_left + col_width, row1_height])

    # ax2: right part, cartoons
    n_right = 3  # number of cartoons
    right_start = row1_left + col_width + hspace_row1
    col_width = (row1_right - right_start - 2 * cartoon_gaps) / n_right
    ax2_1 = fig.add_axes([right_start, row1_bottom, col_width, row1_height])
    ax2_2 = fig.add_axes(
        [right_start + col_width + cartoon_gaps, row1_bottom, col_width, row1_height]
    )
    ax2_3 = fig.add_axes(
        [right_start + 2 * (col_width + cartoon_gaps), row1_bottom, col_width, row1_height]
    )
    ax2 = (ax2_1, ax2_2, ax2_3)

    # Second row
    row2_bottom = gs[1, 0].get_position(fig).y0
    row2_top = gs[1, 0].get_position(fig).y1
    row2_height = row2_top - row2_bottom
    row2_left = gs[1, 0].get_position(fig).x0
    row2_right = gs[1, 2].get_position(fig).x1
    row2_width = row2_right - row2_left
    col2_width = (row2_width - hspace_row2) / 2

    ax3 = fig.add_axes([row2_left, row2_bottom, col2_width, row2_height])
    ax4 = fig.add_axes([row2_left + col2_width + hspace_row2, row2_bottom, col2_width, row2_height])

    # Third row
    row3_bottom = gs[2, 0].get_position(fig).y0
    row3_top = gs[2, 0].get_position(fig).y1
    row3_height = row3_top - row3_bottom
    row3_left = gs[2, 0].get_position(fig).x0
    row3_right = gs[2, 2].get_position(fig).x1
    row3_width = row3_right - row3_left
    col3_width = (row3_width - 2 * hspace_row3) / 3

    ax5 = fig.add_axes([row3_left, row3_bottom, col3_width, row3_height])
    ax6 = fig.add_axes([row3_left + col3_width + hspace_row3, row3_bottom, col3_width, row3_height])
    ax7 = fig.add_axes(
        [row3_left + 2 * (col3_width + hspace_row3), row3_bottom, col3_width / 2, row3_height]
    )
    ax8 = fig.add_axes(
        [
            row3_left + 2 * (col3_width + hspace_row3) + col3_width / 2,
            row3_bottom,
            col3_width / 2,
            row3_height,
        ]
    )

    return fig, (ax1, ax2, ax3, ax4, ax5, ax6, ax7, ax8)


def plot_smallMC(  # noqa: PLR0914
    conn: ConnectivityMatrix, cmap: plt.Colormap, full_width: int, textsize: int = 14
) -> plt.Figure:
    if "density" not in globals() or "rc_submatrix" not in globals():
        msg = (
            "Import of 'density' or 'rc_submatrix' failed. You probably need to install connalysis"
            " locally."
        )
        raise ValueError(msg)

    # Generate template for plot
    fig, axs = make_MC_fig_template(
        figsize=(full_width, full_width),
        height_ratios=[1, 3, 0.3],  # relative row heights
        width_ratios=[1, 1, 1],
        hspace_row1=0.15,
        hspace_row2=0.01,
        hspace_row3=0.01,  # hspaces between columns in each row (fraction)
        cartoon_gaps=0.01,  # gap between cartoons
        ax1_ratio=0.3,  # fraction of row width for ax1
    )

    ax1, ax2, ax3, ax4, ax5, ax6, ax7, ax8 = axs

    # Plot connection probability
    adj = conn.matrix.astype(bool).astype(int)
    x_pos = 0.05
    ax1.text(x_pos, 0.7, f"Connection probability: {density(adj):.2e}", fontsize=textsize)
    ax1.text(
        x_pos,
        0.3,
        f"Reciprocal connections (%): {density(rc_submatrix(adj)) * 100:.1f}%",
        fontsize=textsize,
    )
    ax1.set_axis_off()

    # Plot cartoons
    plot_rc(ax2[0], arrowsize=20, node_size=100)
    ax2[0].set_title("Reciprocal connection", fontsize=textsize, y=1)

    plot_in_out_deg(
        ax2[1], direction="in", node_size=10, head_width=0.3, head_length=0.3, buffer=0.6
    )
    ax2[1].set_title("In-degree", fontsize=textsize, y=1)

    plot_in_out_deg(
        ax2[2], direction="out", node_size=10, head_width=0.3, head_length=0.3, buffer=0.6
    )
    ax2[2].set_title("Out-degree", fontsize=textsize, y=1)

    # Network plots
    # Color nodes by synapse class
    color_map_nodes = {"INH": cmap(0), "EXC": cmap(cmap.N)}
    color_map_edges = {"INH": cmap(0), "EXC": cmap(cmap.N)}
    color_edges_by_prop = True
    color_property = "synapse_class"

    # Plot x-y projection
    projection, coord_names, title = "xy", ["x", "y"], "Node positions: in x-y projection"
    ax3 = plot_small_network(
        ax3,
        conn,
        color_nodes_by_prop=True,
        color_map_nodes=color_map_nodes,
        color_property_nodes=color_property,
        color_edges_by_prop=color_edges_by_prop,
        color_map_edges=color_map_edges,
        color_property_edges=color_property,
        color_edges_by="pre",
        edge_weight_scale=4,
        min_size=300,
        max_size=1500,
        projection=projection,
        coord_names=coord_names,
        axis_fontsize=textsize,
        title=title,
        title_fontsize=textsize,
    )

    # Plot circular projection
    projection, coord_names, title = "circular", None, "Node positions: circular"
    ax4 = plot_small_network(
        ax4,
        conn,
        color_nodes_by_prop=True,
        color_map_nodes=color_map_nodes,
        color_property_nodes=color_property,
        color_edges_by_prop=color_edges_by_prop,
        color_map_edges=color_map_edges,
        color_property_edges=color_property,
        color_edges_by="pre",
        edge_weight_scale=4,
        min_size=300,
        max_size=1500,
        projection=projection,
        coord_names=coord_names,
        axis_fontsize=textsize,
        title=title,
        title_fontsize=textsize,
    )

    # Node legends
    largest_radius = 0.1
    y_nodes = 0.75
    # INH
    color_map = {"INH": cmap(0), "EXC": cmap(cmap.N)}
    plot_growing_circles(fig, ax7, radii=[largest_radius], y1=y_nodes, color=color_map["EXC"][:-1])
    ax7.text(
        0.5,
        0.1,
        "Excitatory neuron",
        va="center",
        ha="center",
        fontsize=12,
        color=color_map["EXC"][:-1],
    )
    ax7.set_axis_off()
    # EXC
    plot_growing_circles(fig, ax8, radii=[largest_radius], y1=y_nodes, color=color_map["INH"][:-1])
    ax8.text(
        0.5,
        0.1,
        "Inhibitory neuron",
        va="center",
        ha="center",
        fontsize=12,
        color=color_map["INH"][:-1],
    )
    ax8.set_axis_off()
    # Node size
    plot_growing_circles(
        fig, ax6, radii=[largest_radius / 6, largest_radius / 3, largest_radius / 2], y1=0.75
    )
    ax6.text(
        0.5,
        0.1,
        "Node size represents in+out degree",
        va="center",
        ha="center",
        fontsize=14,
        color="black",
    )

    # Edge width legend
    plot_growing_arrows(
        ax5,
        widths=np.linspace(1, 12, 3),
        head_widths=[0.1, 0.2, 0.3],
        y1=0.75,
        color="black",
        length=0.2,
        gap=0.05,
    )
    ax5.text(
        0.5,
        0.1,
        "Edge thickness represents number of synapses",
        va="center",
        ha="center",
        fontsize=12,
        color="black",
    )
    return fig


def plot_node_table(  # noqa: PLR0914
    conn: ConnectivityMatrix,
    figsize: tuple[float, float],
    colors_cmap: str,  # name of discrete colormap from matplotlib
    colors_file: str | None = None,  # path to rgba colors file
    h_scale: float = 2.5,
    v_scale: float = 2.5,
) -> plt.Figure:
    """Plot a table of node properties with color coding."""
    # Get data frame of properties
    df = conn.vertices[["node_ids", "layer", "mtype"]]
    df = df.copy().rename(columns={"node_ids": "Neuron ID", "layer": "Layer", "mtype": "M-type"})
    df.insert(0, " ", [""] * len(df))  # Add empty column for circles

    # Get colors
    if colors_cmap != "custom":  # From color map
        colors = plt.get_cmap(colors_cmap)
        n = conn.matrix.shape[0]
        if not (hasattr(colors, "colors") and n <= colors.N):
            msg = (
                "The rendering color map must contain at least as many colors as there are neurons."
            )
            raise ValueError(msg)
        colors = [colors(i) for i in range(colors.N)]
    else:  # Load colors from file
        colors_df = pd.read_csv(colors_file, header=None)
        colors = [tuple(row) for row in colors_df.to_numpy()]
        if not len(colors) >= len(df):
            msg = (
                "The rendering color map must contain at least as many colors as there are neurons."
            )
            raise ValueError(msg)

    fig, ax = plt.subplots(figsize=figsize)
    ax.axis("off")
    ax.set_aspect("equal")

    table = ax.table(cellText=df.to_numpy(), colLabels=df.columns, loc="center", cellLoc="center")
    table.auto_set_font_size(value=False)
    table.set_fontsize(12)
    table.scale(h_scale, v_scale)

    fig.canvas.draw()  # Draw table

    # Add color coding from the rendered image
    for i in range(len(df)):
        cell = table[i + 1, 0]  # +1 for header row
        cell.get_text().set_text("")  # Remove text
        bbox = cell.get_window_extent(fig.canvas.get_renderer())
        inv = ax.transData.inverted()
        x0, y0 = inv.transform((bbox.x0, bbox.y0))
        x1, y1 = inv.transform((bbox.x1, bbox.y1))
        xc, yc = (x0 + x1) / 2, (y0 + y1) / 2
        radius = (y1 - y0) * 0.35
        circle = mpatches.Circle((xc, yc), radius, color=colors[i], zorder=10, clip_on=False)
        ax.add_patch(circle)

    return fig
