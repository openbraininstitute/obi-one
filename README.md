# Install instructions

cd \<repo folder\>

uv venv

source .venv/bin/activate

uv sync

uv pip install '.[jupyter,subcircuit_extraction,connectivity_extraction,fastapi_app,database]'

uv pip install -e .

python -m ipykernel install --user --name=.venv --display-name "Python (.venv)"
