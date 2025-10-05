""""
Generate basic connectivity plots for all connectomes
Last updated 03.2025
Author: Daniela Egas Santander"""

import obi_one as obi
import os

# Path to store figures 
output_root="/Users/danielaegas/OneDrive - Open Brain Institute/Shared Documents - OBI - Scientific staff/Data/Circuits hardcoded/Figures"
# Path to load connectivity matrices 
input_root="/Users/danielaegas/OneDrive - Open Brain Institute/Shared Documents - OBI - Scientific staff/Data/Circuits hardcoded/ConnectivityMatrices"
# ConnectivityMatrices available
ConnectivityMatrices = [f for f in os.listdir(input_root) if os.path.isdir(os.path.join(input_root, f))]
print(f"There are {len(ConnectivityMatrices)} connectivity matrices to be analyazed")

basic_connectivity_plots_scan_config = obi.BasicConnectivityPlotsScanConfig(
                    initialize=obi.BasicConnectivityPlotsScanConfig.Initialize(
                        matrix_path=[obi.NamedPath(name=f"{circ_name}", path=f"{input_root}/{circ_name}/connectivity_matrix.h5") for circ_name in ConnectivityMatrices],
                        plot_formats=("png",), # sub-tuple of ('png', 'pdf', 'svg'), if not specified all are plotted
                        #plot_types=("nodes",) # sub-tuple of ('nodes', 'connectivity_global', 'connectivity_pathway'), if not specified all are plotted
                        )
                        )
grid_scan = obi.GridScanGenerationTask(form=basic_connectivity_plots_scan_config, output_root=output_root, coordinate_directory_option="VALUE")

grid_scan.execute(processing_method='run')