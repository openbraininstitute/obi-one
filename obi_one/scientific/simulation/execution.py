"""Simulation execution module for OBI-One.

This module provides functionality to run simulations using different backends
(BlueCelluLab, Neurodamus) based on the simulation requirements.
"""
import logging
import sys
from pathlib import Path
from typing import Literal, Optional, Union, List, Tuple, Dict, Any
import json
import os
from neuron import h
import sys

# Configure root logger with WARNING level
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Supported simulator backends
SimulatorBackend = Literal["bluecellulab", "neurodamus"]

# Configure BlueCelluLab's logger to propagate to root logger
bluecellulab_logger = logging.getLogger('bluecellulab')
bluecellulab_logger.propagate = True
bluecellulab_logger.setLevel(logging.INFO)

import numpy as np
from bluecellulab import CircuitSimulation
from pynwb import NWBFile, NWBHDF5IO
from pynwb.icephys import CurrentClampSeries, IntracellularElectrode
from datetime import datetime, timezone
import uuid
logger = logging.getLogger(__name__)

def run_simulation(
    simulation_config: Union[str, Path],
    cell_ids: Optional[List[Tuple[str, int]]] = None,
    simulator: SimulatorBackend = "bluecellulab",
    results_dir: Optional[Union[str, Path]] = None,
) -> None:
    """Run a simulation using the specified backend.

    Args:
        simulation_config: Path to the simulation configuration file
        cell_ids: Optional list of (population, gid) tuples for the cells to simulate.
                 If None (default), all cells in the circuit will be simulated.
                 Mainly used with BlueCelluLab backend.
        simulator: Which simulator to use ('bluecellulab' or 'neurodamus')
        results_dir: Directory to save results. If None, uses the directory
                   specified in the simulation config's manifest, or 'output' if not specified.
    """
    # Convert to lowercase for case-insensitive comparison
    simulator = simulator.lower()
    
    # Load the simulation config to check for output directory
    with open(simulation_config, 'r') as f:
        config = json.load(f)
    
    # Determine output directory - use provided dir, then check config, then default to './output'
    if results_dir is None:
        output_dir = config.get('manifest', {}).get('$OUTPUT_DIR', None)
        if output_dir is None or output_dir == '.':
            # Default to './output' in the same directory as the config file
            results_dir = Path(simulation_config).parent / 'output'
        else:
            results_dir = Path(simulation_config).parent / output_dir
    
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Output will be saved to: {results_dir.absolute()}")

    logger.info(f"Starting simulation with {simulator} backend")
    
    if simulator == "bluecellulab":
        _run_bluecellulab(
            simulation_config=simulation_config,
            cell_ids=cell_ids,
            results_dir=results_dir,
        )
    elif simulator == "neurodamus":
        _run_neurodamus(
            simulation_config=simulation_config,
            cell_ids=cell_ids,
            results_dir=results_dir,
        )
    else:
        raise ValueError(f"Unsupported backend: {simulator}")


def _run_bluecellulab(
    simulation_config: Union[str, Path],
    cell_ids: Optional[List[Tuple[str, int]]] = None,
    results_dir: Optional[Union[str, Path]] = None,
) -> None:
    """Run a simulation using BlueCelluLab backend.
    
    Args:
        simulation_config: Path to the simulation configuration file
        cell_ids: List of (population, gid) tuples to simulate
        results_dir: Directory to save results
    """
    logger = logging.getLogger(__name__)
    logger.info("Initializing BlueCelluLab simulation")
    
    # Load configuration using json instead of eval
    with open(simulation_config) as f:
        config = json.load(f)
    
    # Get MPI info using NEURON's ParallelContext
    h.nrnmpi_init()
    pc = h.ParallelContext()
    rank = int(pc.id())
    size = int(pc.nhost())
    
    # Setup logging
    if rank == 0:
        logger.info(f"Running BlueCelluLab simulation with {size} MPI processes")
        # Make sure output is flushed immediately in notebook environment
        sys.stdout.flush()
    
    # Create simulation
    sim = CircuitSimulation(simulation_config)
    
    # Run simulation
    t_stop = config["run"]["tstop"]
    dt = config["run"]["dt"]
    
    if rank == 0:
        logger.info(f"Starting simulation: t_stop={t_stop}ms, dt={dt}ms")
    
    # Distribute cells across MPI ranks
    cells_per_rank = len(cell_ids) // size
    rank_cell_ids = cell_ids[rank * cells_per_rank:(rank + 1) * cells_per_rank]
    
    # Instantiate cells on this rank
    sim.instantiate_gids(rank_cell_ids, add_stimuli=True, add_synapses=True)
    
    # Run simulation
    sim.run(t_stop=t_stop)


def _run_neurodamus(
    simulation_config: Union[str, Path],
    cell_ids: Optional[List[Tuple[str, int]]] = None,
    results_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run simulation using Neurodamus backend"""
    raise NotImplementedError(
        "Neurodamus backend is not yet implemented. "
        "Please use BlueCelluLab backend for now."
    )


def save_results_to_nwb(results: Dict[str, Any], output_path: Union[str, Path]):
    """Save simulation results to NWB format"""
    nwbfile = NWBFile(
        session_description=f'Simulation results from {results["metadata"]["backend"]}',
        identifier=str(uuid.uuid4()),
        session_start_time=datetime.now(timezone.utc),
        experimenter='OBI User',
        lab='Virtual Lab',
        institution='OBI',
        experiment_description='Simulation results',
        session_id=f"sim_{results['metadata']['backend']}"
    )
    
    # Add device and electrode
    device = nwbfile.create_device(
        name='SimulatedElectrode',
        description='Virtual electrode for simulation recording'
    )
    
    # Add voltage traces
    for cell_id, trace in results.get("voltage_traces", {}).items():
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
