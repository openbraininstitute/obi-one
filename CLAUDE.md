# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OBI-ONE is a Python library and FastAPI service for biophysically-detailed brain modeling. It provides standardized workflows with cloud database integration (entitysdk), parameter scanning, and provenance tracking.

## Common Commands

```bash
# Install dependencies (requires: brew install uv open-mpi boost cmake)
make install

# Run FastAPI service locally (http://127.0.0.1:8100/docs)
make run-local

# Run all tests with coverage
make test-local

# Run a single test file
make test-file FILE=tests/path/to/test_file.py

# Run schema tests only
make test-schema

# Lint (check only)
make lint

# Format and auto-fix
make format
make format FILE=obi_one/path/to/file.py

# Update lock file (keeps entitysdk at latest)
make compile-deps
```

## Architecture

The codebase has two main source directories:

- **`obi_one/`** - Core library package (installed as `obi-one`)
- **`app/`** - FastAPI service wrapping the library

### `obi_one/core/` - Framework Abstractions

The core uses a **block-based compositional pattern**:

- **`OBIBaseModel`** (`base.py`) - Pydantic base model with discriminator-based type field for polymorphic serialization. All domain models inherit from this.
- **`Block`** (`block.py`) - Composable, parameterizable component. Any field set to a list becomes a dimension in a parameter scan.
- **`ScanConfig`** (`scan_config.py`) - Abstract configuration composed of Blocks. Defines a modeling use case (e.g., `CircuitSimulationScanConfig`). Has class variables `name`, `description`, `single_coord_class_name`.
- **`SingleConfigMixin`** (`single.py`) - Enforces that all parameters are single values (no lists). Used for execution-ready configs after scan expansion.
- **`Task`** (`task.py`) - Abstract execution unit with an `execute()` method.
- **`ScanGenerationTask`** (`scan_generation.py`) - Expands a ScanConfig into SingleConfigs via Cartesian product of multi-value parameters, then runs each.

**Data flow:** `ScanConfig` (with list params) -> `ScanGenerationTask` -> multiple `SingleConfig` instances -> `Task.execute()` per config.

### `obi_one/scientific/` - Domain Implementation

- **`blocks/`** - Domain-specific blocks: stimuli, neuron sets, recordings, morphology locations, synaptic/neuronal manipulations
- **`tasks/`** - Task implementations: circuit extraction, simulation, morphology operations, ephys extraction, ion channel modeling
- **`unions/`** - Discriminated union types (`ScanConfigsUnion`, `TasksUnion`, etc.) and `config_task_map.py` for dispatch
- **`from_id/`** - Lazy-loading wrappers that fetch data from entitysdk by ID
- **`library/`** - Reusable scientific utility functions

### `app/` - FastAPI Service

- **`endpoints/`** - REST API routers (task launch, validation, metrics)
- **`services/`** - Business logic (task submission with accounting/callbacks, morphology, validation)
- **`dependencies/`** - FastAPI dependency injection (auth, db_client, accounting)
- **`schemas/`** - Pydantic request/response models
- **`config.py`** - Pydantic Settings with env-based configuration

**Task submission flow:** Endpoint -> Task Service -> create EntitySDK Activity -> estimate accounting cost -> reserve credits -> submit to Launch System -> callback on completion.

## Code Conventions

- **Python 3.12** required (`>=3.12.2,<3.13`)
- **Ruff** with `select = ["ALL"]` - very strict linting. Run `make format` before PRs.
- **100 char line length**
- **Google-style docstrings** (`pydocstyle convention = "google"`)
- **Pydantic v2** for all data models
- Tests are less strict on linting (annotations, docstrings, magic values, assert, private access, class-based test methods all allowed)
- Use `Field(default=[...])` for mutable defaults on Pydantic model fields in tests to avoid RUF012
- Coverage minimum: 30%, measured on both `app/` and `obi_one/`
- Output files from examples should go in `obi-output/` outside the repo

## Testing

- **pytest** with `pytest-cov`, `pytest-freezer` (time), `pytest-httpx` (HTTP mocking)
- Test paths: `tests/` and `examples/`
- Tests mirror source structure: `tests/core/`, `tests/scientific/`, `tests/app/`, `tests/tasks/`
- Tests use class-based organization (`class TestFoo:` with `def test_*` methods)
- Env vars for testing loaded from `.env.test-local`
- Always run `make format` before committing test files

## Dependencies

- Package manager: **uv** (>=0.9.22)
- entitysdk is always kept at latest version (`make compile-deps` enforces this)
- Key scientific deps: bluepysnap, brainbuilder, neurom, bluecellulab, bluepyefe, connectome-utilities, caveclient

## CI/CD

- PR checks: lint, test, pip-audit, codecov upload
- Docs check: PRs must update `docs/` files (skip with `skip docs` label)
- Docker: `make build` / `make publish`
