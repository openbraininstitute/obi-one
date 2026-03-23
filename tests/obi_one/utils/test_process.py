import logging
from subprocess import CalledProcessError  # noqa: S404
from unittest.mock import Mock, patch

import pytest

from obi_one.utils import process as test_module


def test_run_success_logs_and_returns(tmp_path, caplog):
    mock_result = Mock()
    mock_result.stdout = "hello\n"
    mock_result.stderr = "warn\n"

    with (
        patch("obi_one.utils.process.subprocess.run", return_value=mock_result) as mock_run,
        caplog.at_level(logging.DEBUG),
    ):
        result = test_module.run_and_log(["echo", "hello"], cwd=tmp_path)

    # subprocess called correctly
    mock_run.assert_called_once_with(
        ["echo", "hello"],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
        cwd=tmp_path,
    )

    # return value
    assert result == mock_result

    # logs
    assert "Command: echo hello" in caplog.text
    assert "stdout: hello" in caplog.text
    assert "stderr: warn" in caplog.text


def test_run_success_no_output(tmp_path, caplog):
    mock_result = Mock()
    mock_result.stdout = ""
    mock_result.stderr = ""

    with (
        patch("obi_one.utils.process.subprocess.run", return_value=mock_result),
        caplog.at_level(logging.DEBUG),
    ):
        test_module.run_and_log(["echo", "hi"], cwd=tmp_path)

    # should log command but no stdout/stderr logs
    assert "Command: echo hi" in caplog.text
    assert "stdout:" not in caplog.text
    assert "stderr:" not in caplog.text


def test_run_failure_logs_and_raises(caplog):
    error = CalledProcessError(
        returncode=1,
        cmd=["false"],
        output="out\n",
        stderr="err\n",
    )

    with (
        patch("obi_one.utils.process.subprocess.run", side_effect=error),
        caplog.at_level(logging.ERROR),
        pytest.raises(CalledProcessError),
    ):
        test_module.run_and_log(["false"])

    assert "Return code: 1" in caplog.text
    assert "stdout: out" in caplog.text
    assert "stderr: err" in caplog.text


def test_run_failure_no_output_logs(caplog):
    error = CalledProcessError(
        returncode=2,
        cmd=["fail"],
        output="",
        stderr="",
    )

    with (
        patch("obi_one.utils.process.subprocess.run", side_effect=error),
        caplog.at_level(logging.ERROR),
        pytest.raises(CalledProcessError),
    ):
        test_module.run_and_log(["fail"])

    assert "Return code: 2" in caplog.text
    assert "stdout:" not in caplog.text
    assert "stderr:" not in caplog.text
