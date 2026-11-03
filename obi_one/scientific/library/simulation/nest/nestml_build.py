"""Build environment for compiling NESTML models against the installed NEST.

NESTML compiles a NEST extension module with CMake, using ``nest-config`` to find NEST's headers and
flags. A compile-capable NEST (source build, conda-forge) ships a working ``nest-config`` and is
used as-is. The PyPI ``nest-simulator`` wheel needs these workarounds:

1. Its ``nest-config`` reports a stale prefix: a replacement (the shim) is written to a cache
   directory and passed to NESTML as ``nest_path``.
2. It ships neither the Boost headers NEST's headers include nor the GSL headers (1.15, matching
   the wheel's libgsl) that GSL-solved models include.
3. It uses the pre-C++11 ``std::string`` ABI, so modules need ``-D_GLIBCXX_USE_CXX11_ABI=0``.

Nothing is linked: a module's NEST and GSL symbols resolve when ``nest.Install`` loads it. Headers
come from ``NESTML_BOOST_INCLUDE`` / ``NESTML_GSL_INCLUDE``, then system include directories, then a
checksum-verified download into ``OBI_NESTML_CACHE`` (default ``~/.cache/obi-one/nestml``).
"""

import os
import shlex
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]  (queries nest-config)
import tarfile
from pathlib import Path

import nest
from pydantic import BaseModel

from obi_one.utils.filesystem import download_file

BOOST_URL = "https://archives.boost.io/release/1.86.0/source/boost_1_86_0.tar.gz"
BOOST_SHA256 = "2575e74ffc3ef1cd0babac2c1ee8bdb5782a0ee672b1912da40e5b4b591ca01f"
GSL_URL = "https://ftp.gnu.org/gnu/gsl/gsl-1.15.tar.gz"
GSL_SHA256 = "85b907e57902e2b7606ef3aef960302ffdd13bd9dc5b8fcbfa75e4f0bf340ea3"

OLD_ABI_FLAG = "-D_GLIBCXX_USE_CXX11_ABI=0"

OLD_ABI_SYMBOL = b"_ZNK4nest24StructuralPlasticityNode21get_synaptic_elementsESs"
NEW_ABI_SYMBOL = b"_ZNK4nest24StructuralPlasticityNode21get_synaptic_elementsENSt7__cxx11"

SYSTEM_INCLUDE_DIRS = (Path("/usr/include"), Path("/usr/local/include"))


class NestmlToolchainError(RuntimeError):
    """Raised when the NESTML build environment cannot be prepared."""


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


def _env_include(var: str, marker: str) -> Path | None:
    value = os.environ.get(var)
    if not value:
        return None
    path = Path(value)
    if not (path / marker).exists():
        msg = f"{var}={value} does not contain {marker}."
        raise NestmlToolchainError(msg)
    return path


def _system_include(marker: str) -> Path | None:
    for directory in SYSTEM_INCLUDE_DIRS:
        if (directory / marker).exists():
            return directory
    return None


def boost_include_dir() -> Path:
    marker = "boost/type_index.hpp"
    found = _env_include("NESTML_BOOST_INCLUDE", marker) or _system_include(marker)
    if found is not None:
        return found
    target = cache_root() / "boost_1_86_0"
    if (target / marker).exists():
        return target
    archive = download_file(BOOST_URL, cache_root() / "downloads" / "boost.tar.gz", BOOST_SHA256)
    with tarfile.open(archive) as tar:
        members = [m for m in tar.getmembers() if m.name.startswith("boost_1_86_0/boost/")]
        tar.extractall(cache_root(), members=members, filter="data")
    archive.unlink(missing_ok=True)
    return target


def gsl_include_dir() -> Path:
    marker = "gsl/gsl_errno.h"
    found = _env_include("NESTML_GSL_INCLUDE", marker)
    if found is not None:
        return found
    target = cache_root() / "gsl-1.15-include"
    if (target / marker).exists():
        return target
    archive = download_file(GSL_URL, cache_root() / "downloads" / "gsl.tar.gz", GSL_SHA256)
    headers = target / "gsl"
    headers.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            name = Path(member.name)
            # the tarball's gsl-1.15/gsl/ is empty: headers live in per-component directories
            if not (member.isfile() and name.name.startswith("gsl_") and name.suffix == ".h"):
                continue
            if len(name.parts) > 2 and name.parts[1] == "gsl":  # ruff: ignore[magic-value-comparison]
                continue
            source = tar.extractfile(member)
            if source is not None:
                (headers / name.name).write_bytes(source.read())
    archive.unlink(missing_ok=True)
    return target


def _query_nest_config(nest_config: Path | None, option: str) -> str:
    if nest_config is None:
        return ""
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [str(nest_config), option], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def build_shim_options(install: NestInstall, include_dirs: list[Path]) -> dict[str, str]:
    cflags = _query_nest_config(install.nest_config, "--cflags") or "-O2 -std=c++20"
    cflags_tokens = [t for t in shlex.split(cflags) if t != OLD_ABI_FLAG]
    if uses_old_cxx_abi(install.package_dir / "nestkernel_api.so"):
        cflags_tokens.append(OLD_ABI_FLAG)
    includes = [install.package_dir / "include" / "nest", *include_dirs]
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


def resolve_nest_path(*, needs_gsl: bool = True) -> Path:
    """Return the ``nest_path`` to pass to NESTML's code generator.

    Uses the installed NEST prefix when it ships a working ``nest-config``; otherwise prepares
    Boost (and, if *needs_gsl*, GSL) headers and writes a ``nest-config`` shim.
    """
    install = find_nest_install()
    if install.prefix is not None:
        return install.prefix
    include_dirs = [boost_include_dir()]
    if needs_gsl:
        include_dirs.append(gsl_include_dir())
    options = build_shim_options(install, include_dirs)
    return write_nest_config_shim(cache_root() / "nest-config-shim", options)
