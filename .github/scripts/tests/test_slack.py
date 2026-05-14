from unittest.mock import MagicMock, patch

import pytest
from slack import cmd_auth_test, cmd_post_message, post_message


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


def test_post_message_sends_correct_payload():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "ts": "1234.5678"}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response) as mock_post:
        ts = post_message(
            token="xoxb-token",
            channel="C0CH1",
            text="hello world",
            username="Pickaroo",
            icon_url="",
            icon_emoji=":kangaroo:",
            thread_ts="",
        )

    assert ts == "1234.5678"
    call_kwargs = mock_post.call_args[1]
    payload = call_kwargs["json"]
    assert payload["channel"] == "C0CH1"
    assert payload["markdown_text"] == "hello world"
    assert payload["username"] == "Pickaroo"
    assert payload["icon_emoji"] == ":kangaroo:"
    assert "icon_url" not in payload
    assert "thread_ts" not in payload


def test_post_message_prefers_icon_url_over_emoji():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "ts": "1234.5678"}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response) as mock_post:
        post_message(
            token="xoxb-token",
            channel="C0CH1",
            text="hi",
            username="",
            icon_url="https://example.com/avatar.png",
            icon_emoji=":kangaroo:",
            thread_ts="",
        )

    payload = mock_post.call_args[1]["json"]
    assert payload["icon_url"] == "https://example.com/avatar.png"
    assert "icon_emoji" not in payload


def test_post_message_includes_thread_ts_when_provided():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "ts": "9999.0000"}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response) as mock_post:
        post_message(
            token="xoxb-token",
            channel="C0CH1",
            text="thread reply",
            username="",
            icon_url="",
            icon_emoji="",
            thread_ts="1234.5678",
        )

    payload = mock_post.call_args[1]["json"]
    assert payload["thread_ts"] == "1234.5678"


def test_post_message_raises_on_slack_error():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response):
        with pytest.raises(RuntimeError, match="channel_not_found"):
            post_message(
                token="xoxb-token",
                channel="C0CH1",
                text="hello",
                username="",
                icon_url="",
                icon_emoji="",
                thread_ts="",
            )


def test_post_message_converts_literal_newlines():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "ts": "1234.5678"}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response) as mock_post:
        post_message(
            token="xoxb-token",
            channel="C0CH1",
            text="line1\\nline2",
            username="",
            icon_url="",
            icon_emoji="",
            thread_ts="",
        )

    payload = mock_post.call_args[1]["json"]
    assert payload["markdown_text"] == "line1\nline2"


def test_cmd_post_message_writes_ts_to_github_output(tmp_path):
    output_file = tmp_path / "github_output"
    output_file.write_text("")
    env = {
        "TOKEN": "xoxb-token",
        "CHANNEL_ID": "C0CH1",
        "MESSAGE": "hello",
        "USERNAME": "Pickaroo",
        "AVATAR_URL": "",
        "AVATAR_EMOJI": ":kangaroo:",
        "THREAD_TS": "",
        "GITHUB_OUTPUT": str(output_file),
    }
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "ts": "1234.5678"}
    mock_response.raise_for_status.return_value = None

    with (
        patch.dict("os.environ", env, clear=False),
        patch("requests.post", return_value=mock_response),
    ):
        cmd_post_message()

    content = output_file.read_text()
    assert "ts=1234.5678" in content
