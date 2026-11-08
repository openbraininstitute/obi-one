SHELL := /bin/bash

export ENVIRONMENT ?= dev
export APP_NAME := obi-one
export APP_VERSION := $(shell git describe --abbrev --dirty --always --tags)
export COMMIT_SHA := $(shell git rev-parse HEAD)
export IMAGE_NAME ?= $(APP_NAME)
export IMAGE_TAG := $(APP_VERSION)
export IMAGE_TAG_ALIAS := latest
ifneq ($(ENVIRONMENT), prod)
	export IMAGE_TAG := $(IMAGE_TAG)-$(ENVIRONMENT)
	export IMAGE_TAG_ALIAS := $(IMAGE_TAG_ALIAS)-$(ENVIRONMENT)
endif

.PHONY: help install install-bluecellulab install-docs serve-docs compile-deps upgrade-deps check-deps compile-launch-deps upgrade-launch-deps check-launch-deps pin-launch-deps format lint lint-lib lint-app build publish test-local test-lib-local test-app-local test-app-docker run-local run-docker destroy

LIB_TEST_PATHS := tests/obi_one tests/launch_scripts
APP_TEST_PATHS := tests/app tests/ui_schema

define load_env
	# all the variables in the included file must be prefixed with export
	$(eval ENV_FILE := .env.$(1))
	@echo "Loading env from $(ENV_FILE)"
	$(eval include $(ENV_FILE))
endef

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-23s\033[0m %s\n", $$1, $$2}'

install:  ## Default installation (for running tasks and local scripts)
	CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync

install-bluecellulab:  ## Install with BlueCelluLab (simulation, MEModel calibration/validation)
	CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync --extra bluecellulab

install-meshing:  ## Install with private meshing dependencies (Requires AWS auth)
	CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync --extra meshing

install-simplification:  ## Install with private circuit simplification dependencies (Requires AWS auth)
	CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync --extra simplification

install-connectivity:  ## Install with connectivity dependencies (for connectivity analysis & plots) -- needs notebooks as well
	CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync --extra notebooks --extra connectivity

install-notebooks:  ## Install with notebooks dependencies (for running notebooks locally)
	CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync --extra notebooks

install-service:  ## Install with service dependencies (for running as a service)
	CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync --extra service

install-service-meshing: ## Install both service and meshing dependencies
	CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync --extra service --extra meshing

install-all:  ## Install all dependencies (for production/deployment)
	CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync --extra all

install-dev:  ## Install all dependencies + dev tools (for development)
	CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync --extra all --group dev

install-ipython: install-all ## Create a virtual environment and install the ipython kernel
	uv run python -m ipykernel install --user --name=obi-one --display-name "obi-one"

install-docs:  ## Install documentation dependencies without uninstalling other dependencies
	uv sync --group docs

serve-docs:  ## Serve documentation locally
	uv run mkdocs serve

compile-deps:  ## Create or update the lock file, without upgrading the version of the dependencies
	uv lock --upgrade-package entitysdk

upgrade-deps:  ## Create or update the lock file, using the latest version of the dependencies
	uv lock --upgrade

check-deps:  ## Check that the dependencies in the existing lock file are valid, and that entitysdk is at the latest version.
	uv lock --locked --upgrade-package entitysdk

compile-launch-deps:  ## Compile launch-script requirements (.in -> pinned .txt), preserving existing pins. Optional: FILE=<path to .in or dir>
	uv run python launch_scripts/tools/launch_deps_compile.py $(FILE)

upgrade-launch-deps:  ## Compile launch-script requirements, upgrading the transitive closure to latest. Optional: FILE=<path to .in or dir>
	uv run python launch_scripts/tools/launch_deps_compile.py --upgrade $(FILE)

check-launch-deps:  ## Verify committed launch-script .txt files are consistent with their .in sources
	uv run python launch_scripts/tools/launch_deps_compile.py --check $(FILE)

pin-launch-deps:  ## Pin obi-one==VERSION in launch-script .txt files (used by the release-pin workflow). Required: VERSION=<calver>. Optional: FILE=<path to .txt or dir>
	python3 launch_scripts/tools/launch_deps_pin.py --version "$(VERSION)" $(FILE)

format:  ## Run formatters
	uv run ruff format $(FILE)
	uv run ruff check --fix $(FILE)
	uv run ty check --fix $(FILE)

# Shared test helpers used by both suites (owned by the lib lint path).
SHARED_TEST_PATHS := tests/conftest.py tests/utils.py tests/httpx_mock.py

lint-lib:  ## Lint/format-check obi_one + its tests + launch_scripts
	uv run ruff format --check obi_one tests/obi_one launch_scripts tests/launch_scripts $(SHARED_TEST_PATHS)
	uv run ruff check obi_one tests/obi_one launch_scripts tests/launch_scripts $(SHARED_TEST_PATHS)
	uv run ty check --error-on-warning obi_one launch_scripts

lint-app:  ## Lint/format-check app + its tests + ui_schema
	uv run ruff format --check app tests/app tests/ui_schema
	uv run ruff check app tests/app tests/ui_schema
	uv run ty check --error-on-warning app

lint: lint-lib lint-app  ## Run all linters (lib then app)

format_count: ## Count the number of errors by file
	uv run ruff check --output-format=json | jq '.[].filename' | sort | uniq -c

format_types: ## Count the number of errors by type
	uv run ruff check --output-format=json | jq -r '.[] | [.code, .message] | @tsv' | sort | uniq -c

build: BUILDER ?=
build:  ## Build the Docker image. CI may set BUILDER, CACHE_FROM, CACHE_TO (e.g. type=gha).
	# Compose has no --cache-from/--cache-to flags; GHA cache goes through docker-compose.gha-cache.yml + bake.
	$(if $(and $(CACHE_FROM),$(CACHE_TO)),COMPOSE_BAKE=true) docker compose --profile "*" --progress=plain \
		$(if $(and $(CACHE_FROM),$(CACHE_TO)),-f docker-compose.yml -f docker-compose.gha-cache.yml) \
		build \
		$(if $(BUILDER),--builder "$(BUILDER)") \
		app

publish: build  ## Publish the Docker image to DockerHub
	docker compose push app

test-lib-local:  ## Run lib (obi_one + launch_scripts) tests locally with coverage
	@$(call load_env,test-local)
	mkdir -p .coverage
	COVERAGE_FILE=.coverage/coverage-lib.db \
	uv run -m pytest $(LIB_TEST_PATHS) \
		--cov=obi_one \
		--cov-report=term-missing \
		--cov-report=xml:.coverage/coverage-lib.xml

test-app-local:  ## Run app tests locally with coverage (expects install-service / --extra service)
	@$(call load_env,test-local)
	mkdir -p .coverage
	COVERAGE_FILE=.coverage/coverage-app.db \
	uv run -m pytest $(APP_TEST_PATHS) \
		--cov=app \
		--cov-report=term-missing \
		--cov-report=xml:.coverage/coverage-app.xml

test-local: test-lib-local test-app-local  ## Run lib then app tests locally (host)

test-file: ## Run tests in a single test file locally. Usage: make test-file FILE=path/to/test_file.py
	@$(call load_env,test-local)
	uv run -m pytest $(FILE) --no-cov --disable-warnings

test-schema: ## Run schema tests locally.
	@$(call load_env,test-local)
	uv run -m pytest tests/ui_schema/test_schema.py tests/ui_schema/test_titles.py --no-cov --disable-warnings

test-schema-verbose: ## Run schema tests locally with verbose output.
	@$(call load_env,test-local)
	uv run -m pytest tests/ui_schema/test_schema.py tests/ui_schema/test_titles.py --no-cov --disable-warnings --log-cli-level=INFO

test-app-docker: build  ## Run app tests in Docker (production image, --extra service)
	mkdir -p .coverage
	COVERAGE_FILE=.coverage/coverage-app.db \
	PYTEST_ARGS="$(APP_TEST_PATHS) --cov=app --cov-report=term-missing --cov-report=xml:.coverage/coverage-app.xml" \
	docker compose run --rm --remove-orphans test

pip-audit:  ## Run package auditing
	uv run --with pip-audit pip-audit --local --progress-spinner off --desc off \
		--ignore-vuln CVE-2025-53000

run-local: ## Run the application locally
	@$(call load_env,run-local)
	uv run -m app run --host $(UVICORN_HOST) --port $(UVICORN_PORT) --reload

run-docker: build  ## Run the application in Docker
	docker compose up app --watch --remove-orphans

destroy: export COMPOSE_PROFILES=run,test
destroy:  ## Take down the application and remove the volumes
	docker compose down --remove-orphans --volumes
