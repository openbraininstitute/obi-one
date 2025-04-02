# Install instructions

cd \<repo folder\>

uv venv

source .venv/bin/activate

uv sync

uv pip install '.[jupyter,subcircuit_extraction,connectivity,fastapi_app,database,blueetl]'

uv pip install -e .

uv pip install -e ../brainbuilder

python -m ipykernel install --user --name=.venv --display-name "Python (.venv)"
