""""
Generate basic connectivity plots for all small connectomes
Last updated 06.2025
Author: Daniela Egas Santander"""

import numpy as np
import obi_one as obi

# List of all small circuits 
h = 0
volumetric = ([f"nbS1-O1-vSub-nCN-HEX{h}-L{l}-01" for l in np.arange(1,7)]+
              [f"nbS1-O1-vSub-sCN-HEX{h}-L{l}-01" for l in np.arange(1,7)])
simplicial_dim2 = ([f"nbS1-O1-sSub-pre-dim2-nCN-HEX0-L{l}-01" for l in np.arange(1,7)]+
                   [f"nbS1-O1-sSub-post-dim2-nCN-HEX0-L{l}-01" for l in np.arange(1,7)]) 
simplicial_dim_max =["nbS1-O1-sSub-pre-dim4-nCN-HEX0-L2-01", 
                     "nbS1-O1-sSub-pre-dim4-nCN-HEX0-L3-01",
                     "nbS1-O1-sSub-pre-dim5-nCN-HEX0-L1-01",
                     "nbS1-O1-sSub-pre-dim5-nCN-HEX0-L4-01",
                     "nbS1-O1-sSub-pre-dim5-nCN-HEX0-L6-01",
                     "nbS1-O1-sSub-pre-dim6-nCN-HEX0-L5-01",
                     "nbS1-O1-sSub-post-dim5-nCN-HEX0-L1-01",
                     "nbS1-O1-sSub-post-dim5-nCN-HEX0-L4-01",
                     "nbS1-O1-sSub-post-dim5-nCN-HEX0-L5-01",
                     "nbS1-O1-sSub-post-dim6-nCN-HEX0-L2-01",
                     "nbS1-O1-sSub-post-dim6-nCN-HEX0-L3-01",
                     "nbS1-O1-sSub-post-dim6-nCN-HEX0-L6-01"]
pairs = ([f"nbS1-O1-PV2E-maxNsyn-HEX0-L{l}" for l in np.arange(2,7)]+
         [f"nbS1-O1-Sst2E-maxNsyn-HEX0-L{l}" for l in np.arange(2,7)]+
         [f"nbS1-O1-E2PV-maxNsyn-HEX0-L{l}" for l in np.arange(2,7)]+
         [f"nbS1-O1-E2Sst-maxNsyn-HEX0-L{l}" for l in np.arange(2,7)]+
         [f"nbS1-O1-ErcPV-maxNsyn-HEX0-L{l}" for l in np.arange(2,7)]+
         [f"nbS1-O1-ErcSst-maxNsyn-HEX0-L{l}" for l in np.arange(2,7)])
hippocampus = [f"rCA1-CYLINDER-REF-1PC-8PV-{i:02d}" for i in np.arange(1,11)]

small_MCs= volumetric+simplicial_dim2+simplicial_dim_max+pairs+hippocampus
print(f"Generating figures for {len(small_MCs)} connectomes")


# Set up gridscan
root = "/Users/danielaegas/OneDrive - Open Brain Institute/Shared Documents - OBI - Scientific staff/Data/Circuits hardcoded/" 
matrix_path = [obi.NamedPath(name=circ_name, path=f"{root}ConnectivityMatrices/{circ_name}/connectivity_matrix.h5") for circ_name in small_MCs]
print(f"Generating figures for {len(matrix_path)} connectomes")


basic_connectivity_plots_scan_config = obi.BasicConnectivityPlotsScanConfig(initialize=obi.BasicConnectivityPlotsScanConfig.Initialize(
    matrix_path= matrix_path,
                 plot_formats=("png",),  # sub-tuple of ('png', 'pdf', a'svg'), if not specified all are plotted
                 plot_types=("nodes", "small_adj_and_stats","network_in_2D", "property_table",), 
                 # dpi=int default 300
                rendering_cmap = "tab10",
                # rendering_cmap = "custom", # Choose this is colors are given from a user defined file, otherwise use a discrete maplotlib color map as ``tab10§§
                # rendering_color_file = 'colors_tab10.csv' # path to colors with node identifiers for each node
                 )
                 )
grid_scan = obi.GridScanGenerationTask(form=basic_connectivity_plots_scan_config, output_root=f"{root}Figures", coordinate_directory_option="VALUE")

# Run
grid_scan.execute(processing_method='run')

print("Done")