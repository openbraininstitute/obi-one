import numpy  # NOQA: ICN001
import pandas  # NOQA: ICN001
from matplotlib import pyplot as plt


def plot_mapping_stats(
    mapped_synapses_df: pandas.DataFrame,
    mesh_res: float,
    plt_max_dist: float = 3.0,
    nbins: int = 99,
) -> plt.Figure:
    dbins = numpy.linspace(0, plt_max_dist, nbins)
    w = numpy.mean(numpy.diff(dbins))

    frst_dist = numpy.maximum(mapped_synapses_df["distance"], 0.0)
    sec_dist = mapped_synapses_df["competing_distance"]

    fig = plt.figure(figsize=(2.5, 4))
    ax = fig.add_subplot(2, 1, 1)

    ax.bar(
        dbins[1:],
        numpy.histogram(frst_dist, bins=dbins)[0],
        width=w,
        label="Dist.: Nearest structure",
    )
    ax.bar(
        dbins[1:],
        numpy.histogram(sec_dist, bins=dbins)[0],
        width=w,
        label="Dist.: Second nearest structure",
    )
    ymx = ax.get_ylim()[1] * 0.85
    ax.plot([mesh_res, mesh_res], [0, ymx], color="black", label="Mesh resolution")
    ax.set_ylabel("Synapse count")
    ax.set_frame_on(False)
    plt.legend()
    return fig
