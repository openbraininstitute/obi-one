# Install instructions (draft/notes)

uv venv

source .venv/bin/activate

uv sync

uv pip install '.[jupyter,subcircuit_extraction,fastapi_app]'

uv pip install -e .


# Todo

Rewrite several comments in scan.py

Complete bbp-workflow like simulation campaign config

Test building Block dependency tree

Test/integrate Block dictionary parameters for filtering