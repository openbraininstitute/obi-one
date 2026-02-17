1. Download the sims using [download_sim_campaigns.ipynb](download_sim_campaigns.ipynb)
    - Stop the download once you have the spike files. We don't need the soma reports for now.
2. Download the circuit without the edges file using [download_circuit_without_edges.ipynb](download_circuit_without_edges.ipynb)
3. Convert the simulations to sonata using [blue_config_sims_to_sonata.ipynb](blue_config_sims_to_sonata.ipynb). This:
    - Creates the sonata simulation configs
4. Convert input spikes using [convert_input_spikes.ipynb](convert_input_spikes.ipynb)
    1) First convert input spike files from .dat to .h5
    2) Split input spike files into two population input spike files
    3) Create new output spike file with "S1nonbarrel_neurons" name
    4) Remap output spikes to correct gids
    5) TODO: Remap input spikes of both files
5. Download circuit without edges using [download_circuit_without_edges.ipynb](download_circuit_without_edges.ipynb)
6. Register campaign using [register_sim_campaigns.ipynb](register_sim_campaigns.ipynb)



