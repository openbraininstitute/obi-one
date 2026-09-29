import logging
import os
import resource
import shlex
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from pathlib import Path

L = logging.getLogger(__name__)


def run_and_log(
    command: list[str], cwd: Path | None = None, env: dict | None = None
) -> subprocess.CompletedProcess:
    """Run a subprocess command and log stdout/stderr."""
    cmd_str = shlex.join(command)
    L.info("Command: %s", cmd_str)
    try:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            command,
            check=True,
            capture_output=True,
            text=True,
            shell=False,
            cwd=cwd,
            env=env or os.environ,
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


def log_peak_rss() -> None:
    """Log peak resident memory for recalibrating launch resource estimates."""
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # ru_maxrss is in KiB on Linux (the launch-system executor), bytes on macOS.
    gb = rss / 1024**2 if sys.platform.startswith("linux") else rss / 1024**3
    L.info("Peak RSS: %.2f GB", gb)
