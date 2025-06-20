"""Simulation execution module for OBI-One.

This module provides functionality to run simulations using different backends
(BlueCelluLab, Neurodamus) based on the simulation requirements.
"""
import logging
import sys
from pathlib import Path
from typing import Optional, Union, List, Tuple, Dict, Any
import json
from neuron import h
import sys

# Configure root logger with WARNING level
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

from bluecellulab import CircuitSimulation
from pynwb import NWBFile, NWBHDF5IO
from pynwb.icephys import CurrentClampSeries, IntracellularElectrode
from datetime import datetime, timezone
import shutil
from typing import Literal
import uuid

# Type alias for simulator backends
SimulatorBackend = Literal["bluecellulab", "neurodamus"]

logger = logging.getLogger(__name__)


def run_bluecellulab(
    simulation_config: Union[str, Path],
    save_nwb: bool = False,
) -> None:
    """Run a simulation using BlueCelluLab backend.
    
    Args:
        simulation_config: Path to the simulation configuration file
        save_nwb: Whether to save results in NWB format.
    """
    logger = logging.getLogger(__name__)
    
    # Get MPI info using NEURON's ParallelContext
    h.nrnmpi_init()
    pc = h.ParallelContext()
    rank = int(pc.id())
    size = int(pc.nhost())
    
    if rank == 0:
        logger.info("Initializing BlueCelluLab simulation")
    
    # Load configuration using json
    with open(simulation_config) as f:
        simulation_config_data = json.load(f)
    
    # Get simulation parameters from config
    t_stop = simulation_config_data["run"]["tstop"]
    dt = simulation_config_data["run"]["dt"]
    
    # Get the directory of the simulation config
    sim_config_base_dir = Path(simulation_config).parent
    print("sim_config_base_dir", sim_config_base_dir)
    # Get manifest path
    manifest_sim = simulation_config_data.get("manifest", {}).get("$OUTPUT_DIR", "./")
    print("manifest_sim", manifest_sim)
    # Get the node_set
    node_set_name = simulation_config_data.get("node_set", "All")
    
    # # Get the circuit config
    # circuit_config_file = simulation_config_data["network"]
    
    # Load node sets
    # with open(sim_config_base_dir / manifest_sim / circuit_config_file) as f:
    #     circuit_config_data = json.load(f)
    
    node_sets_file = sim_config_base_dir / manifest_sim / simulation_config_data["node_sets_file"]
    print("node_sets_file", node_sets_file)
    
    with open(node_sets_file) as f:
        node_set_data = json.load(f)

    # Get population and node IDs
    population = node_set_data[node_set_name]["population"]
    all_node_ids = node_set_data[node_set_name]["node_id"]
    print("population", population)
    print("all_node_ids", all_node_ids)
    
    # Distribute nodes across ranks
    num_nodes = len(all_node_ids)
    nodes_per_rank = num_nodes // size
    remainder = num_nodes % size
    print("num_nodes", num_nodes)
    print("nodes_per_rank", nodes_per_rank)
    print("remainder", remainder)
    
    # Calculate start and end indices for this rank
    start_idx = rank * nodes_per_rank + min(rank, remainder)
    if rank < remainder:
        nodes_per_rank += 1
    end_idx = start_idx + nodes_per_rank
    print("start_idx", start_idx)
    print("end_idx", end_idx)
    # Get node IDs for this rank
    rank_node_ids = all_node_ids[start_idx:end_idx]
    print("rank_node_ids", rank_node_ids)
    # create cell_ids_for_this_rank
    cell_ids_for_this_rank = [(population, i) for i in rank_node_ids]
    logger.info(f"Rank {rank}: Handling {len(cell_ids_for_this_rank)} cells: {cell_ids_for_this_rank}")
    
    if rank == 0:
        logger.info(f"Running BlueCelluLab simulation with {size} MPI processes")
        logger.info(f"Total cells: {num_nodes}, Cells per rank: ~{num_nodes//size}")
        logger.info(f"Starting simulation: t_stop={t_stop}ms, dt={dt}ms")
    
    logger.info(f"Rank {rank}: Processing {len(rank_node_ids)} cells (IDs: {rank_node_ids[0]}...{rank_node_ids[-1] if rank_node_ids else 'None'})")
    
    # Create simulation
    sim = CircuitSimulation(simulation_config)


    
    try:
        # Instantiate cells on this rank
        # https://github.com/openbraininstitute/BlueCelluLab/blob/24e49003859571d3c01b943b4e3113a374ea1b80/bluecellulab/circuit_simulation.py#L128
        sim.instantiate_gids(cell_ids_for_this_rank, 
                            add_stimuli=True, 
                            add_synapses=True,
                            add_minis=True, #False
                            add_replay=True,
                            add_projections=True)
        
        # Run simulation
        sim.run(t_stop, dt, cvode=False)
        
        # Get time trace once for all cells
        time_ms = sim.get_time_trace()
        if time_ms is None:
            logger.error(f"Rank {rank}: Time trace is None, cannot proceed with saving.")
            return
            
        time_s = time_ms / 1000.0  # Convert ms to seconds
        
        # Get voltage traces for each cell on this rank
        results = {}
        for cell_id in cell_ids_for_this_rank:
            voltage = sim.get_voltage_trace(cell_id)
            if voltage is not None:
                # change the cell_id to be Population_ID format
                cell_id_key = f"{cell_id[0]}_{cell_id[1]}"
                results[cell_id_key] = {
                    'time': time_s.tolist(),  # Convert numpy array to list for serialization
                    'voltage': voltage.tolist(),
                    'unit': 'mV'
                }
        
        # Gather all results to rank 0
        gathered_results = pc.py_gather(results, 0)
        
        if rank == 0 and save_nwb:
            # Merge results from all ranks
            all_results = {}
            for rank_results in gathered_results:
                if rank_results:
                    all_results.update(rank_results)
            
            # Create output directory structure
            base_dir = Path(simulation_config).parent
            output_config = simulation_config_data.get("output", {})
            output_dir = Path(output_config.get("output_dir", "output"))
            
            # Create a timestamped directory for this run
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_output_dir = base_dir / output_dir / f"simulation_{timestamp}"
            
            # Ensure the directory exists
            run_output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Saving simulation results to: {run_output_dir}")
            
            # Save NWB file
            output_path = run_output_dir / "results.nwb"
            save_results_to_nwb(all_results, output_path)
            
            logger.info(f"Successfully saved results to {output_path}")
            
    except Exception as e:
        logger.error(f"Rank {rank} failed: {str(e)}")
        raise
    finally:
        # Ensure proper cleanup
        pc.barrier()
        if rank == 0:
            logger.info("Simulation completed")

def run_neurodamus(
    simulation_config: Union[str, Path],
    save_nwb: bool = False,
) -> Dict[str, Any]:
    """Run simulation using Neurodamus backend"""
    raise NotImplementedError(
        "Neurodamus backend is not yet implemented. "
        "Please use BlueCelluLab backend for now."
    )

def save_results_to_nwb(results: Dict[str, Any], output_path: Union[str, Path]):
    """Save simulation results to NWB format"""
    nwbfile = NWBFile(
        session_description=f'Small Microcircuit Simulation results',
        identifier=str(uuid.uuid4()),
        session_start_time=datetime.now(timezone.utc),
        experimenter='OBI User',
        lab='Virtual Lab',
        institution='OBI',
        experiment_description='Simulation results',
        session_id=f"sim_small_microcircuit"
    )
    
    # Add device and electrode
    device = nwbfile.create_device(
        name='SimulatedElectrode',
        description='Virtual electrode for simulation recording'
    )
    
    # Add voltage traces
    for cell_id, trace in results.items():
        electrode = IntracellularElectrode(
            name=f'electrode_{cell_id}',
            description=f'Simulated electrode for {cell_id}',
            device=device,
            location='soma',
            filtering='none'
        )
        nwbfile.add_icephys_electrode(electrode)
        
        # Convert time from ms to seconds for NWB
        time_s = trace["time"] / 1000.0
        voltage_v = trace["voltage"] / 1000.0  # Convert mV to V
        
        # Create current clamp series
        ics = CurrentClampSeries(
            name=f'voltage_{cell_id}',
            data=voltage_v,
            electrode=electrode,
            timestamps=time_s,
            gain=1.0,
            unit='volt',
            description=f'Voltage trace for {cell_id}'
        )
        nwbfile.add_acquisition(ics)
    
    # Save to file
    with NWBHDF5IO(str(output_path), 'w') as io:
        io.write(nwbfile)
    
    logger.info(f"Saved results to {output_path}")
