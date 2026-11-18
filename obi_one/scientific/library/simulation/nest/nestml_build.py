"""Compile NESTML models against the NEST installed in the environment.

NESTML builds a NEST extension module with CMake, using the ``nest-config`` of the NEST prefix
(``nest.build_info["prefix"]``). A NEST built from source, such as the NEST runtime image, or a
conda NEST has a valid prefix and is used as it is.

The PyPI ``nest-simulator`` wheel has none. NEST itself runs, but its build metadata is not
relocatable, so NESTML cannot build against it:

- ``nest.build_info["prefix"]`` and ``nest-config --prefix`` are the temporary directory the wheel
  was built in. NESTML stops with ``InvalidPathException: NEST path (...) is not a directory``.
- ``nest-config --compiler``, ``--includes`` and ``--libs`` name the compiler, the headers and the
  libraries of the build machine, so CMake cannot find a compiler.
- The wheel is built with the pre-C++11 ``std::string`` ABI. A module compiled with the default ABI
  builds, but ``nest.Install`` cannot load it: ``undefined symbol ... __cxx11 ...``.

These are known upstream, except the ABI, which we did not find reported:
https://github.com/nest/nest-simulator/issues/3762#issuecomment-4448756028 (the paths, with a
reproducer) and https://github.com/nest/nestml/issues/1384 (the same error, unresolved).

``nest_prefix`` therefore gives NESTML a prefix whose ``nest-config`` fixes those options and
passes the others to the wheel's own ``nest-config``. Remove it once the wheel's ``nest-config``
is relocatable. Building needs a C++ compiler (``CXX``, else ``c++``), CMake, and the Boost and GSL
headers. Nothing is linked: a module's NEST and GSL symbols resolve when ``nest.Install`` loads it.
"""

import shlex
import sys
from pathlib import Path

import nest
from pynestml.frontend.pynestml_frontend import generate_nest_target


class NestmlBuildError(RuntimeError):
    """Raised when a NESTML custom model cannot be generated or compiled."""


def nest_prefix(output_dir: Path) -> Path:
    """Return the NEST prefix to build against, or a ``nest-config`` wrapper for the PyPI wheel."""
    prefix = Path(nest.build_info["prefix"])
    if prefix.is_dir():
        return prefix
    wheel_config = shlex.quote(str(Path(sys.prefix) / "bin" / "nest-config"))
    includes = shlex.quote(f"-I{Path(nest.__file__).parent / 'include' / 'nest'}")
    wrapper = output_dir / "nest_prefix"
    (wrapper / "bin").mkdir(parents=True, exist_ok=True)
    script = wrapper / "bin" / "nest-config"
    script.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  --compiler) echo "${CXX:-c++}" ;;\n'
        f"  --includes) echo {includes} ;;\n"
        "  --libs) echo ;;\n"
        f'  --cflags) echo "$({wheel_config} --cflags) -D_GLIBCXX_USE_CXX11_ABI=0" ;;\n'
        f'  *) exec {wheel_config} "$@" ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return wrapper


def compile_nestml_module(source: Path, output_dir: Path, module_name: str) -> Path:
    """Generate and compile *source* into ``output_dir``; return the NEST module path.

    An existing ``<module_name>.so`` in *output_dir* is reused without rebuilding.
    """
    library = output_dir / f"{module_name}.so"
    if library.exists():
        return library
    output_dir.mkdir(parents=True, exist_ok=True)
    nest_path = str(nest_prefix(output_dir))
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
