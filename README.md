# OBI-ONE

OBI-ONE is a standardized library of workflows for biophysically-detailed brain modeling, with the following features:
- Integration with a standardized cloud database for neuroscience and computational neuroscience through [**entitysdk**](https://github.com/openbraininstitute/entitysdk).
- Standardized provenance of workflows.
- Standardized parameter scans across different modeling workflows.
- Corresponding OpenAPI schema and service generated from Pydantic.

<br>

# Installation

## For Most Users (Default)

```bash
# Install core + science dependencies
make install
```

This installs everything needed for running tasks and data processing scripts.

## For Development (Full Setup)

```bash
# Install all dependencies + dev tools
make install-dev
```

This installs everything needed for development: all optional dependencies + dev tools (pytest, ruff, etc.).

## For Specific Use Cases

```bash
# Service deployment
make install-service

# Notebook development
make install-notebooks

# Production build (all deps, no dev tools)
make install-all
```


## Pre-installation Requirements

```bash
brew install uv open-mpi boost cmake
```

<br>


# Examples
Notebooks are available in [**examples/**](examples/)
Remember to install notebook dependencies with
```bash
make install-notebooks
```

<br>


# Technical Overview / Glossary

The package is split into [**core/**](obi_one/core/) and [**scientific/**](obi_one/scientific/) code.

[**core/**](obi_one/core/) defines the following key classes:

- [**ScanConfig**](obi_one/core/scan_config.py): defines configurations for specific modeling use cases such as a [CircuitSimulationScanConfig](obi_one/scientific/tasks/generate_simulations/config/circuit.py).  A Form is composed of one or multiple Blocks (see next), which define the parameterization of a use case. Currently Forms can have both single Blocks and dictionaries of Blocks. Each Form, for example, has its own Initialize Block for specifying the base parameters of the use case. Dictionaries of Blocks of a particular type are used where the Form can accept an unspecified number of this Block type, such as Stimulus Blocks.
- [**Block**](obi_one/core/block.py): defines a component of a ScanConfig. Blocks are the components which support the specification of parameters which should be scanned over in the multi-dimensional parameter scan. When using the Form (in a Jupyter Notebook for example). Any parameter which is specified as a list is used as a dimension of a multi-dimensional parameter scan when passed to a Scan object (see below).
- [**SingleConfig**](obi_one/core/single.py):
- [**Task**](obi_one/core/task.py):
- [**ScanGenerationTask**](obi_one/core/scan_generation.py): is an example task which takes a single ScanConfig as input, an output path and a string for specifying how output files should be stored. Then the function scan.execute() function can then be called which generates the multiple dimensional scan


<br>


# FastAPI Service

Launch the FastAPI Service, with docs viewable at: http://127.0.0.1:8100/docs
```bash
make install-service
make run-local
```
<br>

# Contributions
Please see [**CONTRIBUTING.md**](CONTRIBUTING.md) for guidelines on how to contribute.
 
# Acknowledgements
Copyright © 2025-2026 Open Brain Institute
