"""
Circuit Simulation Example with OBI-One
======================================

This script demonstrates how to run circuit simulations using the OBI-One simulation framework
with BlueCelluLab as the backend.
"""

import os
import logging
from pathlib import Path
from typing import List, Tuple, Optional

# Import the simulation framework
from obi_one.scientific.simulation.simulations import Simulation

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_simulation(
    circuit_config: str,
    output_dir: str = "output",
    dt: float = 0.025,  # ms
    cell_ids: Optional[List[Tuple[str, int]]] = None,
    simulator: str = "bluecellulab"
) -> None:
    """
    Run a circuit simulation with the given parameters.
    
    Args:
        circuit_config: Path to the circuit configuration file
        output_dir: Directory to save simulation results
        dt: Simulation timestep in milliseconds
        cell_ids: Optional list of (population, gid) tuples to simulate
        simulator: Simulator to use ('bluecellulab' or 'neurodamus')
    """
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Starting simulation with {simulator}")
    logger.info(f"Circuit config: {circuit_config}")
    logger.info(f"Output directory: {output_path.absolute()}")
    
    # Create and configure the simulation
    simulation = Simulation(
        circuit_config=circuit_config,
        dt=dt,
        output_dir=output_dir
    )
    
    # Generate the simulation configuration
    simulation.generate()
    
    # Run the simulation
    simulation.run(
        cell_ids=cell_ids,
        simulator=simulator,
        results_dir=output_dir
    )
    
    logger.info("Simulation completed successfully!")

if __name__ == "__main__":
    # Example usage
    # Replace these paths with your actual circuit configuration
    circuit_config = "path/to/your/circuit_config.json"
    output_dir = "simulation_results"
    
    # Optional: Specify specific cells to simulate
    # cell_ids = [("population_name", 1), ("population_name", 2)]
    
    run_simulation(
        circuit_config=circuit_config,
        output_dir=output_dir,
        cell_ids=None,  # Simulate all cells
        simulator="bluecellulab"
    )
