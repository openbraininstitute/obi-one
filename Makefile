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

.PHONY: help install compile-deps upgrade-deps check-deps format lint build publish test-local test-docker run-local run-docker destroy

define load_env
	# all the variables in the included file must be prefixed with export
	$(eval ENV_FILE := .env.$(1))
	@echo "Loading env from $(ENV_FILE)"
	$(eval include $(ENV_FILE))
endef

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-23s\033[0m %s\n", $$1, $$2}'

install:  ## Create a virtual environment
	CMAKE_POLICY_VERSION_MINIMUM=3.5 uv sync --extra connectivity
	uv run python -m ipykernel install --user --name=obi-one --display-name "obi-one"

compile-deps:  ## Create or update the lock file, without upgrading the version of the dependencies
	uv lock

upgrade-deps:  ## Create or update the lock file, using the latest version of the dependencies
	uv lock --upgrade

check-deps:  ## Check that the dependencies in the existing lock file are valid
	uv lock --locked

format:  ## Run formatters
	uv run -m ruff format $(FILE)
	uv run -m ruff check --fix $(FILE)

lint:  ## Run linters
	uv run -m ruff format --check
	uv run -m ruff check
	#uv run -m pyright obi_one

format_count: ## Count the number of errors by file
	uv run -m ruff check --output-format=json | jq '.[].filename' | sort | uniq -c

format_types: ## Count the number of errors by type
	uv run -m ruff check --output-format=json | jq -r '.[] | [.code, .message] | @tsv' | sort | uniq -c

build:  ## Build the Docker image
	docker compose --profile "*" --progress=plain build app

publish: build  ## Publish the Docker image to DockerHub
	docker compose push app

test-local:  ## Run tests locally
	@$(call load_env,test-local)
	uv run -m pytest
	uv run -m coverage xml
	uv run -m coverage html

test-docker: build  ## Run tests in Docker
	docker compose run --rm --remove-orphans test

pip-audit:
	uv run --group audit pip-audit --progress-spinner off -f json -o pip-audit-output.json || true

run-local: ## Run the application locally
	@$(call load_env,run-local)
	uv run -m app run --host $(UVICORN_HOST) --port $(UVICORN_PORT) --reload

run-docker: build  ## Run the application in Docker
	docker compose up app --watch --remove-orphans

destroy: export COMPOSE_PROFILES=run,test
destroy:  ## Take down the application and remove the volumes
	docker compose down --remove-orphans --volumes
