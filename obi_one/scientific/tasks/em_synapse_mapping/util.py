import logging
import os
import subprocess  # NOQA: S404
from pathlib import Path

L = logging.getLogger(__name__)


def compress_output(
    out_root: Path,
) -> os.PathLike:
    Path(out_root / "sonata.tar").write_bytes(
        subprocess.check_output(["tar", "-c", str(out_root)])  # NOQA: S607, S603
    )
    subprocess.check_call(["gzip", "-1", str(out_root / "sonata.tar")])  # NOQA: S607, S603
    return str(out_root / "sonata.tar.gz")
