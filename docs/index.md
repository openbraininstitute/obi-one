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

### Private ultraliser from AWS CodeArtifacts

The `meshing` extra (installed by `make install-meshing`, `make install-all` and `make install-dev`) requires `ultraliser`, which is used by the skeletonization and mesh LOD generation tasks and is published only on AWS CodeArtifact.
The service Docker image does not include the `meshing` extra: those tasks run as launch-system jobs that install `ultraliser` from their own requirements in `launch_scripts/`, so building the image does not need a CodeArtifact token.
At the OBI [AWS Console](https://openbraininstitute.awsapps.com/start), first check that you have access to the `Container Registry` (AWS Account Id: `985539765147`).

Then setup the the SSO AWS login; steps 1 and 2 from: [Bastion Access](https://github.com/openbraininstitute/aws-terraform-deployment/blob/staging/bastion_host/BASTION_ACCESS.md#database-access-via-port-forwarding)

Make sure you have the following profile in your `~/.aws/config` file:

```ini
[profile codeartifact]
sso_session = obi
sso_account_id = 985539765147
sso_role_name = ReadOnlyAccess
region = us-east-1
output = json
```

Then login to SSO if you haven't already:

```bash
aws sso login --sso-session obi
```

Then one can get the credentials with:

```bash
export AWS_PROFILE=codeartifact
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
- **SingleConfig**: A single configuration instance within a scan. Which SingleConfig a given ScanConfig expands into is declared once in `config_task_map` (each task's `TaskSpec`, resolved by `TaskType` / `task_type` on the config class). A ScanConfig reads it back through its `single_config_class` property, so the pairing does not have to be repeated on the config classes themselves.
- **TaskSpec**: One entry of the `TASK_SPECS` registry in `config_task_map`, pairing a `TaskType` with its task, SingleConfig and ScanConfig classes plus the entitycore config/activity types. Classes are declared as `("package.module", "ClassName")` reference tuples and imported by the spec's `task_cls` / `single_config_cls` / `scan_config_cls` properties on first access, so reading a spec (for example to get its `asset_label`) imports no task code. Tasks behind an optional dependency declare `requires_package`, and are reported as unavailable rather than failing to import when it is missing. The deserialization type map in `core/deserializable_types.py` is derived from this registry, so registering a task type is what makes its configs deserializable.
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
