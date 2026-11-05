"""Compile NESTML models against the NEST installed in the environment.

NESTML builds a NEST extension module with CMake, using the ``nest-config`` of the NEST prefix
(``nest.build_info["prefix"]``). NEST must therefore be a compile-capable install, such as the NEST
runtime image or a source or conda build. The PyPI ``nest-simulator`` wheel is not supported: its
``nest-config`` reports a stale prefix and it uses the pre-C++11 ``std::string`` ABI, so the
modules built for it cannot be loaded.

NEST's headers include Boost, and models with ODEs that have no analytic solution need the GSL
headers. Both must come from the environment; this module does not check for them.

Nothing is linked: a module's NEST and GSL symbols resolve when ``nest.Install`` loads it.
"""

from pathlib import Path

import nest
from pynestml.frontend.pynestml_frontend import generate_nest_target


class NestmlBuildError(RuntimeError):
    """Raised when a NESTML custom model cannot be generated or compiled."""


def compile_nestml_module(source: Path, output_dir: Path, module_name: str) -> Path:
    """Generate and compile *source* into ``output_dir``; return the NEST module path.

    An existing ``<module_name>.so`` in *output_dir* is reused without rebuilding.
    """
    library = output_dir / f"{module_name}.so"
    if library.exists():
        return library
    output_dir.mkdir(parents=True, exist_ok=True)
    nest_path = nest.build_info["prefix"]
    target = output_dir / "target"
    try:
        generate_nest_target(
            input_path=str(source),
            target_path=str(target),
            install_path=str(output_dir),
            module_name=module_name,
            logging_level="ERROR",
            codegen_opts={"nest_path": nest_path},
        )
    except Exception as exc:
        msg = (
            f"NESTML failed to generate/compile '{source.name}' against NEST at {nest_path}. "
            f"Build output is under {target}."
        )
        raise NestmlBuildError(msg) from exc
    return library
