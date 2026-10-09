# AGENTS.md

Shared guidance for AI coding agents (Claude Code, Cursor, Kiro, and others) working in this repository.

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
- **`ScanConfig`** (`scan_config.py`) - Abstract configuration composed of Blocks. Defines a modeling use case (e.g., `CircuitSimulationScanConfig`). Has class variables `name` and `description`. The SingleConfig it expands into comes from its `TaskSpec` in `config_task_map` (looked up by the config class name via `get_task_spec_for_scan_config`), via the `single_config_class` property.
- **`SingleConfigMixin`** (`single.py`) - Enforces that all parameters are single values (no lists). Used for execution-ready configs after scan expansion.
- **`Task`** (`task.py`) - Abstract execution unit with an `execute()` method.
- **`ScanGenerationTask`** (`scan_generation.py`) - Expands a ScanConfig into SingleConfigs via Cartesian product of multi-value parameters, then runs each.

**Data flow:** `ScanConfig` (with list params) -> `ScanGenerationTask` -> multiple `SingleConfig` instances -> `Task.execute()` per config.

### `obi_one/scientific/` - Domain Implementation

- **`blocks/`** - Domain-specific blocks: stimuli, neuron sets, recordings, morphology locations, synaptic/neuronal manipulations
- **`tasks/`** - Task implementations: circuit extraction, simulation, morphology operations, ephys extraction, ion channel modeling
- **`unions_and_references/`** - Discriminated union types (`ScanConfigsUnion`, `TasksUnion`, etc.) and the block reference types / reference-type constants that go with them
- **`mappings_and_registry/`** - `config_task_map.py` for config->task dispatch and `block_reference_registry.py` for block reference registration
- **`from_id/`** - Lazy-loading wrappers that fetch data from entitysdk by ID
- **`library/`** - Reusable scientific utility functions

### `app/` - FastAPI Service

- **`endpoints/`** - REST API routers (task launch, validation, metrics)
- **`services/`** - Business logic (task submission with accounting/callbacks, morphology, validation)
- **`dependencies/`** - FastAPI dependency injection (auth, db_client, accounting)
- **`schemas/`** - Pydantic request/response models
- **`config.py`** - Pydantic Settings with env-based configuration

**Task submission flow:** Endpoint -> Task Service -> create EntitySDK Activity -> estimate accounting cost -> reserve credits -> submit to Launch System -> callback on completion.

## Adding Tasks and Blocks

For complex tasks, create `obi_one/scientific/tasks/<task_name>/` and split only the modules you need:

| Module | Responsibility |
| --- | --- |
| `config.py` | Task configuration and validation |
| `staging.py` | Preprocessing, data fetching, and preparation before execution |
| `task.py` | Task / scientific execution logic |
| `registration.py` | Database registration of results after execution |
| `utils.py` | Task-specific helpers only (see Code Conventions for shared utilities) |

- Put task-related blocks under `obi_one/scientific/blocks/<task_name>/`.
- Create only modules that are actually needed.
- For helpers and shared utilities, follow Code Conventions (reuse / centralization).

When registering a new **`TaskType`** in the framework (not only a launch-only legacy job):

- Add a `TASK_SPECS[TaskType.…] = TaskSpec(...)` entry in `obi_one/scientific/mappings_and_registry/config_task_map.py`. Classes are declared as `("package.module", "ClassName")` reference tuples and imported lazily by the spec's `task_cls` / `single_config_cls` / `scan_config_cls` properties, so do not import task modules there. Reuse the module-prefix constants at the top of the file (`TASKS`, `NEURON_CONFIG`, …). Gate tasks needing an optional dependency with `requires_package=`.
- Do not add the config classes to `TYPE_MAP` in `obi_one/core/deserializable_types.py`: it is derived from `TASK_SPECS`. Only framework classes and `__init__`/alias re-exports are listed there explicitly.
- Add the new type to `LAUNCH_SYSTEM_TASK_TYPES_WITHOUT_CONFIG_MAP` in `tests/obi_one/scientific/mappings_and_registry/test_config_task_map.py` only if it is launch-only; registered types are derived from `TASK_SPECS`, so `test_config_task_map_cases_partition_task_type_enum` keeps partitioning the enum on its own.

## entitysdk / database

- Prefer `entitysdk.Client` and its methods over reimplementing the same behavior.
- Use types from `entitysdk.types` instead of plain strings when those types exist.
- Database helper placement: see Code Conventions.

## Code Conventions

- Before adding any new function/helper, search `obi_one/utils/`, `obi_one/db_sdk/`, `obi_one/scientific/library/`, and entitysdk (`Client` methods, `entitysdk.registration`). Reuse; do not duplicate. If reusable DB/registration logic is missing from entitysdk, flag it for entitysdk instead of building a parallel version in obi-one.
- Put generic helpers (filesystem, format I/O, serialization, etc.) in `obi_one/utils/`; keep them task-agnostic.
- Put database-related (entitysdk) helpers in `obi_one/db_sdk/`, not in task modules or `obi_one/utils/`.
- **Python 3.12** required (`>=3.12.2,<3.13`)
- **Ruff** with `select = ["ALL"]` - very strict linting. Run `make format` before PRs.
- **100 char line length** (Python code; not Markdown, see Documentation)
- **Google-style docstrings** (`pydocstyle convention = "google"`)
- Comments and docstrings should explain non-obvious intent, not restate the code. Prefer none over redundant; don't duplicate what argparse/signatures already convey.
- Functions that perform actions must not silently no-op (e.g. `if x is None: return`) or swallow errors. Let them raise, and handle optional inputs and exceptions where the function is called.
- **Pydantic v2** for all data models
- Do not add `from __future__ import annotations`.
- Avoid protected (`_`-prefixed) constants and classes. Do not import protected functions from other modules; rename them to public names first (drop the leading `_`).
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

## Enabling ScanConfigs in the UI

Read [`docs/gui-definition-spec/gui-definition.md`](docs/gui-definition-spec/gui-definition.md) before working on UI-enabled ScanConfigs. The basics:

- A ScanConfig becomes UI-enabled by setting `ui_enabled = True`; this turns on schema validation in CI (`make test-schema`), and only configs that comply with the spec can be integrated into the UI. Each field declares a `ui_element` in its `json_schema_extra`.
- There is a strict 1-1 mapping between the JSONSchema a field produces (and therefore its Pydantic annotation) and its `ui_element` string. The frontend renders and reads each `ui_element` from a fixed schema shape, so the validator for a `ui_element` is the contract the frontend relies on.
- Validators live in the locked `tests/ui_schema/validators/` package (block elements) and `tests/ui_schema/validators/root/` (root elements), one module per `ui_element`. `registry.py` is the single place a validator is registered (the `__init__.py` files re-export nothing; import a validator from its own module). The CI guard (`guard-validators` in `.github/workflows/run-tests.yml`) blocks MODIFIED or DELETED files under the folder; ADDED validator files and the guard-exempt `registry.py` are allowed.
- If adding a `ui_element` (or changing a field's annotation) breaks validation, do NOT change the existing validators to make it pass. Loosening a validator effectively rewrites the spec the frontend depends on and risks breaking the frontend for every other config using that element.
- Instead, add a NEW `ui_element`: document it in `gui-definition.md`, add a validator module for it under `tests/ui_schema/validators/`, and register it in `registry.py`. This needs no label (a new file is an addition, not an edit to a locked validator). Even functionally similar elements must have unique `ui_element` identifiers if their schema shapes differ.
- If a user insists on modifying an existing validator instead of adding a new element, explain why that shouldn't be done (it rewrites the frontend contract and risks breaking the frontend) and propose the alternative: write a new `ui_element`.
- Under very rare circumstances (this has not happened so far) there may be a genuine need to modify or delete an existing validator. Only then is the `change-validators` label required: point it out explicitly, explain that it requires explicit approval from the frontend team, and instruct the user to add the `change-validators` label to the GitHub PR so a reviewer can sign off.

## Documentation

- In Markdown files (`README.md`, `docs/`, `AGENTS.md`, etc.), do not hard wrap lines at a fixed width. Write each paragraph or list item on one line; a line break is allowed only at the end of a sentence.

## Dependencies

- Package manager: **uv** (>=0.9.22)
- entitysdk is always kept at latest version (`make compile-deps` enforces this)
- Key scientific deps: bluepysnap, brainbuilder, neurom, bluecellulab, bluepyefe, connectome-utilities, caveclient

## CI/CD

- PR checks: lint, test, pip-audit, codecov upload
- Docs check: PRs must update `docs/` files (skip with `skip docs` label)
- Docker: `make build` / `make publish`
