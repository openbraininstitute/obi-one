# OBI-ONE

OBI-ONE is a standardized library of workflows for biophysically-detailed brain modeling, with the following features:
- Integration with a standardized cloud database for neuroscience and computational neuroscience through [**entitysdk**](https://github.com/openbraininstitute/entitysdk).
- Standardized provenance of workflows.
- Standardized parameter scans across different modeling workflows.
- Corresponding OpenAPI schema and service generated from Pydantic.

<br>

# Examples
Example Jupyter notebooks are available in [**examples/**](examples/)

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

    - [**Block**](obi_one/core/block.py)s are the main components of ScanConfigs. Parameters in Blocks can be specified as single values or multiple values. Specifying multiple values for a parameter indicates that this parameter is a dimension of the parameter scan.

    - Currently ScanConfigs can have both single Blocks and dictionaries of Blocks. Each ScanConfig, for example, has its own Initialize Block for specifying the base parameters of the use case. Dictionaries of Blocks of a particular type are used where the ScanConfig can accept an unspecified number of this Block type, such as Stimulus Blocks.

- [**ScanGenerationTask**](obi_one/core/scan_generation_task.py) takes as input a ScanConfig and generates the coordinates of the parameter scan. OBI-ONE currently supports: 
    - [**GridScanGenerationTask**](obi_one/core/scan_generation_task.py)
    - [**CoupledScanGenerationTask**](obi_one/core/scan_generation_task.py)

- [**SingleConfig**](obi_one/core/single.py)s are created by a ScanGenerationTask for each coordinate in a parameter scan. SingleConfigs (i.e. [**CircuitSimulationSingleConfig**](obi_one/scientific/simulation/simulations.py)) inherit all parameters from a parent ScanConfig (i.e. [**CircuitSimulationScanConfig**](obi_one/scientific/simulation/simulations.py)), but a [**SingleConfigMixin**](obi_one/core/single.py) enforces that only single values are specified for each parameter. After generating the single coordinates, the 

- [**Task**](obi_one/core/task.py)s are where scientific code is defined, and are run for single points in a parameter space. For example, a CircuitSimulationGenerationTask might generate the SONATA simulation files for a single simulation in a parameter scan.

<br>


# FastAPI Service

Launch the FastAPI Service, with docs viewable at: http://127.0.0.1:8100/docs
```bash
make install-service
make run-local
```

<br>

# Documentation

OBI-ONE uses [MkDocs](https://www.mkdocs.org/) with the [Material theme](https://squidfunk.github.io/mkdocs-material/) for documentation.

## Installing Documentation Dependencies

To install the documentation dependencies (MkDocs and MkDocs Material) without affecting your existing dependencies:

```bash
make install-docs
```

This command uses `uv sync --group docs` to add only the documentation dependencies to your environment, ensuring that other installed packages remain unchanged.

## Serving Documentation Locally

To build and serve the documentation locally for preview:

```bash
make serve-docs
```

This will start a local development server (typically at `http://127.0.0.1:8000`) where you can preview the documentation. The server will automatically reload when you make changes to the documentation files.

## Tags

Tags are metadata used to link documentation `.md` files to products. Each documentation file should include appropriate tags in its frontmatter to categorize and organize content.

## Continuous Integration

The documentation is automatically checked in CI on pull requests. The `.github/workflows/check-docs.yml` workflow:

1. Checks if any files in the `docs/` directory have been modified in the pull request
2. If no documentation changes are detected, the check fails with an error message
3. You can skip this check by adding the `skip docs` label to your pull request

This ensures that documentation is updated alongside code changes. The check only runs on pull requests targeting `main` and can be bypassed with the `skip docs` label when documentation updates are not needed.

<br>

# Contributions
Please see [**CONTRIBUTING.md**](CONTRIBUTING.md) for guidelines on how to contribute.
 
# Acknowledgements
Copyright © 2025-2026 Open Brain Institute
