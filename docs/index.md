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

# OBI-ONE

OBI-ONE is a standardized library of workflows for biophysically-detailed brain modeling.

## Features

- **Database Integration**: Integration with a standardized cloud database for neuroscience and computational neuroscience through [**entitysdk**](https://github.com/openbraininstitute/entitysdk).
- **Provenance**: Standardized provenance of workflows.
- **Parameter Scans**: Standardized parameter scans across different modeling workflows.
- **API Service**: Corresponding OpenAPI schema and service generated from Pydantic.

## Installation

### Pre-installation Requirements

```bash
brew install uv open-mpi boost cmake
```

### Private neuromorphomesh from AWS CodeArtifacts

Certain commands require the installation of `neuromorphomesh`.
At the OBI [AWS Console](https://openbraininstitute.awsapps.com/start), first check that you have access to the `Container Registry` (AWS Account Id: `985539765147`).

Then setup the the SSO AWS login; steps 1 and 2 from: [Bastion Access](https://github.com/openbraininstitute/aws-terraform-deployment/blob/staging/bastion_host/BASTION_ACCESS.md#database-access-via-port-forwarding)

Then one can get the credentials with:

```bash
export AWS_PROFILE=$WHAT_YOU_NAMED_IT
export CODEARTIFACT_AUTH_TOKEN=$(aws codeartifact get-authorization-token \
  --domain openbraininstitute \
  --query authorizationToken \
  --output text \
  --region us-east-1)
export UV_INDEX_OBI_CODEARTIFACT_PASSWORD="$CODEARTIFACT_AUTH_TOKEN"
export UV_INDEX_OBI_CODEARTIFACT_USERNAME="aws"
```
Then `uv` operations should work.

### For Most Users (Default)

```bash
# Install core + science dependencies
make install
```

This installs everything needed for running tasks and data processing scripts.

### For Development (Full Setup)

```bash
# Install all dependencies + dev tools
make install-dev
```

This installs everything needed for development: all optional dependencies + dev tools (pytest, ruff, etc.).

### For Specific Use Cases

```bash
# Service deployment
make install-service

# Notebook development
make install-notebooks

# Production build (all deps, no dev tools)
make install-all
```

## Technical Overview / Glossary

The package is split into **core/** and **scientific/** code.

**core/** defines the following key classes:

- **ScanConfig**: Defines configurations for specific modeling use cases. A Form is composed of one or multiple Blocks, which define the parameterization of a use case. Currently Forms can have both single Blocks and dictionaries of Blocks. Each Form has its own Initialize Block for specifying the base parameters of the use case.
- **Block**: Defines a component of a ScanConfig. Blocks support the specification of parameters which should be scanned over in the multi-dimensional parameter scan. When using the Form (in a Jupyter Notebook for example), any parameter which is specified as a list is used as a dimension of a multi-dimensional parameter scan when passed to a Scan object.
- **SingleConfig**: A single configuration instance within a scan.
- **Task**: Defines executable tasks that operate on configurations.
- **ScanGenerationTask**: Takes a single ScanConfig as input, an output path and a string for specifying how output files should be stored. The `scan.execute()` function can then be called which generates the multi-dimensional scan.

## FastAPI Service

Launch the FastAPI service, with docs viewable at: http://127.0.0.1:8100/docs

```bash
make install-service
make run-local
```

## Examples

Notebooks are available in the [examples/](../examples/) directory.
Remember to install notebook dependencies with:

```bash
make install-notebooks
```

## Further Documentation

- [Single Cell Simulations](scs.md) - Learn about single cell simulation workflows
- [Small Circuit Simulations](scircuit.md) - Learn about small circuit simulation workflows
