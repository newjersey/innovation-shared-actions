from unittest.mock import MagicMock, patch

import pytest
import requests
from pickaroo import (
    _next_page,
    build_candidate_pool,
    build_comment_body,
    build_main_message,
    build_thread_message,
    cmd_build_messages,
    cmd_find_comment,
    cmd_post_comment,
    cmd_select_reviewers,
    count_valid_existing,
    deduplicate_reviewers,
    filter_ooo_candidates,
    get_collaborators,
    get_pr_comments,
    get_pr_reviews,
    get_requested_reviewers,
    get_slack_status,
    get_team_members,
    is_ooo,
    parse_pickaroo_comment,
    patch_pr_comment,
    post_pr_comment,
    request_reviewers,
    validate_slack_token,
)


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


def test_build_comment_body_includes_message_ts():
    result = build_comment_body("1234567890.123456", "alice bob")
    assert "message_ts: 1234567890.123456" in result


def test_build_comment_body_includes_previously_picked():
    result = build_comment_body("1234567890.123456", "alice bob carol")
    assert "previously_picked: alice bob carol" in result


def test_build_comment_body_includes_kangaroo_emoji():
    result = build_comment_body("1234567890.123456", "alice")
    assert "🦘" in result


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


def test_next_page_extracts_url_from_link_header():
    link = '<https://api.github.com/repos/org/repo/issues/42/comments?page=2>; rel="next", <https://api.github.com/repos/org/repo/issues/42/comments?page=5>; rel="last"'
    assert _next_page(link) == "https://api.github.com/repos/org/repo/issues/42/comments?page=2"


def test_next_page_returns_empty_when_no_next():
    link = '<https://api.github.com/repos/org/repo/issues/42/comments?page=5>; rel="last"'
    assert _next_page(link) == ""


def test_next_page_returns_empty_on_empty_header():
    assert _next_page("") == ""


def test_get_pr_comments_returns_parsed_list():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"id": 1, "body": "hello"}]
    mock_response.raise_for_status.return_value = None
    mock_response.headers = {"Link": ""}

    with patch("requests.get", return_value=mock_response) as mock_get:
        result = get_pr_comments("org/repo", "42", "token123")

    assert result == [{"id": 1, "body": "hello"}]
    url = mock_get.call_args[0][0]
    assert "org/repo" in url
    assert "42" in url
    kwargs = mock_get.call_args[1]
    assert kwargs["params"] == {"per_page": 100}


def test_get_pr_comments_follows_pagination():
    page1 = MagicMock()
    page1.json.return_value = [{"id": 1, "body": "first"}]
    page1.raise_for_status.return_value = None
    page1.headers = {"Link": '<https://api.github.com/next?page=2>; rel="next"'}

    page2 = MagicMock()
    page2.json.return_value = [{"id": 2, "body": "second"}]
    page2.raise_for_status.return_value = None
    page2.headers = {"Link": ""}

    with patch("requests.get", side_effect=[page1, page2]) as mock_get:
        result = get_pr_comments("org/repo", "42", "token123")

    assert result == [{"id": 1, "body": "first"}, {"id": 2, "body": "second"}]
    assert mock_get.call_count == 2
    # Second call uses the Link next URL directly with no extra params
    second_call_url = mock_get.call_args_list[1][0][0]
    assert second_call_url == "https://api.github.com/next?page=2"
    assert mock_get.call_args_list[1][1]["params"] == {}


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
    env = _post_comment_env(
        {"PREVIOUSLY_PICKED": "alice bob", "REVIEWERS": "alice carol"}
    )
    with patch("requests.post", return_value=mock_response) as mock_post:
        with patch.dict("os.environ", env, clear=False):
            cmd_post_comment()

    body = mock_post.call_args[1]["json"]["body"]
    assert body.count("alice") == 1
    assert "carol" in body
    assert "bob" in body


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def test_get_team_members_returns_logins():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"login": "alice"}, {"login": "bob"}]
    mock_response.raise_for_status.return_value = None
    mock_response.headers = {"Link": ""}

    with patch("requests.get", return_value=mock_response) as mock_get:
        result = get_team_members("myorg", "my-team", "tok")

    assert result == ["alice", "bob"]
    url = mock_get.call_args[0][0]
    assert "myorg/teams/my-team/members" in url


def test_get_team_members_paginates():
    page1 = MagicMock()
    page1.json.return_value = [{"login": "alice"}]
    page1.raise_for_status.return_value = None
    page1.headers = {"Link": '<https://api.github.com/next?page=2>; rel="next"'}

    page2 = MagicMock()
    page2.json.return_value = [{"login": "bob"}]
    page2.raise_for_status.return_value = None
    page2.headers = {"Link": ""}

    with patch("requests.get", side_effect=[page1, page2]):
        result = get_team_members("myorg", "my-team", "tok")

    assert result == ["alice", "bob"]


def test_get_collaborators_returns_logins():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"login": "carol"}, {"login": "dave"}]
    mock_response.raise_for_status.return_value = None
    mock_response.headers = {"Link": ""}

    with patch("requests.get", return_value=mock_response) as mock_get:
        result = get_collaborators("org/repo", "tok")

    assert result == ["carol", "dave"]
    url = mock_get.call_args[0][0]
    assert "org/repo/collaborators" in url


def test_get_collaborators_paginates():
    page1 = MagicMock()
    page1.json.return_value = [{"login": "carol"}]
    page1.raise_for_status.return_value = None
    page1.headers = {"Link": '<https://api.github.com/next?page=2>; rel="next"'}

    page2 = MagicMock()
    page2.json.return_value = [{"login": "dave"}]
    page2.raise_for_status.return_value = None
    page2.headers = {"Link": ""}

    with patch("requests.get", side_effect=[page1, page2]):
        result = get_collaborators("org/repo", "tok")

    assert result == ["carol", "dave"]


def test_get_requested_reviewers_returns_user_logins():
    mock_response = MagicMock()
    mock_response.json.return_value = {"users": [{"login": "alice"}, {"login": "bob"}], "teams": []}
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response) as mock_get:
        result = get_requested_reviewers("org/repo", "42", "tok")

    assert result == ["alice", "bob"]
    url = mock_get.call_args[0][0]
    assert "org/repo/pulls/42/requested_reviewers" in url


def test_get_requested_reviewers_returns_empty_when_no_users():
    mock_response = MagicMock()
    mock_response.json.return_value = {"users": [], "teams": []}
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        result = get_requested_reviewers("org/repo", "42", "tok")

    assert result == []


def test_get_pr_reviews_returns_unique_reviewer_logins():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"user": {"login": "alice"}},
        {"user": {"login": "bob"}},
    ]
    mock_response.raise_for_status.return_value = None
    mock_response.headers = {}

    with patch("requests.get", return_value=mock_response) as mock_get:
        result = get_pr_reviews("org/repo", "42", "tok")

    assert result == ["alice", "bob"]
    url = mock_get.call_args[0][0]
    assert "org/repo/pulls/42/reviews" in url


def test_get_pr_reviews_deduplicates_multiple_reviews_from_same_user():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"user": {"login": "alice"}},
        {"user": {"login": "bob"}},
        {"user": {"login": "alice"}},  # alice reviewed again
    ]
    mock_response.raise_for_status.return_value = None
    mock_response.headers = {}

    with patch("requests.get", return_value=mock_response):
        result = get_pr_reviews("org/repo", "42", "tok")

    assert result == ["alice", "bob"]


def test_request_reviewers_posts_correct_payload():
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": 1}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response) as mock_post:
        result = request_reviewers("org/repo", "42", "tok", ["alice", "bob"])

    assert mock_post.call_args[1]["json"] == {"reviewers": ["alice", "bob"]}
    url = mock_post.call_args[0][0]
    assert "org/repo/pulls/42/requested_reviewers" in url


# ---------------------------------------------------------------------------
# Slack helpers
# ---------------------------------------------------------------------------

def test_is_ooo_returns_false_for_empty_status():
    assert is_ooo("", "") is False


def test_is_ooo_returns_true_for_ooo_text():
    assert is_ooo("out of office", "") is True


def test_is_ooo_returns_true_for_ooo_emoji():
    assert is_ooo("", ":palm_tree:") is True
    assert is_ooo("", ":thermometer:") is True
    assert is_ooo("", ":face_with_medical_mask:") is True
    assert is_ooo("", ":face_vomiting:") is True
    assert is_ooo("", ":airplane:") is True
    assert is_ooo("", ":beach_with_umbrella:") is True


def test_is_ooo_returns_true_for_vacation():
    assert is_ooo("vacation time!", "") is True


def test_is_ooo_returns_true_for_sick():
    assert is_ooo("sick day", ":thermometer:") is True


def test_is_ooo_returns_false_for_future_ooo():
    """Future OOO indicators are treated as currently available."""
    assert is_ooo("upcoming vacation", ":crystal_ball:") is False


def test_is_ooo_is_case_insensitive():
    assert is_ooo("OOO", "") is True
    assert is_ooo("Vacation", "") is True


def test_is_ooo_no_false_positive_on_substring():
    assert is_ooo("fluent in Python", "") is False
    assert is_ooo("unmasked", "") is False
    assert is_ooo("leaves of absence", "") is False


def test_get_slack_status_returns_text_and_emoji():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ok": True,
        "profile": {"status_text": "on vacation", "status_emoji": ":palm_tree:"},
    }
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response) as mock_get:
        text, emoji = get_slack_status("U123", "slack-token")

    assert text == "on vacation"
    assert emoji == ":palm_tree:"
    assert "U123" in str(mock_get.call_args)


def test_get_slack_status_returns_empty_strings_when_no_profile():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "profile": {}}
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        text, emoji = get_slack_status("U123", "slack-token")

    assert text == ""
    assert emoji == ""


def test_validate_slack_token_returns_true_on_ok():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response):
        assert validate_slack_token("slack-token") is True


def test_validate_slack_token_returns_false_when_not_ok():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": False, "error": "invalid_auth"}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response):
        assert validate_slack_token("bad-token") is False


# ---------------------------------------------------------------------------
# Selection logic
# ---------------------------------------------------------------------------

def test_count_valid_existing_counts_valid_reviewers():
    result = count_valid_existing(
        requested=["alice", "bob"],
        reviewed=[],
        include_set={"alice", "bob", "carol"},
        exclude_set=set(),
        collaborators_set={"alice", "bob", "carol"},
        author="dave",
    )
    assert result == 2


def test_count_valid_existing_excludes_reviewer_in_exclude_set():
    result = count_valid_existing(
        requested=["alice", "bob"],
        reviewed=[],
        include_set={"alice", "bob"},
        exclude_set={"alice"},
        collaborators_set={"alice", "bob"},
        author="dave",
    )
    assert result == 1


def test_count_valid_existing_excludes_pr_author():
    result = count_valid_existing(
        requested=["alice", "dave"],
        reviewed=[],
        include_set={"alice", "dave"},
        exclude_set=set(),
        collaborators_set={"alice", "dave"},
        author="dave",
    )
    assert result == 1


def test_count_valid_existing_excludes_non_collaborators():
    result = count_valid_existing(
        requested=["alice", "bob"],
        reviewed=[],
        include_set={"alice", "bob"},
        exclude_set=set(),
        collaborators_set={"alice"},  # bob is not a collaborator
        author="dave",
    )
    assert result == 1


def test_count_valid_existing_excludes_reviewer_not_in_include_set():
    result = count_valid_existing(
        requested=["alice", "external-user"],
        reviewed=[],
        include_set={"alice"},
        exclude_set=set(),
        collaborators_set={"alice", "external-user"},
        author="dave",
    )
    assert result == 1


def test_count_valid_existing_returns_zero_for_empty_requested():
    result = count_valid_existing(
        requested=[],
        reviewed=[],
        include_set={"alice", "bob"},
        exclude_set=set(),
        collaborators_set={"alice", "bob"},
        author="dave",
    )
    assert result == 0


def test_count_valid_existing_counts_reviewed_users():
    """Users who have already submitted a review count as existing reviewers."""
    result = count_valid_existing(
        requested=[],
        reviewed=["alice", "bob"],
        include_set={"alice", "bob", "carol"},
        exclude_set=set(),
        collaborators_set={"alice", "bob", "carol"},
        author="dave",
    )
    assert result == 2


def test_count_valid_existing_deduplicates_requested_and_reviewed():
    """A user who is both requested and reviewed counts only once."""
    result = count_valid_existing(
        requested=["alice"],
        reviewed=["alice", "bob"],
        include_set={"alice", "bob"},
        exclude_set=set(),
        collaborators_set={"alice", "bob"},
        author="dave",
    )
    assert result == 2


def test_build_candidate_pool_returns_valid_candidates():
    result = build_candidate_pool(
        include_set={"alice", "bob", "carol"},
        exclude_set=set(),
        collaborators_set={"alice", "bob", "carol"},
        author="dave",
        already_requested=["alice"],
        already_reviewed=[],
    )
    assert set(result) == {"bob", "carol"}


def test_build_candidate_pool_excludes_author():
    result = build_candidate_pool(
        include_set={"alice", "dave"},
        exclude_set=set(),
        collaborators_set={"alice", "dave"},
        author="dave",
        already_requested=[],
        already_reviewed=[],
    )
    assert "dave" not in result


def test_build_candidate_pool_excludes_non_collaborators():
    result = build_candidate_pool(
        include_set={"alice", "bob"},
        exclude_set=set(),
        collaborators_set={"alice"},
        author="dave",
        already_requested=[],
        already_reviewed=[],
    )
    # Set iteration order is non-deterministic; use set comparison
    assert set(result) == {"alice"}


def test_build_candidate_pool_excludes_already_requested():
    result = build_candidate_pool(
        include_set={"alice", "bob", "carol"},
        exclude_set=set(),
        collaborators_set={"alice", "bob", "carol"},
        author="dave",
        already_requested=["bob", "carol"],
        already_reviewed=[],
    )
    assert set(result) == {"alice"}


def test_build_candidate_pool_excludes_already_reviewed():
    """Users who already submitted a review are not candidates for re-request."""
    result = build_candidate_pool(
        include_set={"alice", "bob", "carol"},
        exclude_set=set(),
        collaborators_set={"alice", "bob", "carol"},
        author="dave",
        already_requested=[],
        already_reviewed=["bob", "carol"],
    )
    assert set(result) == {"alice"}


def test_build_candidate_pool_returns_empty_when_all_filtered():
    result = build_candidate_pool(
        include_set={"alice"},
        exclude_set={"alice"},
        collaborators_set={"alice"},
        author="dave",
        already_requested=[],
        already_reviewed=[],
    )
    assert result == []


def test_filter_ooo_candidates_includes_user_not_in_mapping():
    result = filter_ooo_candidates(["alice"], {}, "slack-tok")
    assert result == ["alice"]


def test_filter_ooo_candidates_includes_available_user():
    with patch("pickaroo.get_slack_status", return_value=("", "")):
        result = filter_ooo_candidates(["alice"], {"alice": "U123"}, "slack-tok")
    assert result == ["alice"]


def test_filter_ooo_candidates_excludes_ooo_user():
    with patch("pickaroo.get_slack_status", return_value=("on vacation", ":palm_tree:")):
        result = filter_ooo_candidates(["alice"], {"alice": "U123"}, "slack-tok")
    assert result == []


def test_filter_ooo_candidates_includes_user_on_api_failure(capsys):
    with patch("pickaroo.get_slack_status", side_effect=Exception("network error")):
        result = filter_ooo_candidates(["alice"], {"alice": "U123"}, "slack-tok")
    assert result == ["alice"]
    assert "WARNING" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_select_reviewers
# ---------------------------------------------------------------------------


def _select_reviewers_env(tmp_path, overrides=None):
    """Base env for cmd_select_reviewers tests."""
    github_output = tmp_path / "github_output"
    github_output.write_text("")
    base = {
        "GITHUB_TOKEN": "tok",
        "GITHUB_REPOSITORY": "org/repo",
        "GH_PR_NUMBER": "42",
        "GH_PR_AUTHOR": "author",
        "GH_INCLUDE_TEAMS": "",
        "GH_INCLUDE_USERS": "alice bob carol",
        "GH_EXCLUDE_TEAMS": "",
        "GH_EXCLUDE_USERS": "",
        "GH_NUMBER_OF_REVIEWERS": "2",
        "GH_NUMBER_OF_REPICKS": "1",
        "GH_SLACK_USER_MAP": "",
        "SLACK_TOKEN": "",
        "GITHUB_OUTPUT": str(github_output),
    }
    if overrides:
        base.update(overrides)
    return github_output, base


def test_cmd_select_reviewers_picks_needed_reviewers(tmp_path):
    github_output, env = _select_reviewers_env(tmp_path)

    with patch.dict("os.environ", env, clear=False):
        with patch("pickaroo.get_collaborators", return_value=["alice", "bob", "carol", "dave"]):
            with patch("pickaroo.get_requested_reviewers", return_value=[]):
                with patch("pickaroo.get_pr_reviews", return_value=[]):
                    with patch("pickaroo.request_reviewers") as mock_request:
                        cmd_select_reviewers()

    content = github_output.read_text()
    assert "reviewers=" in content
    # 2 reviewers should be picked
    picked = content.split("reviewers=")[1].strip().split()
    assert len(picked) == 2
    assert all(r in {"alice", "bob", "carol"} for r in picked)
    mock_request.assert_called_once()


def test_cmd_select_reviewers_picks_one_more_when_slots_filled(tmp_path):
    """When valid_existing >= n, picks exactly 1 additional reviewer."""
    github_output, env = _select_reviewers_env(tmp_path, {
        "GH_INCLUDE_USERS": "alice bob carol",
        "GH_NUMBER_OF_REVIEWERS": "2",
    })

    with patch.dict("os.environ", env, clear=False):
        with patch("pickaroo.get_collaborators", return_value=["alice", "bob", "carol"]):
            with patch("pickaroo.get_requested_reviewers", return_value=["alice", "bob"]):
                with patch("pickaroo.get_pr_reviews", return_value=[]):
                    with patch("pickaroo.request_reviewers") as mock_request:
                        cmd_select_reviewers()

    mock_request.assert_called_once()
    picked = mock_request.call_args[0][3]
    assert len(picked) == 1
    assert picked[0] == "carol"


def test_cmd_select_reviewers_counts_already_reviewed(tmp_path):
    """Users who have already reviewed count toward valid_existing."""
    github_output, env = _select_reviewers_env(tmp_path, {
        "GH_INCLUDE_USERS": "alice bob carol dave",
        "GH_NUMBER_OF_REVIEWERS": "2",
    })

    with patch.dict("os.environ", env, clear=False):
        with patch("pickaroo.get_collaborators", return_value=["alice", "bob", "carol", "dave"]):
            with patch("pickaroo.get_requested_reviewers", return_value=["alice"]):
                with patch("pickaroo.get_pr_reviews", return_value=["bob"]):
                    with patch("pickaroo.request_reviewers") as mock_request:
                        cmd_select_reviewers()

    # alice (requested) + bob (reviewed) = 2 valid existing = slots filled → picks 1 more
    mock_request.assert_called_once()
    picked = mock_request.call_args[0][3]
    assert len(picked) == 1
    assert picked[0] in {"carol", "dave"}


def test_cmd_select_reviewers_reviewed_not_in_candidate_pool(tmp_path):
    """Users who have already reviewed are excluded from candidate selection."""
    github_output, env = _select_reviewers_env(tmp_path, {
        "GH_INCLUDE_USERS": "alice bob carol",
        "GH_NUMBER_OF_REVIEWERS": "1",
    })

    with patch.dict("os.environ", env, clear=False):
        with patch("pickaroo.get_collaborators", return_value=["alice", "bob", "carol"]):
            with patch("pickaroo.get_requested_reviewers", return_value=[]):
                with patch("pickaroo.get_pr_reviews", return_value=["alice", "bob"]):
                    with patch("pickaroo.request_reviewers") as mock_request:
                        cmd_select_reviewers()

    picked = mock_request.call_args[0][3]
    assert picked == ["carol"]


def test_cmd_select_reviewers_picks_only_missing_slots(tmp_path):
    """When 1 of 2 slots is filled, picks exactly 1 more."""
    github_output, env = _select_reviewers_env(tmp_path, {
        "GH_INCLUDE_USERS": "alice bob carol",
        "GH_NUMBER_OF_REVIEWERS": "2",
    })

    with patch.dict("os.environ", env, clear=False):
        with patch("pickaroo.get_collaborators", return_value=["alice", "bob", "carol"]):
            with patch("pickaroo.get_requested_reviewers", return_value=["alice"]):
                with patch("pickaroo.get_pr_reviews", return_value=[]):
                    with patch("pickaroo.request_reviewers") as mock_request:
                        cmd_select_reviewers()

    mock_request.assert_called_once()
    picked = mock_request.call_args[0][3]  # 4th positional arg is reviewers list
    assert len(picked) == 1
    assert picked[0] in {"bob", "carol"}


def test_cmd_select_reviewers_falls_back_to_repicks_when_reviewers_zero(tmp_path, capsys):
    """number_of_reviewers=0 falls back to number_of_repicks with a deprecation warning."""
    github_output, env = _select_reviewers_env(tmp_path, {
        "GH_INCLUDE_USERS": "alice bob carol",
        "GH_NUMBER_OF_REVIEWERS": "0",
        "GH_NUMBER_OF_REPICKS": "1",
    })

    with patch.dict("os.environ", env, clear=False):
        with patch("pickaroo.get_collaborators", return_value=["alice", "bob", "carol"]):
            with patch("pickaroo.get_requested_reviewers", return_value=[]):
                with patch("pickaroo.get_pr_reviews", return_value=[]):
                    with patch("pickaroo.request_reviewers") as mock_request:
                        cmd_select_reviewers()

    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "number_of_reviewers" in captured.err
    assert "newjersey.github.io" in captured.err
    mock_request.assert_called_once()


def test_cmd_select_reviewers_exits_1_when_both_zero(tmp_path):
    """Both number_of_reviewers and number_of_repicks <= 0 → exit 1."""
    github_output, env = _select_reviewers_env(tmp_path, {
        "GH_NUMBER_OF_REVIEWERS": "0",
        "GH_NUMBER_OF_REPICKS": "0",
    })

    with patch.dict("os.environ", env, clear=False):
        with pytest.raises(SystemExit) as exc_info:
            cmd_select_reviewers()

    assert exc_info.value.code == 1


def test_cmd_select_reviewers_previously_picked_excluded(tmp_path):
    """previously_picked passed in GH_EXCLUDE_USERS prevents repicking."""
    github_output, env = _select_reviewers_env(tmp_path, {
        "GH_INCLUDE_USERS": "alice bob carol",
        "GH_EXCLUDE_USERS": "alice",  # alice was previously picked
        "GH_NUMBER_OF_REVIEWERS": "1",
    })

    with patch.dict("os.environ", env, clear=False):
        with patch("pickaroo.get_collaborators", return_value=["alice", "bob", "carol"]):
            with patch("pickaroo.get_requested_reviewers", return_value=[]):
                with patch("pickaroo.get_pr_reviews", return_value=[]):
                    with patch("pickaroo.request_reviewers") as mock_request:
                        cmd_select_reviewers()

    picked = mock_request.call_args[0][3]
    assert "alice" not in picked


def test_cmd_select_reviewers_outputs_empty_when_no_candidates(tmp_path):
    """When candidate pool is empty after filtering, writes reviewers= and exits cleanly."""
    github_output, env = _select_reviewers_env(tmp_path, {
        "GH_INCLUDE_USERS": "alice",
        "GH_EXCLUDE_USERS": "alice",
        "GH_NUMBER_OF_REVIEWERS": "1",
    })

    with patch.dict("os.environ", env, clear=False):
        with patch("pickaroo.get_collaborators", return_value=["alice"]):
            with patch("pickaroo.get_requested_reviewers", return_value=[]):
                with patch("pickaroo.get_pr_reviews", return_value=[]):
                    with patch("pickaroo.request_reviewers") as mock_request:
                        cmd_select_reviewers()

    content = github_output.read_text()
    assert "reviewers=\n" in content
    mock_request.assert_not_called()
