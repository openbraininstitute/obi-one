---
tags:
  - explore
  - launch-notebook
  - contribute-and-fix-data
  - build-ion-channel-model
  - single-cell-simulation
  - paired-neuron-simulation
  - circuit-simulation
  - neuron-skeletonization
  - virtual-labs
---

# OBI-one

OBI-one is a standardized library of workflows for biophysically-detailed brain modeling.

## Features

- **Database Integration**: Integration with a standardized cloud database for neuroscience and computational neuroscience through [entitysdk](https://github.com/openbraininstitute/entitysdk)
- **Provenance**: Standardized provenance of workflows
- **Parameter Scans**: Standardized parameter scans across different modeling workflows
- **API Service**: Corresponding OpenAPI schema and service generated from Pydantic

## Installation

### Pre-installation

```bash
brew install uv open-mpi boost cmake
```

### Virtual Environment

Create a virtual environment (registered as a Jupyter kernel):

```bash
make install
```

## Architecture

The package is split into **core/** and **scientific/** code.

### Core Components

- **[ScanConfig](obi_one/core/scan_config.py)**: Defines configurations for specific modeling use cases. A Form is composed of one or multiple Blocks, which define the parameterization of a use case.

- **[Block](obi_one/core/block.py)**: Defines a component of a ScanConfig. Blocks support the specification of parameters which should be scanned over in multi-dimensional parameter scans.

- **[Task](obi_one/core/task.py)**: Defines executable tasks that operate on configurations.

- **[ScanGenerationTask](obi_one/core/scan_generation.py)**: Takes a single ScanConfig as input, an output path, and generates multi-dimensional parameter scans.

## FastAPI Service

Launch the FastAPI service with docs viewable at: http://127.0.0.1:8100/docs

```bash
make run-local
```

## Examples

Notebooks are available in the [examples/](../examples/) directory.

## Documentation

- [Single Cell Simulations](scs.md) - Learn about single cell simulation workflows
- [Small Circuit Simulations](scircuit.md) - Learn about small circuit simulation workflows
