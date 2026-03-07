import logging
import shlex
import subprocess  # noqa: S404
from pathlib import Path

L = logging.getLogger(__name__)


def run_and_log(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a subprocess command and log stdout/stderr."""
    cmd_str = shlex.join(command)
    L.info("Command: %s", cmd_str)
    try:
        result = subprocess.run(  # noqa: S603
            command, check=True, capture_output=True, text=True, shell=False, cwd=cwd
        )
    except subprocess.CalledProcessError as e:
        L.error("Return code: %s", e.returncode)

        if e.stdout:
            L.error("stdout: %s", e.stdout.strip())

        if e.stderr:
            L.error("stderr: %s", e.stderr.strip())

        raise

    if result.stdout:
        L.debug("stdout: %s", result.stdout.strip())

    if result.stderr:
        L.warning("stderr: %s", result.stderr.strip())

    return result
