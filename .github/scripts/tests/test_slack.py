from unittest.mock import MagicMock, patch

import pytest
from slack import cmd_auth_test


def test_cmd_auth_test_prints_ok_on_valid_token(tmp_path, capsys):
    output_file = tmp_path / "github_output"
    output_file.write_text("")
    env = {
        "TOKEN": "xoxb-valid",
        "GITHUB_OUTPUT": str(output_file),
    }
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True}
    mock_response.raise_for_status.return_value = None

    with (
        patch.dict("os.environ", env, clear=False),
        patch("requests.post", return_value=mock_response),
    ):
        cmd_auth_test()

    captured = capsys.readouterr()
    assert "valid" in captured.out.lower()
    content = output_file.read_text()
    assert "valid=true" in content


def test_cmd_auth_test_exits_1_on_invalid_token(tmp_path):
    output_file = tmp_path / "github_output"
    output_file.write_text("")
    env = {
        "TOKEN": "xoxb-bad",
        "GITHUB_OUTPUT": str(output_file),
    }
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": False, "error": "invalid_auth"}
    mock_response.raise_for_status.return_value = None

    with (
        patch.dict("os.environ", env, clear=False),
        patch("requests.post", return_value=mock_response),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cmd_auth_test()
    assert exc_info.value.code == 1
