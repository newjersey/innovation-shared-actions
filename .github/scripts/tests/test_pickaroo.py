# Tests for .github/scripts/pickaroo.py

from pickaroo import parse_pickaroo_comment


def test_parse_pickaroo_comment_extracts_message_ts():
    body = (
        "Pickaroo selected and notified reviewers for this PR! 🦘\n\n"
        "message_ts: 1234567890.123456\n"
        "previously_picked: alice bob"
    )
    result = parse_pickaroo_comment(body)
    assert result["message_ts"] == "1234567890.123456"


def test_parse_pickaroo_comment_extracts_previously_picked():
    body = (
        "Pickaroo selected and notified reviewers for this PR! 🦘\n\n"
        "message_ts: 1234567890.123456\n"
        "previously_picked: alice bob carol"
    )
    result = parse_pickaroo_comment(body)
    assert result["previously_picked"] == "alice bob carol"


def test_parse_pickaroo_comment_returns_empty_on_no_match():
    result = parse_pickaroo_comment("some unrelated comment body")
    assert result == {}


from pickaroo import deduplicate_reviewers


def test_deduplicate_reviewers_merges_and_deduplicates():
    result = deduplicate_reviewers("alice bob", "bob carol")
    assert result == ["alice", "bob", "carol"]


def test_deduplicate_reviewers_preserves_insertion_order():
    result = deduplicate_reviewers("charlie alice", "bob alice")
    assert result == ["charlie", "alice", "bob"]


def test_deduplicate_reviewers_handles_empty_previously_picked():
    result = deduplicate_reviewers("", "alice bob")
    assert result == ["alice", "bob"]


def test_deduplicate_reviewers_handles_empty_new_reviewers():
    result = deduplicate_reviewers("alice bob", "")
    assert result == ["alice", "bob"]


def test_deduplicate_reviewers_handles_both_empty():
    result = deduplicate_reviewers("", "")
    assert result == []


from pickaroo import build_comment_body


def test_build_comment_body_includes_message_ts():
    result = build_comment_body("1234567890.123456", "alice bob")
    assert "message_ts: 1234567890.123456" in result


def test_build_comment_body_includes_previously_picked():
    result = build_comment_body("1234567890.123456", "alice bob carol")
    assert "previously_picked: alice bob carol" in result


def test_build_comment_body_includes_kangaroo_emoji():
    result = build_comment_body("1234567890.123456", "alice")
    assert "🦘" in result


from pickaroo import build_main_message


def test_build_main_message_includes_pr_url():
    result = build_main_message(
        pr_url="https://github.com/org/repo/pull/42",
        pr_type="Review",
        repo_name="my-repo",
        pr_number="42",
        author_mention="<@U123>",
        pr_title="Fix the bug",
        current_reviewer_mentions="",
    )
    assert "https://github.com/org/repo/pull/42" in result


def test_build_main_message_includes_repo_pr_author_title():
    result = build_main_message(
        pr_url="https://github.com/org/repo/pull/42",
        pr_type="Review",
        repo_name="my-repo",
        pr_number="42",
        author_mention="<@U123>",
        pr_title="Fix the bug",
        current_reviewer_mentions="",
    )
    assert "my-repo" in result
    assert "#42" in result
    assert "<@U123>" in result
    assert "Fix the bug" in result


def test_build_main_message_omits_reviewers_when_empty():
    result = build_main_message(
        pr_url="https://github.com/org/repo/pull/42",
        pr_type="Review",
        repo_name="my-repo",
        pr_number="42",
        author_mention="<@U123>",
        pr_title="Fix the bug",
        current_reviewer_mentions="",
    )
    assert "Reviewers:" not in result


def test_build_main_message_includes_reviewers_when_present():
    result = build_main_message(
        pr_url="https://github.com/org/repo/pull/42",
        pr_type="Review",
        repo_name="my-repo",
        pr_number="42",
        author_mention="<@U123>",
        pr_title="Fix the bug",
        current_reviewer_mentions="<@U456>, <@U789>",
    )
    assert "Reviewers: <@U456>, <@U789>" in result


def test_build_main_message_uses_literal_newlines():
    """Message uses literal \\n (two chars), not actual newlines, for slack-message action compatibility."""
    result = build_main_message(
        pr_url="https://github.com/org/repo/pull/1",
        pr_type="Review",
        repo_name="repo",
        pr_number="1",
        author_mention="@user",
        pr_title="My PR",
        current_reviewer_mentions="",
    )
    assert "\\n" in result
    assert "\n" not in result


def test_build_main_message_show_type():
    result = build_main_message(
        pr_url="https://github.com/org/repo/pull/1",
        pr_type="Show",
        repo_name="repo",
        pr_number="1",
        author_mention="@user",
        pr_title="My PR",
        current_reviewer_mentions="",
    )
    assert "PR Show" in result


from pickaroo import build_thread_message


def test_build_thread_message_mentions_reviewers_when_present():
    result = build_thread_message(
        new_reviewer_mentions="<@U123> <@U456>",
        pr_author_mention="<@U789>",
        repository="org/repo",
        run_id="12345",
    )
    assert "<@U123> <@U456>" in result
    assert "review" in result.lower()


def test_build_thread_message_apology_when_no_reviewers():
    result = build_thread_message(
        new_reviewer_mentions="",
        pr_author_mention="<@U789>",
        repository="org/repo",
        run_id="12345",
    )
    assert "<@U789>" in result
    assert "https://github.com/org/repo/actions/runs/12345" in result


def test_build_thread_message_apology_does_not_mention_reviewers():
    result = build_thread_message(
        new_reviewer_mentions="",
        pr_author_mention="<@U789>",
        repository="org/repo",
        run_id="12345",
    )
    assert "Hey " not in result


import pytest
import requests
from unittest.mock import patch, MagicMock
from pickaroo import get_pr_comments, post_pr_comment, patch_pr_comment


def test_get_pr_comments_returns_parsed_list():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"id": 1, "body": "hello"}]
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response) as mock_get:
        result = get_pr_comments("org/repo", "42", "token123")

    assert result == [{"id": 1, "body": "hello"}]
    url = mock_get.call_args[0][0]
    assert "org/repo" in url
    assert "42" in url


def test_get_pr_comments_raises_on_non_200():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(requests.HTTPError):
            get_pr_comments("org/repo", "42", "token123")


def test_post_pr_comment_sends_correct_payload():
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": 99}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response) as mock_post:
        result = post_pr_comment("org/repo", "42", "token123", "hello world")

    assert result == {"id": 99}
    assert mock_post.call_args[1]["json"] == {"body": "hello world"}


def test_post_pr_comment_raises_on_error_response():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("422")

    with patch("requests.post", return_value=mock_response):
        with pytest.raises(requests.HTTPError):
            post_pr_comment("org/repo", "42", "token123", "body")


def test_patch_pr_comment_sends_correct_payload():
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": 55}
    mock_response.raise_for_status.return_value = None

    with patch("requests.patch", return_value=mock_response) as mock_patch:
        result = patch_pr_comment("org/repo", "55", "token123", "updated body")

    assert result == {"id": 55}
    assert mock_patch.call_args[1]["json"] == {"body": "updated body"}
    url = mock_patch.call_args[0][0]
    assert "55" in url


from pickaroo import cmd_find_comment


def test_find_comment_writes_outputs_when_comment_found(tmp_path):
    output_file = tmp_path / "github_output"
    output_file.write_text("")

    comments = [
        {"id": 101, "body": "unrelated comment"},
        {
            "id": 202,
            "body": (
                "Pickaroo selected and notified reviewers for this PR! 🦘\n\n"
                "message_ts: 1234567890.654321\n"
                "previously_picked: alice bob"
            ),
        },
    ]
    mock_response = MagicMock()
    mock_response.json.return_value = comments
    mock_response.raise_for_status.return_value = None

    env = {
        "GITHUB_TOKEN": "tok",
        "GITHUB_REPOSITORY": "org/repo",
        "PR_NUMBER": "7",
        "GITHUB_OUTPUT": str(output_file),
    }
    with patch("requests.get", return_value=mock_response):
        with patch.dict("os.environ", env, clear=False):
            cmd_find_comment()

    content = output_file.read_text()
    assert "message-ts=1234567890.654321" in content
    assert "comment-id=202" in content
    assert "previously-picked=alice bob" in content


def test_find_comment_writes_nothing_when_no_pickaroo_comment(tmp_path):
    output_file = tmp_path / "github_output"
    output_file.write_text("")

    mock_response = MagicMock()
    mock_response.json.return_value = [{"id": 1, "body": "hello"}]
    mock_response.raise_for_status.return_value = None

    env = {
        "GITHUB_TOKEN": "tok",
        "GITHUB_REPOSITORY": "org/repo",
        "PR_NUMBER": "7",
        "GITHUB_OUTPUT": str(output_file),
    }
    with patch("requests.get", return_value=mock_response):
        with patch.dict("os.environ", env, clear=False):
            cmd_find_comment()

    content = output_file.read_text()
    assert content == ""


from unittest.mock import patch
from pickaroo import cmd_build_messages


def _build_messages_env(tmp_path, overrides=None):
    github_env = tmp_path / "github_env"
    github_env.write_text("")
    base = {
        "GITHUB_ENV": str(github_env),
        "REVIEWERS": "alice",
        "NEW_REVIEWER_MENTIONS": "<@U123>",
        "CURRENT_REVIEWER_MENTIONS": "<@U123>",
        "AUTHOR_MENTION": "<@U999>",
        "PR_URL": "https://github.com/org/repo/pull/1",
        "PR_NUMBER": "1",
        "PR_TITLE": "Fix the bug",
        "SHOW": "false",
        "GITHUB_REPOSITORY": "org/repo",
        "GITHUB_RUN_ID": "555",
    }
    if overrides:
        base.update(overrides)
    return github_env, base


def test_build_messages_writes_message_to_github_env(tmp_path):
    github_env, env = _build_messages_env(tmp_path)
    with patch.dict("os.environ", env, clear=False):
        cmd_build_messages()
    content = github_env.read_text()
    assert "MESSAGE=" in content
    assert "Fix the bug" in content


def test_build_messages_writes_thread_message_when_reviewers_found(tmp_path):
    github_env, env = _build_messages_env(tmp_path)
    with patch.dict("os.environ", env, clear=False):
        cmd_build_messages()
    content = github_env.read_text()
    assert "THREAD_MESSAGE=" in content
    assert "<@U123>" in content


def test_build_messages_skips_thread_message_in_show_mode(tmp_path):
    github_env, env = _build_messages_env(tmp_path, {"SHOW": "true", "REVIEWERS": ""})
    with patch.dict("os.environ", env, clear=False):
        cmd_build_messages()
    content = github_env.read_text()
    assert "THREAD_MESSAGE=\n" in content


def test_build_messages_pr_type_is_show_when_show_true(tmp_path):
    github_env, env = _build_messages_env(tmp_path, {"SHOW": "true"})
    with patch.dict("os.environ", env, clear=False):
        cmd_build_messages()
    content = github_env.read_text()
    assert "PR Show" in content


def test_build_messages_pr_title_with_special_chars_does_not_break(tmp_path):
    """Regression: PR titles with quotes and backticks must not corrupt GITHUB_ENV."""
    title = """It's a "test" with `backticks` and $dollar"""
    github_env, env = _build_messages_env(tmp_path, {"PR_TITLE": title})
    with patch.dict("os.environ", env, clear=False):
        cmd_build_messages()
    content = github_env.read_text()
    assert title in content


from unittest.mock import patch, MagicMock
from pickaroo import cmd_post_comment


def _post_comment_env(overrides=None):
    base = {
        "GITHUB_TOKEN": "tok",
        "GITHUB_REPOSITORY": "org/repo",
        "PR_NUMBER": "7",
        "REVIEWERS": "carol",
        "PREVIOUSLY_PICKED": "alice bob",
        "MESSAGE_TS": "1234567890.654321",
        "COMMENT_ID": "",
    }
    if overrides:
        base.update(overrides)
    return base


def test_post_comment_posts_new_comment_when_no_comment_id():
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": 300}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response) as mock_post:
        with patch.dict("os.environ", _post_comment_env(), clear=False):
            cmd_post_comment()

    mock_post.assert_called_once()
    body = mock_post.call_args[1]["json"]["body"]
    assert "previously_picked: alice bob carol" in body
    assert "message_ts: 1234567890.654321" in body


def test_post_comment_patches_existing_comment_when_comment_id_present():
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": 99}
    mock_response.raise_for_status.return_value = None

    env = _post_comment_env({"COMMENT_ID": "99"})
    with patch("requests.patch", return_value=mock_response) as mock_patch:
        with patch.dict("os.environ", env, clear=False):
            cmd_post_comment()

    mock_patch.assert_called_once()
    url = mock_patch.call_args[0][0]
    assert "99" in url


def test_post_comment_deduplicates_reviewers():
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": 1}
    mock_response.raise_for_status.return_value = None

    # alice is in both previously_picked and new reviewers
    env = _post_comment_env({"PREVIOUSLY_PICKED": "alice bob", "REVIEWERS": "alice carol"})
    with patch("requests.post", return_value=mock_response) as mock_post:
        with patch.dict("os.environ", env, clear=False):
            cmd_post_comment()

    body = mock_post.call_args[1]["json"]["body"]
    assert body.count("alice") == 1
    assert "carol" in body
    assert "bob" in body
