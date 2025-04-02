# Install instructions

cd \<repo folder\>

# Install brew

brew install cmake==4.0.0

uv venv

source .venv/bin/activate

uv sync

uv pip install -e .

uv pip install -e ../brainbuilder

python -m ipykernel install --user --name=.venv --display-name "Python (.venv)"
