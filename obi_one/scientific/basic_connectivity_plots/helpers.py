"""Basic functions to compute network stats and for plotting
Last modified 03.2025 
Author: Daniela Egas Santander"""

import warnings

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from matplotlib import gridspec

try:
    from connalysis.network.classic import connection_probability_within, density
    from connalysis.network.topology import rc_submatrix
except ImportError:
    warnings.warn("Connectome functionalities not available", UserWarning, stacklevel=1)


### Stats functions 

def connection_probability_pathway(conn, grouping_prop): #TODO: Add directly to connalysis?
    """
    Compute the connection probability of the matrix for a given grouping of the nodes
    """
    def count_connections(mat, nrn):
        return mat.nnz
    def count_nodes(mat, nrn):
        return mat.shape

    # Setup analysis config per pathway
    analysis_specs = {
        "analyses":{
            "connection_counts": {
                "source": count_connections,
                "output": "scalar",
                "decorators": [
                    {
                        "name": "pathways_by_grouping_config",
                        "args": [{"columns": [grouping_prop], "method": "group_by_properties"}]
                    }
                ]
            },
            "node_counts": {
                "source": count_nodes,
                "output": "scalar",
                "decorators": [
                    {
                        "name": "pathways_by_grouping_config",
                        "args": [{"columns": [grouping_prop], "method": "group_by_properties"}]
                    }
                ]
            }
        }
    }
    out=conn.analyze(analysis_specs)

    # Compute connection probability
    df=out["node_counts"].unstack(f"idx-{grouping_prop}_post")
    diag=np.zeros(df.shape)
    np.fill_diagonal(diag, np.diag(df.map(lambda x: x[0]).to_numpy()))
    possible_connections=(df.map(lambda x: x[0]*x[1])-diag).astype(int)
    connections=out["connection_counts"].unstack(f"idx-{grouping_prop}_post")
    connection_prob=connections/possible_connections 
    return connection_prob

def connection_probability_within_pathway(conn, grouping_prop, max_dist=100): 
    """
    Compute the connection probability within `max_dist` and for a given grouping of the nodes
    """
    # Setup analysis config per pathway
    analysis_specs = {
        "analyses":{
            "probability_within": {
                "source": connection_probability_within,
                "args": [["x", "y", "z"], max_dist, "directed"], #[["x_um", "y_um", "z_um"], max_dist, "directed"],
                "output": "scalar",
                "decorators": [
                    {
                        "name": "pathways_by_grouping_config",
                        "args": [{"columns": [grouping_prop], "method": "group_by_properties"}]
                    }
                ]
            }
        }
    }
    out=conn.analyze(analysis_specs)
    return out['probability_within'].unstack(f"idx-{grouping_prop}_post")

def compute_global_connectivity(m, m_ER, v=None, type="full", max_dist=100, cols=["x", "y"],):
    """
    Compute connection probabilities for the full network of with max_dist and similarly for the control"""
    if type=="full": # Compute on the entire network 
        return np.array([density(m), density(m_ER), density(rc_submatrix(m)), density(rc_submatrix(m_ER))])
    elif type=="within": 
        return np.array([connection_probability_within(m, v, max_dist=max_dist, cols=cols, type='directed', skip_symmetry_check= True),
                         connection_probability_within(m_ER, v, max_dist=max_dist, cols=cols, type='directed', skip_symmetry_check= True),
                         connection_probability_within(rc_submatrix(m), v, max_dist=max_dist, cols=cols, type='directed', skip_symmetry_check= True),
                         connection_probability_within(rc_submatrix(m_ER), v, max_dist=max_dist, cols=cols, type='directed', skip_symmetry_check= True)])

### Plotting functions 

## Nodes
def make_pie_plot(ax, conn, grouping_prop, cmaps):
    category_counts = conn.vertices[grouping_prop].value_counts()
    category_counts = category_counts[category_counts > 0]
    
    # Group categories with percentages ≤ 2% into "Other"
    total = category_counts.sum()
    percentages = (category_counts / total) * 100
    small_categories = percentages[percentages <= 2].index
    if len(small_categories) > 1:
        other_count = category_counts[small_categories].sum()
        category_counts = category_counts.drop(small_categories)
        category_counts["Other"] = other_count
    
    # Define colors
    cmap = cmaps[grouping_prop]
    if grouping_prop == "synapse_class":
        # Fix red/blue for EXC/INH
        color_map = {"EXC": cmap(cmap.N), "INH": cmap(0)}
        colors = [color_map.get(key, cmap(i)) for i, key in enumerate(category_counts.index)]
    else:
        colors = [cmap(i) for i in range(len(category_counts))[::-1]]
    
    # Create the pie chart without percentages inside
    wedges, _ = ax.pie(
        category_counts, startangle=140, colors=colors, textprops={'fontsize': 8}
    )
    
    # Add annotations outside the pie chart to avoid overlapping
    for i, wedge in enumerate(wedges):
        angle = (wedge.theta2 + wedge.theta1) / 2  # Midpoint angle of the wedge
        x = np.cos(np.radians(angle))  # X-coordinate for the label
        y = np.sin(np.radians(angle))  # Y-coordinate for the label
        extent = 1.4
        label_x = extent * x  # Position the label farther out
        label_y = extent * y
        ax.text(
            label_x, label_y,
            f"{category_counts.index[i]}: {percentages.iloc[i]:.1f}%",
            fontsize=8, ha='center', va='center'
        )
    
    # Adjust limits to ensure all labels are visible
    ax.set_xlim(-extent-0.1, extent+0.1)
    ax.set_ylim(-extent-0.1, extent+0.1)
    
    return ax

def plot_node_stats(conn,cmaps):
    fig  = plt.figure(figsize=(17, 5))
    gs = gridspec.GridSpec(2, 2, width_ratios=[1, 2.75])

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[:, 1])


    """Make plot of synapse class and mtype counts"""


    ax1.set_title('EI cell distribution')
    make_pie_plot(ax1, conn, "synapse_class",cmaps)
    ax2.set_title('Layer cell distribution')
    make_pie_plot(ax2, conn, "layer",cmaps)


    # mtype classes 
    grouping_prop="mtype"
    category_counts = conn.vertices[grouping_prop].value_counts()
    category_counts = category_counts[category_counts > 0]
    # Make bar chart
    cmap=cmaps[grouping_prop]
    category_counts.plot(kind='bar', color=cmap(cmap.N))
    ax3.set_xlabel('m-type')
    ax3.set_ylabel('Counts')
    ax3.set_title('m-type cell distribution')
    ax3.tick_params(axis='x', rotation=90)
    ax3.spines[["top", "right"]].set_visible(False)


    return fig

# Networks

def plot_degree(ax, deg, deg_ER, direction, type="full"):
    colors=["teal", "lightgray"]
    for df, label, color in zip([deg, deg_ER], ['Connectome', 'ER control'], colors):
        df=df['IN']+df['OUT'] if direction == "TOTAL" else df[direction]
        if type=="full":
            ax.plot(df.value_counts().sort_index(), label=label, color=color)
        elif type=="hist":
            ax.hist(df, alpha=0.5, label=label, color=color)    
    return ax

from mpl_toolkits.axes_grid1.inset_locator import inset_axes

def plot_global_connection_probability(ax1, densities):
    # Connection probabilities
    colors = ['teal', 'lightgrey', 'teal', 'lightgrey']
    labels = ['Connectome', 'ER control']
    connectivity_label = ['Fulll', 'Full', 'Reciprocal', 'Reciprocal']
    hatches = ['', '', '//', '//']  # Add stripes reciprocal connectivity

    
    # Plot full connectivity the primary y-axis
    bars1 = ax1.bar([0, 1], densities[:2], width=0.4, color=colors[:2])
    #ax1.legend(bars1, labels, frameon=False)

    # Create a secondary y-axis
    ax2 = ax1.twinx()
    # Plot reciprocal connectivity on the secondary y-axis
    bars2 = ax2.bar([2, 3], densities[2:], width=0.4, color=colors[2:])
    # Add hatches to reicprocal connectivity
    for bar, hatch in zip(bars2, hatches[2:]):
        bar.set_hatch(hatch)

    # Add labels to each bar
    ax1.set_xticks([0, 1, 2, 3], labels=connectivity_label)
    ax1.set_frame_on(False)
    ax2.set_frame_on(False)
    for bar, label in zip(bars1 + bars2, labels):
        #height = bar.get_height()
        #ax = ax1 if bar in bars1 else ax2
        #ax.text(bar.get_x() + bar.get_width() / 2, height, label, ha='center', va='bottom')
        pass

    # Set labels and title
    #ax1.set_xlabel('Categories')
    ax1.set_ylabel('Connection probability')
    ax2.set_ylabel('Reciprocal connection probability', rotation=270, labelpad=20)
    ax1.ticklabel_format(style='scientific', axis='y', scilimits=(0,0), useMathText=False)
    ax2.ticklabel_format(style='scientific', axis='y', scilimits=(0,0), useMathText=False)
    #ax1.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:.1e}'))
    print(bars1)
    return ax1, bars1, labels


def plot_rc_connetion(ax, arrowsize=20, node_size=100):
    # Create a directed graph
    G = nx.DiGraph()
    G.add_node(1)
    G.add_node(2)
    G.add_edge(1, 2)
    G.add_edge(2, 1)

    # Draw the graph with curved edges
    pos = nx.circular_layout(G)
    nx.draw(G, pos, with_labels=False, node_color='black', edge_color='black', arrows=True, 
            arrowsize=arrowsize, node_size=node_size,
            connectionstyle='arc3,rad=0.2', ax=ax)
    return ax
def plot_in_out_deg(ax, direction, node_size=10, head_width=0.1, head_length=0.1, buffer=0.85):

    # Plot the central node
    ax.plot(0, 0, 'ko', markersize=node_size)

    # Plot the arrows
    for i in range(5):
        angle = i * (360 / 5)
        x = 1.5 * np.cos(np.radians(angle))
        y = 1.5 * np.sin(np.radians(angle))
        if direction == 'in':
            ax.arrow(x, y, -buffer * x, -buffer * y, head_width=head_width, head_length=head_length, fc='k', ec='k')
        elif direction == 'out':
            ax.arrow(0, 0, buffer * x, buffer * y, head_width=head_width, head_length=head_length, fc='k', ec='k')

    # Set the limits and aspect ratio
    ax.set_xlim(-2, 2)
    ax.set_ylim(-2, 2)
    ax.set_aspect('equal')
    ax.set_axis_off()
    return ax 

def imshow_wrapper(ax, img, cutoff=15*15, perc=97.5, **kwargs):
    if np.prod(img.shape) > cutoff:
        kwargs.update({"clim": [0.0, np.percentile(img.values.ravel()[~np.isnan(img.values.ravel())], perc)]})
    plot=ax.imshow(img, **kwargs)
    return ax, plot

def plot_connection_probability_pathway(ax, connection_prob, cmap, cutoff=15*15, perc=97.5, **kwargs):
    ax, plot=imshow_wrapper(ax, connection_prob, cutoff=cutoff, perc=perc, cmap=cmap, **kwargs)
    ax.set_yticks(range(len(connection_prob)),labels= connection_prob.index)
    ax.set_xticks(range(len(connection_prob)),labels= connection_prob.index)
    return ax, plot

def plot_connection_probability_stats(full_width, global_conn_probs):
    fig, axs = plt.subplots(1,5, figsize=(full_width,full_width//3), gridspec_kw={'width_ratios': [1,0.2, 1,0.2, 0.6]})
    axs[0].set_title('Connection probabilities overall', y=1.1, fontsize=14)
    axs[2].set_title('Connection probabilities within 100um', y=1.1, fontsize=14)

    #Global connection probabilities 
    axs[0], bars, labels=plot_global_connection_probability(axs[0], global_conn_probs["full"])
    axs[2], bars, labels=plot_global_connection_probability(axs[2], global_conn_probs["widthin"])

    # Cartoons and labels
    ax=axs[4]
    inset_ax1 = inset_axes(ax, width="100%", height="20%", loc='upper left')
    inset_ax2 = inset_axes(ax, width="100%", height="40%", loc='center', bbox_to_anchor=(0.2, 0.2, 0.6, 0.8), bbox_transform=ax.transAxes)
    inset_ax3 = inset_axes(ax, width="50%", height="50%", loc='lower left')
    inset_ax4 = inset_axes(ax, width="50%", height="50%", loc='lower right')

    ax.set_axis_off() #Axis created just for white space

    inset_ax1.legend(bars, labels,frameon=False,ncol=2, loc="center")#, bbox_to_anchor=(0.25,1))
    inset_ax1.set_axis_off() #Axis created just for white space



    plot_rc_connetion(inset_ax2, arrowsize=20, node_size=60)
    inset_ax2.set_title('Reciprocal \nconnection', fontsize=10,y=0.7)

    plot_in_out_deg(inset_ax3, direction='in', node_size=10, head_width=0.3, head_length=0.3, buffer=0.6) 
    inset_ax3.set_title('In-degree', fontsize=10,y=0.8)

    plot_in_out_deg(inset_ax4, direction='out', node_size=10,head_width=0.3, head_length=0.3, buffer=0.6) 
    inset_ax4.set_title('Out-degree', fontsize=10,y=0.8)


    for ax in [axs[1], axs[3]]:
        ax.set_axis_off() #Axes created just for white space
    
    return fig

def plot_connection_probability_pathway_stats(full_width, conn_probs, deg, deg_ER):
    fig, axs = plt.subplots(3,3, figsize=(full_width,full_width))

    for j, connection_type in enumerate(["full", "within"]):
        title='Connection probabilty \nper pathway overall' if connection_type == "full" else 'Connection probabilty \nper pathway within 100um'
        axs[0, j].text(0.5, 1.2, title, fontsize=14,
                    ha='center', va='bottom', transform=axs[0, j].transAxes)

        # Connection probability 
        for i, grouping_prop in enumerate(["synapse_class","layer",  "mtype"]):
            plotme=conn_probs[connection_type][grouping_prop]
            axs[i,j],plot=plot_connection_probability_pathway(axs[i,j], plotme, cmap="viridis")
            cbar=plt.colorbar(plot, ax=axs[i,j], orientation="vertical", shrink=0.85, label="Probability")
            cbar.ax.ticklabel_format(style='scientific', axis='y', scilimits=(0,0))
            axs[i,j].set_xlabel("Post-synaptic cell")
            axs[i,j].set_ylabel("Pre-synaptic cell")
        axs[2,j].set_title("Pathway: m-type")
        axs[2,j].tick_params(labelbottom=False, labelleft=False)
        axs[1,j].set_title("Pathway: layer")
        axs[0,j].set_title("Pathway: synapse class")



    # Plot degree distributions
    axs[0, 2].text(0.5, 1.1, 'Degree distributions', fontsize=14,
                    ha='center', va='bottom', transform=axs[0, 2].transAxes)
    for i, direction in enumerate(['IN', 'OUT', 'TOTAL'], start=0):
        axs[i,2]=plot_degree(axs[i,2], deg, deg_ER, direction, type="full")
        axs[i,2].set_xlabel(f"{direction.capitalize()}-degree")
        axs[i,2].spines[["top", "right"]].set_visible(False)
        axs[i,2].set_frame_on(False)
        axs[i,2].set_ylabel("Count")
        axs[i,2].legend(frameon=False)   

    fig.subplots_adjust(wspace=0.3)
    return fig