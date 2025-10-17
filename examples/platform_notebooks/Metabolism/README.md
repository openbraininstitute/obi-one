# Metabolism
Copyright (c) 2023- 2025 Blue Brain Project, EPFL

Authors: Polina Shichkova, Daniel Keller

Last modified: 1-29-2025

## Summary
This data-driven molecular model of the neuro-glia-vascular system allows exploration of the complex relationships between the aging brain, energy metabolism, blood flow, and neuronal activity. Comprising 16,800 interaction pathways, the model includes all key enzymes,transporters, metabolites, and circulatory factors vital for neuronal electrical activity. The simulation allows one to track the time evolution of metabolites in response to a pulse stimulus.

## Use
1. Download the analysis_notebook.ipynb notebook to your local machine.
2. Ensure that Julia version 1.6.6 is installed. This can either be done from the command line or by uncommenting the first code cell and running it from the notebook (by Ctrl+Enter or ⌘+Enter).
3. Add the packages listed in analysis_info.json requirements. The packages can also be installed by uncommenting the codeblock containing Pkg.add and running the cell from the notebook.
4. Run the notebook. Interactive checkbox sections allow one to select which species are plotted.
5. You can directly modify parameters and initial values of variables in the downloaded json files. The functions can also be adapted to your needs and run the simulations for your special version of the model.

## Publication
The related publication is: Polina Shichkova1, Jay Coggan, Lida Kanari, Elvis Boci, Cyrille Favreau, Stefano M. Antonel, Daniel Keller, and Henry Markram. "Breakdown and repair of the aging brain metabolic system" Frontiers in Science, February 2025.
