# Install instructions (draft/notes)

uv venv

source .venv/bin/activate

uv sync

uv pip install '.[jupyter,subcircuit_extraction]'

uv pip install -e .


# Todo

Option for scan folder hierarchy to be based on scan variables and values

Create bbp-workflow like simulation campaign config

Test building Block dependency tree

Test/integrate Block dictionary parameters for filtering

