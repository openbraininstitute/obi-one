import logging
from pathlib import Path
from typing import Any

import matplotlib as mpl
import numpy as np

# Use non-interactive backend for matplotlib to avoid display issues
mpl.use("Agg")
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


def plot_voltage_traces(
    results: dict[str, Any], output_path: str | Path, max_cols: int = 3
) -> None:
    """Plot voltage traces for all cells in a grid of subplots and save to file.

    Args:
        results: Dictionary containing simulation results for each cell
        output_path: Path where to save the plot (should include .png extension)
        max_cols: Maximum number of columns in the subplot grid
    """
    plotted = []
    for cell_id, cell_result in results.items():
        voltage_key = None
        for rec_key, rec in cell_result.get("recordings", {}).items():
            if rec.get("variable_name") == "v":
                voltage_key = rec_key
                break

        if voltage_key is not None:
            plotted.append((cell_id, cell_result, voltage_key))

    n_cells = len(plotted)
    if n_cells == 0:
        logger.warning("No voltage traces to plot")
        return

    # Calculate grid size
    n_cols = min(max_cols, n_cells)
    n_rows = (n_cells + n_cols - 1) // n_cols

    # Create figure with subplots
    fig, axes = plt.subplots(
        n_rows, n_cols, figsize=(15, 3 * n_rows), squeeze=False, constrained_layout=True
    )

    # Flatten axes for easier iteration
    axes = axes.ravel()

    # Plot each cell's voltage trace in its own subplot
    for idx, (cell_id, cell_result, voltage_key) in enumerate(plotted):
        ax = axes[idx]
        time_s = np.asarray(cell_result["time"], dtype=float)
        time_ms = time_s * 1000.0
        voltage_mv = np.asarray(cell_result["recordings"][voltage_key]["values"], dtype=float)

        ax.plot(time_ms, voltage_mv, linewidth=1)
        ax.set_title(f"Cell {cell_id}", fontsize=10)
        ax.grid(visible=True, alpha=0.3)

        # Only label bottom row x-axes
        if idx >= (n_rows - 1) * n_cols:
            ax.set_xlabel("Time (ms)", fontsize=8)

        # Only label leftmost column y-axes
        if idx % n_cols == 0:
            ax.set_ylabel("mV", fontsize=8)

    # Turn off unused subplots
    for idx in range(n_cells, len(axes)):
        axes[idx].axis("off")

    # Add a main title
    fig.suptitle(f"Voltage Traces for {n_cells} Cells", fontsize=12)

    # Save the figure
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved voltage traces plot to %s", output_path)
