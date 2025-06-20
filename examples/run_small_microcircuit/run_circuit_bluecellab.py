import argparse
import json
import os
import logging
import time
from pathlib import Path
from matplotlib import pyplot as plt
import seaborn as sns
sns.set_style("white")
from neuron import h  # For MPI parallel context
from datetime import datetime, timezone
import uuid # For nwb file writing
from pynwb import NWBFile, NWBHDF5IO
from pynwb.icephys import CurrentClampSeries, IntracellularElectrode
from bluecellulab import CircuitSimulation
import numpy as np


def run_simulation_sonata(simulation_config, cell_ids, pc, rank, logger):
    # To disable HDF5 file locking to prevent BlockingIOError
    os.environ['HDF5_USE_FILE_LOCKING'] = 'FALSE'
    
    # Get the circuit folder name from the simulation_config path
    # This assumes the simulation_config is structured as "circuit_folder/simulation_config.json"
    circuit_folder_name = str(simulation_config).split("/")[0]
    logger.info(f"Rank {rank}: Determined circuit folder name: {circuit_folder_name}")
    # Create a results directory based on the circuit folder name
    # This will create a directory named "results/circuit_folder_name"
    results_dir = f"results/{circuit_folder_name}"
    # Create the results directory if it doesn't exist
    
    if rank == 0:
        os.makedirs(results_dir, exist_ok=True)
        logger.info(f"Rank 0: Ensured results directory exists: {results_dir}")
    pc.barrier() # Ensure directory is created by rank 0 before other ranks might proceed

    # Load the simulation configuration
    with open(simulation_config) as f:
        simulation_config_dict = json.load(f)

    sim = CircuitSimulation(simulation_config)
    logger.info(f"Rank {rank}: CircuitSimulation object created for {simulation_config}")

    # instantiate_gids() supports several arguments which can used for circuit
    # instantiation. Here, we are adding stimuli from simulation_config.json 
    # and activating synapses to the cells given by gids.
    sim.instantiate_gids(cell_ids, add_stimuli=True, add_synapses=True)
    logger.info(f"Rank {rank}: Cells instantiated for simulation: {cell_ids}")

    t_stop = simulation_config_dict["run"]['tstop']
    dt = simulation_config_dict["run"]['dt']

    logger.info(f"Rank {rank}: Starting simulation run for t_stop = {t_stop} ms, dt = {dt} ms.")
    sim_run_start_time = time.perf_counter()
    sim.run(t_stop=t_stop)
    sim_run_end_time = time.perf_counter()
    logger.info(f"Rank {rank}: Simulation run completed in {sim_run_end_time - sim_run_start_time:.2f} seconds.")


    # Plotting and saving should be done by a single rank (e.g., rank 0)
    # to avoid file overwriting and manage resources.
    if rank == 0:

        plotting_start_time = time.perf_counter()
        # --- Plotting ---
        logger.info(f"Rank 0: Generating plot for {len(cell_ids)} cells...")
        # Create subplots; handle single cell case for axs indexing robustly
        if not cell_ids:
            logger.warning("Rank 0: No cells to plot.")
            plotting_end_time = time.perf_counter()
            logger.info(f"Rank 0: Plotting took {plotting_end_time - plotting_start_time:.2f} seconds (no cells).")
            return

        fig, axs_list = plt.subplots(len(cell_ids), 1, figsize=(10, 6 * len(cell_ids)), squeeze=False)
        axs_list = axs_list.flatten()  # Ensure axs_list is a flat array of axes

        # Get the time array once for both plotting and NWB saving.
        time_ms = sim.get_time_trace() # Assumes rank 0 can get the global time trace
        if time_ms is None:
            logger.error("Rank 0: Error - Time trace is None. Cannot plot or save NWB.")
            plotting_end_time = time.perf_counter()
            logger.info(f"Rank 0: Plotting took {plotting_end_time - plotting_start_time:.2f} seconds (time trace error).")
            return

        for i, cid_tuple in enumerate(cell_ids):
            voltage_mv = sim.get_voltage_trace(cid_tuple)  # Get the voltage trace for the specific cell ID
            if voltage_mv is not None:  # Plot if voltage data is available
                axs_list[i].plot(time_ms, voltage_mv, label=str(cid_tuple))
                # save the time and voltage in a dat file
                dat_filename = f"{results_dir}/voltage_{cid_tuple[0]}_{cid_tuple[1]}.dat"
                try:
                    np.savetxt(dat_filename, np.column_stack((time_ms, voltage_mv)), header="Time (ms) Voltage (mV)", fmt="%s")
                    logger.info(f"Rank 0: Saved .dat file for {cid_tuple} to {dat_filename}")
                except Exception as e:
                    logger.error(f"Rank 0: Failed to save .dat file for {cid_tuple} to {dat_filename}: {e}")
            else:
                logger.warning(f"Rank 0: No voltage trace found for {cid_tuple} for plotting or .dat saving.")

            axs_list[i].set_xlabel("Time (ms)")
            axs_list[i].set_ylabel("Voltage (mV)")
            axs_list[i].legend()
            axs_list[i].set_title(f"Voltage Trace for Cell {cid_tuple[0]} GID {cid_tuple[1]}")
            axs_list[i].grid()
        plt.tight_layout()
        
        plot_filename = f"{results_dir}/{circuit_folder_name}.png"
        plt.savefig(plot_filename, dpi=300, bbox_inches='tight', facecolor='w')
        plt.close(fig)
        logger.info(f"Rank 0: Saved plot for {len(cell_ids)} cells to {plot_filename}")
        plotting_end_time = time.perf_counter()
        logger.info(f"Rank 0: Plotting took {plotting_end_time - plotting_start_time:.2f} seconds.")

        nwb_saving_start_time = time.perf_counter()
        # --- NWB Saving ---
        if not cell_ids: # This check is somewhat redundant due to earlier return, but good for clarity
            logger.warning("Rank 0: No cell data to save to NWB (should have been caught earlier).")
            nwb_saving_end_time = time.perf_counter()
            logger.info(f"Rank 0: NWB saving took {nwb_saving_end_time - nwb_saving_start_time:.2f} seconds (no cells).")
            return

        logger.info(f"Rank 0: Preparing to save {len(cell_ids)} cells to NWB file...")
        
        # Write the NWB file
        nwb_filename = f"{results_dir}/{circuit_folder_name}_num_cells={len(cell_ids)}.nwb"

        nwbfile = NWBFile(
            session_description=f'Circuit simulation for {len(cell_ids)} cells of {circuit_folder_name}. Config: {simulation_config.name if simulation_config else "N/A"}',
            identifier=str(uuid.uuid4()),
            session_start_time=datetime.now(timezone.utc),
            experimenter='OBI User',
            lab='My Virtual Lab',
            institution='My Institution',
            experiment_description=f'Simulated voltage traces for cells: {cell_ids}',
            session_id=f"sim_{circuit_folder_name}_{cell_ids[0][0]}_{cell_ids[0][1]}" if cell_ids else f"sim_{circuit_folder_name}_no_cells"
        )

        device = nwbfile.create_device(name='SimulatedIntracellularElectrode', description='Virtual electrode simulation.')

        # time_ms is already fetched above.
        # Ensure it's not None (already checked, but good practice if sections were more separate)
        if time_ms is not None:
            time_s = time_ms / 1000.0  # Convert ms to seconds

            for i, cid_tuple in enumerate(cell_ids):
                voltage_mv_nwb = sim.get_voltage_trace(cid_tuple) # Re-fetch or ensure data is gathered if needed
                if voltage_mv_nwb is not None:
                    voltage_v = voltage_mv_nwb / 1000.0 # Convert mV to Volts

                    intracellular_electrode = IntracellularElectrode(
                        name=f'electrode_{cid_tuple[0]}_{cid_tuple[1]}',
                        description=f'Simulated intracellular electrode for cell {cid_tuple[0]} GID {cid_tuple[1]}.',
                        device=device,
                        location='Soma',
                        filtering='none'
                    )
                    nwbfile.add_icephys_electrode(intracellular_electrode)

                    voltage_series = CurrentClampSeries(
                        name=f'Voltage_{cid_tuple[0]}_{cid_tuple[1]}',
                        data=voltage_v,
                        electrode=intracellular_electrode,
                        timestamps=time_s,
                        conversion=1.0,
                        resolution=-1.0,
                        comments=f"Population: {cid_tuple[0]}, GID: {cid_tuple[1]}.",
                        stimulus_description="A current stimulus was injected during the simulation (not saved as a separate NWB TimeSeries).",
                    )
                    nwbfile.add_acquisition(voltage_series)
                else:
                    logger.warning(f"Rank 0: No voltage trace found for {cid_tuple} for NWB saving, skipping NWB entry.")
        else:
            logger.error("Rank 0: Time trace is None, cannot save NWB data series.")

        with NWBHDF5IO(nwb_filename, "w") as io:
            io.write(nwbfile)
        logger.info(f"Rank 0: Saved NWB file to {nwb_filename}")
        nwb_saving_end_time = time.perf_counter()
        logger.info(f"Rank 0: NWB saving took {nwb_saving_end_time - nwb_saving_start_time:.2f} seconds.")

    pc.barrier() # Ensure all processes wait until rank 0 is done writing/plotting.
    logger.info(f"Rank {rank}: run_simulation_sonata finished.")


def main():
    # Initialize MPI and get rank/size
    h.nrnmpi_init()
    pc = h.ParallelContext()
    rank = int(pc.id())
    nhost = int(pc.nhost())

    # Setup logging
    logger = logging.getLogger(__name__) # Get logger for this module
    log_level = logging.INFO
    logger.setLevel(log_level)
    
    # StreamHandler for console output
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(log_level)
    log_format_str = "%(asctime)s - PID:%(process)d - %(levelname)s - %(message)s"
    if nhost > 1: # Add rank info if running in parallel
        log_format_str = f"[Rank {rank:02d}/{nhost:02d}] {log_format_str}"
    formatter = logging.Formatter(log_format_str)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    
    # Prevent duplicate logging if root logger also has handlers
    logger.propagate = False

    overall_start_time = time.perf_counter()
    logger.info("Starting run10cells_parallel.py script.")

    parser = argparse.ArgumentParser(description="Run BlueCelluLab SONATA simulation and save voltage plots.")
    parser.add_argument("--config", type=Path, help="Path to the simulation_config JSON file")
    parser.add_argument("--population_name", type=str, default="S1nonbarrel_neurons", help="Population name (default: S1nonbarrel_neurons)")
    parser.add_argument("--start_gid", type=int, default=0, help="Cell GID (default: 0)")
    parser.add_argument("--num_cells", type=int, default=1, help="Number of cells to simulate (default: 1)")
    args = parser.parse_args()
    logger.info(f"Parsed arguments: {args}")

    # Create logs directory if it doesn't exist (only by rank 0)
    logs_dir = Path("logs")
    if rank == 0:
        logs_dir.mkdir(parents=True, exist_ok=True)
    pc.barrier() # Ensure directory is created before other ranks proceed to create log files

    # FileHandler for rank-specific log files
    # Using circuit_folder_name in log file name for better organization if multiple circuits are run
    circuit_folder_name_for_log = "unknown_circuit"
    if args.config:
        try:
            circuit_folder_name_for_log = str(args.config).split("/")[0]
        except IndexError:
            pass # Keep default if path is not as expected

    # FileHandler for a central log file, written only by rank 0
    if rank == 0:
        log_file_path = logs_dir / f"{circuit_folder_name_for_log}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file_path, mode='w') # 'w' to overwrite
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter) # Use the same formatter
        logger.addHandler(file_handler)
        logger.info(f"Rank 0: Logging to central file: {log_file_path}")
    # All ranks (including 0) will still log to console via stream_handler

    cell_ids = [(args.population_name, args.start_gid + i) for i in range(args.num_cells)]
    logger.info(f"Target cell_ids for simulation: {cell_ids}")

    run_simulation_sonata(args.config, cell_ids, pc, rank, logger)

    pc.barrier() # Ensure all ranks have completed run_simulation_sonata
    overall_end_time = time.perf_counter()
    if rank == 0:
        logger.info(f"Total script execution time: {overall_end_time - overall_start_time:.2f} seconds.")


if __name__ == "__main__":
    main()