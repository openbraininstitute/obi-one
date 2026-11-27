import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys

CODE = """
import sys
before = sys.getdlopenflags()
import nest
widened = sys.getdlopenflags()
sys.setdlopenflags(before)
from obi_one.scientific.library.simulation.nest.nest_import import nest as safe_nest
print(before, widened, sys.getdlopenflags(), safe_nest is nest)
"""


def test_importing_nest_does_not_leave_global_symbols_set():
    out = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [sys.executable, "-c", CODE], capture_output=True, text=True, check=True
    ).stdout.split()[-4:]
    before, widened, after, same_module = out
    assert int(widened) != int(before)
    assert int(after) == int(before)
    assert same_module == "True"
