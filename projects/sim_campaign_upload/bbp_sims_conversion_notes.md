1. Download the sims using [download/download_sim_campaigns.ipynb](download/download_sim_campaigns.ipynb)
    - Stop the download once you have the spike files. We don't need the soma reports for now.
    - For the spike sorting dataset the command which ignores the extracellular ("lfp") files is in the notebook
    - For spike sorting cylindrical target available at: https://drive.google.com/file/d/16N_fryCWC-GVxWasThxn2fBi_VHANnop/view?usp=sharing
2. Download the circuit without the edges file using [download/download_circuit_without_edges.ipynb](download/download_circuit_without_edges.ipynb)
3. Convert the simulations to sonata using [convert/blue_config_sims_to_sonata.ipynb](convert/blue_config_sims_to_sonata.ipynb). This:
    - Creates the sonata simulation configs
4. Convert input spikes using [convert/convert_input_spikes.ipynb](convert/convert_input_spikes.ipynb)
    1) First convert input spike files from .dat to .h5
    2) Split input spike files into two population input spike files
    3) Create new output spike file with "S1nonbarrel_neurons" name
    4) Remap output spikes to correct gids
    5) TODO: Remap input spikes of both files
5. Download circuit without edges using [download/download_circuit_without_edges.ipynb](download/download_circuit_without_edges.ipynb)
6. Register campaign using [upload/register_sim_campaigns.ipynb](upload/register_sim_campaigns.ipynb)





Spike sorting status
- IIRC: Campaign downloaded 

