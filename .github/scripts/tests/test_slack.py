from unittest.mock import MagicMock, patch

import pytest
from slack import cmd_auth_test, cmd_find_message, cmd_list_users, cmd_post_message, cmd_update_message, find_message, list_users, post_message, update_message


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


def test_update_message_sends_correct_payload():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "ts": "1234.5678"}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response) as mock_post:
        ts = update_message(
            token="xoxb-token",
            channel="C0CH1",
            ts="1234.5678",
            text="updated text",
            username="Pickaroo",
            icon_url="",
            icon_emoji=":kangaroo:",
        )

    assert ts == "1234.5678"
    payload = mock_post.call_args[1]["json"]
    assert payload["channel"] == "C0CH1"
    assert payload["ts"] == "1234.5678"
    assert payload["markdown_text"] == "updated text"
    assert payload["username"] == "Pickaroo"
    assert payload["icon_emoji"] == ":kangaroo:"


def test_update_message_raises_on_slack_error():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": False, "error": "message_not_found"}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response):
        with pytest.raises(RuntimeError, match="message_not_found"):
            update_message(
                token="xoxb-token",
                channel="C0CH1",
                ts="1234.5678",
                text="updated",
                username="",
                icon_url="",
                icon_emoji="",
            )


def test_update_message_converts_literal_newlines():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "ts": "1234.5678"}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response) as mock_post:
        update_message(
            token="xoxb-token",
            channel="C0CH1",
            ts="1234.5678",
            text="line1\\nline2",
            username="",
            icon_url="",
            icon_emoji="",
        )

    payload = mock_post.call_args[1]["json"]
    assert payload["markdown_text"] == "line1\nline2"


def test_cmd_update_message_writes_ts_to_github_output(tmp_path):
    output_file = tmp_path / "github_output"
    output_file.write_text("")
    env = {
        "TOKEN": "xoxb-token",
        "CHANNEL_ID": "C0CH1",
        "MESSAGE_TS": "1234.5678",
        "MESSAGE": "updated",
        "USERNAME": "",
        "AVATAR_URL": "",
        "AVATAR_EMOJI": "",
        "GITHUB_OUTPUT": str(output_file),
    }
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "ts": "1234.5678"}
    mock_response.raise_for_status.return_value = None

    with (
        patch.dict("os.environ", env, clear=False),
        patch("requests.post", return_value=mock_response),
    ):
        cmd_update_message()

    content = output_file.read_text()
    assert "ts=1234.5678" in content


def test_find_message_returns_true_when_message_found():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ok": True,
        "messages": [{"ts": "1234.5678"}],
    }
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        result = find_message(
            token="xoxb-token",
            channel="C0CH1",
            message_ts="1234.5678",
        )

    assert result is True


def test_find_message_returns_false_when_no_messages():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "messages": []}
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        result = find_message(
            token="xoxb-token",
            channel="C0CH1",
            message_ts="1234.5678",
        )

    assert result is False


def test_find_message_returns_false_when_ts_mismatch():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ok": True,
        "messages": [{"ts": "9999.0000"}],
    }
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        result = find_message(
            token="xoxb-token",
            channel="C0CH1",
            message_ts="1234.5678",
        )

    assert result is False


def test_find_message_returns_false_on_api_error():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        result = find_message(
            token="xoxb-token",
            channel="C0CH1",
            message_ts="1234.5678",
        )

    assert result is False


def test_cmd_find_message_exits_1_when_message_not_found(tmp_path):
    env = {
        "TOKEN": "xoxb-token",
        "CHANNEL_ID": "C0CH1",
        "MESSAGE_TS": "1234.5678",
    }
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "messages": []}
    mock_response.raise_for_status.return_value = None

    with (
        patch.dict("os.environ", env, clear=False),
        patch("requests.get", return_value=mock_response),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cmd_find_message()
    assert exc_info.value.code == 1


def test_cmd_find_message_succeeds_when_message_found(capsys):
    env = {
        "TOKEN": "xoxb-token",
        "CHANNEL_ID": "C0CH1",
        "MESSAGE_TS": "1234.5678",
    }
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ok": True,
        "messages": [{"ts": "1234.5678"}],
    }
    mock_response.raise_for_status.return_value = None

    with (
        patch.dict("os.environ", env, clear=False),
        patch("requests.get", return_value=mock_response),
    ):
        cmd_find_message()

    captured = capsys.readouterr()
    assert "Found" in captured.out


def test_list_users_returns_active_user_ids():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ok": True,
        "members": [
            {"id": "U001", "deleted": False, "is_bot": False, "name": "alice"},
            {"id": "U002", "deleted": True, "is_bot": False, "name": "deleted-user"},
            {"id": "U003", "deleted": False, "is_bot": True, "name": "bot-user"},
            {"id": "U004", "deleted": False, "is_bot": False, "name": "slackbot"},
            {"id": "U005", "deleted": False, "is_bot": False, "name": "bob"},
        ],
        "response_metadata": {"next_cursor": ""},
    }
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        result = list_users(token="xoxb-token")

    assert result == ["U001", "U005"]


def test_list_users_paginates():
    page1 = MagicMock()
    page1.json.return_value = {
        "ok": True,
        "members": [
            {"id": "U001", "deleted": False, "is_bot": False, "name": "alice"},
        ],
        "response_metadata": {"next_cursor": "cursor123"},
    }
    page1.raise_for_status.return_value = None

    page2 = MagicMock()
    page2.json.return_value = {
        "ok": True,
        "members": [
            {"id": "U002", "deleted": False, "is_bot": False, "name": "bob"},
        ],
        "response_metadata": {"next_cursor": ""},
    }
    page2.raise_for_status.return_value = None

    with patch("requests.get", side_effect=[page1, page2]) as mock_get:
        result = list_users(token="xoxb-token")

    assert result == ["U001", "U002"]
    assert mock_get.call_count == 2


def test_list_users_raises_on_api_error():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": False, "error": "invalid_auth"}
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(RuntimeError, match="invalid_auth"):
            list_users(token="xoxb-token")


def test_cmd_list_users_writes_json_array_to_github_output(tmp_path):
    output_file = tmp_path / "github_output"
    output_file.write_text("")
    env = {
        "TOKEN": "xoxb-token",
        "GITHUB_OUTPUT": str(output_file),
    }
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ok": True,
        "members": [
            {"id": "U001", "deleted": False, "is_bot": False, "name": "alice"},
            {"id": "U002", "deleted": False, "is_bot": False, "name": "bob"},
        ],
        "response_metadata": {"next_cursor": ""},
    }
    mock_response.raise_for_status.return_value = None

    with (
        patch.dict("os.environ", env, clear=False),
        patch("requests.get", return_value=mock_response),
    ):
        cmd_list_users()

    content = output_file.read_text()
    assert 'user_ids=["U001", "U002"]' in content
