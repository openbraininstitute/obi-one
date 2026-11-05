"""Build environment for compiling NESTML models against the installed NEST.

NESTML compiles a NEST extension module with CMake, using ``nest-config`` to find NEST's headers and
flags. A compile-capable NEST (source build, conda-forge) ships a working ``nest-config`` and is
used as-is. The PyPI ``nest-simulator`` wheel needs these workarounds:

1. Its ``nest-config`` reports a stale prefix: a replacement (the shim) is written to a cache
   directory and passed to NESTML as ``nest_path``.
2. It uses the pre-C++11 ``std::string`` ABI, so modules need ``-D_GLIBCXX_USE_CXX11_ABI=0``.
3. Its headers include Boost, and models with ODEs that have no analytic solution need the GSL
   headers. Both must come from the environment; this module does not check for them.

Nothing is linked: a module's NEST and GSL symbols resolve when ``nest.Install`` loads it.
"""

import os
import shlex
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]  (queries nest-config)
from pathlib import Path

import nest
from pydantic import BaseModel
from pynestml.frontend.pynestml_frontend import generate_nest_target

from obi_one.core.exception import OBIONEError

OLD_ABI_FLAG = "-D_GLIBCXX_USE_CXX11_ABI=0"

OLD_ABI_SYMBOL = b"_ZNK4nest24StructuralPlasticityNode21get_synaptic_elementsESs"
NEW_ABI_SYMBOL = b"_ZNK4nest24StructuralPlasticityNode21get_synaptic_elementsENSt7__cxx11"


class NestmlToolchainError(RuntimeError):
    """Raised when the NESTML build environment cannot be prepared."""


class NestmlBuildError(RuntimeError):
    """Raised when a NESTML custom model cannot be generated or compiled."""


class NestInstall(BaseModel, frozen=True):
    package_dir: Path
    prefix: Path | None
    nest_config: Path | None


def cache_root() -> Path:
    env = os.environ.get("OBI_NESTML_CACHE")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "obi-one" / "nestml"


def find_nest_install() -> NestInstall:
    package_dir = Path(nest.__file__).resolve().parent
    build_info = getattr(nest, "build_info", {}) or {}
    raw_prefix = build_info.get("prefix")
    prefix = Path(raw_prefix) if raw_prefix else None
    if prefix is not None and not (prefix / "bin" / "nest-config").exists():
        prefix = None
    which = shutil.which("nest-config")
    nest_config = (prefix / "bin" / "nest-config") if prefix else (Path(which) if which else None)
    return NestInstall(package_dir=package_dir, prefix=prefix, nest_config=nest_config)


def uses_old_cxx_abi(kernel_library: Path) -> bool:
    """Return True if *kernel_library* exports NEST symbols built with the pre-C++11 string ABI."""
    if not kernel_library.exists():
        return False
    data = kernel_library.read_bytes()
    return OLD_ABI_SYMBOL in data and NEW_ABI_SYMBOL not in data


def _query_nest_config(nest_config: Path | None, option: str) -> str:
    if nest_config is None:
        return ""
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [str(nest_config), option], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def build_shim_options(install: NestInstall) -> dict[str, str]:
    cflags = _query_nest_config(install.nest_config, "--cflags") or "-O2 -std=c++20"
    cflags_tokens = [t for t in shlex.split(cflags) if t != OLD_ABI_FLAG]
    if uses_old_cxx_abi(install.package_dir / "nestkernel_api.so"):
        cflags_tokens.append(OLD_ABI_FLAG)
    includes = [install.package_dir / "include" / "nest"]
    return {
        "--includes": " ".join(f"-I{d}" for d in includes),
        "--cflags": " ".join(cflags_tokens),
        "--libs": "",
        "--compiler": os.environ.get("CXX", "c++"),
        "--libdir": "lib",
        "--static-libraries": "OFF",
        "--static-linking": "OFF",
        "--version": _query_nest_config(install.nest_config, "--version") or "3.10.0",
    }


def write_nest_config_shim(shim_prefix: Path, options: dict[str, str]) -> Path:
    bin_dir = shim_prefix / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    cases = [f"    --prefix) echo {shlex.quote(str(shim_prefix))} ;;"]
    cases += [f"    {opt}) echo {shlex.quote(value)} ;;" for opt, value in options.items()]
    script = "\n".join(
        [
            "#!/bin/sh",
            'for arg in "$@"; do',
            '  case "$arg" in',
            *cases,
            '    *) echo "nest-config shim: unsupported option $arg" >&2; exit 1 ;;',
            "  esac",
            "done",
            "",
        ]
    )
    path = bin_dir / "nest-config"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return shim_prefix


def resolve_nest_path() -> Path:
    """Return the ``nest_path`` to pass to NESTML's code generator.

    Uses the installed NEST prefix when it ships a working ``nest-config``; otherwise writes a
    ``nest-config`` shim.
    """
    install = find_nest_install()
    if install.prefix is not None:
        return install.prefix
    options = build_shim_options(install)
    return write_nest_config_shim(cache_root() / "nest-config-shim", options)


def compile_nestml_module(source: Path, output_dir: Path, module_name: str) -> Path:
    """Generate and compile *source* into ``output_dir``; return the NEST module path.

    An existing ``<module_name>.so`` in *output_dir* is reused without rebuilding.
    """
    library = output_dir / f"{module_name}.so"
    if library.exists():
        return library
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        nest_path = resolve_nest_path()
    except (NestmlToolchainError, OBIONEError, OSError) as exc:
        msg = f"Could not prepare the NESTML build environment: {exc}"
        raise NestmlBuildError(msg) from exc
    target = output_dir / "target"
    try:
        generate_nest_target(
            input_path=str(source),
            target_path=str(target),
            install_path=str(output_dir),
            module_name=module_name,
            logging_level="ERROR",
            codegen_opts={"nest_path": str(nest_path)},
        )
    except Exception as exc:
        msg = (
            f"NESTML failed to generate/compile '{source.name}' against NEST at {nest_path}. "
            f"Build output is under {target}."
        )
        raise NestmlBuildError(msg) from exc
    return library
