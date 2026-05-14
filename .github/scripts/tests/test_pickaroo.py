from unittest.mock import MagicMock, patch

import pytest
import requests
from pickaroo import (
    _THREAD_MESSAGE_TEMPLATES,
    _next_page,
    build_candidate_pool,
    build_comment_body,
    build_main_message,
    build_thread_message,
    cmd_build_messages,
    cmd_find_comment,
    cmd_post_comment,
    cmd_select_reviewers,
    cmd_send_messages,
    count_existing_reviewers,
    deduplicate_reviewers,
    filter_by_slack_status,
    get_collaborators,
    get_pr_comments,
    get_pr_reviews,
    get_requested_reviewers,
    get_team_members,
    is_ooo,
    parse_pickaroo_comment,
    patch_pr_comment,
    post_pr_comment,
    request_reviewers,
)


def test_parse_pickaroo_comment_extracts_message_ts():
    body = (
        "Pickaroo selected and notified reviewers for this PR! 🦘\n\n"
        "message_ts: 1234567890.123456 in C0CH1\n"
        "previously_picked: alice bob"
    )
    result = parse_pickaroo_comment(body)
    assert result["message_ts"] == {"C0CH1": "1234567890.123456"}


def test_parse_pickaroo_comment_extracts_multi_channel_message_ts():
    body = (
        "Pickaroo selected and notified reviewers for this PR! 🦘\n\n"
        "message_ts: 1234.5678 in C0CH1; 9876.5432 in C0CH2\n"
        "previously_picked: alice bob"
    )
    result = parse_pickaroo_comment(body)
    assert result["message_ts"] == {"C0CH1": "1234.5678", "C0CH2": "9876.5432"}


def test_parse_pickaroo_comment_extracts_previously_picked():
    body = (
        "Pickaroo selected and notified reviewers for this PR! 🦘\n\n"
        "message_ts: 1234567890.123456 in C0CH1\n"
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


def test_build_comment_body_includes_message_ts():
    result = build_comment_body({"C0CH1": "1234567890.123456"}, "alice bob")
    assert "message_ts: 1234567890.123456 in C0CH1" in result


def test_build_comment_body_multi_channel():
    result = build_comment_body({"C0CH1": "1234.5678", "C0CH2": "9876.5432"}, "alice")
    assert "1234.5678 in C0CH1" in result
    assert "9876.5432 in C0CH2" in result


def test_build_comment_body_includes_previously_picked():
    result = build_comment_body({"C0CH1": "1234567890.123456"}, "alice bob carol")
    assert "previously_picked: alice bob carol" in result


def test_build_main_message_includes_key_fields():
    result = build_main_message(
        pr_url="https://github.com/org/repo/pull/42",
        pr_type="Review",
        repo_name="my-repo",
        pr_number="42",
        author_mention="<@U123>",
        pr_title="Fix the bug",
        all_reviewer_mentions="",
    )
    assert "https://github.com/org/repo/pull/42" in result
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
        all_reviewer_mentions="",
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
        all_reviewer_mentions="<@U456>, <@U789>",
    )
    assert "Reviewers: <@U456>, <@U789>" in result


def test_all_thread_message_templates_contain_mentions():
    """Every template must include the reviewer mentions."""
    for template in _THREAD_MESSAGE_TEMPLATES:
        result = template.format(mentions="<@U123>")
        assert "<@U123>" in result, f"Template missing mentions: {template!r}"


def test_build_thread_message_mentions_reviewers_when_present():
    result = build_thread_message(
        picked_reviewer_mentions="<@U123> <@U456>",
        pr_author_mention="<@U789>",
        repository="org/repo",
        run_id="12345",
    )
    assert "<@U123> <@U456>" in result


def test_build_thread_message_apology_when_no_reviewers():
    result = build_thread_message(
        picked_reviewer_mentions="",
        pr_author_mention="<@U789>",
        repository="org/repo",
        run_id="12345",
    )
    assert "<@U789>" in result
    assert "https://github.com/org/repo/actions/runs/12345" in result


def test_next_page_extracts_url_from_link_header():
    link = '<https://api.github.com/repos/org/repo/issues/42/comments?page=2>; rel="next", <https://api.github.com/repos/org/repo/issues/42/comments?page=5>; rel="last"'
    assert (
        _next_page(link)
        == "https://api.github.com/repos/org/repo/issues/42/comments?page=2"
    )


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


def test_cmd_find_comment_calls_get_pr_comments_with_correct_args(tmp_path):
    output_file = tmp_path / "github_output"
    output_file.write_text("")
    env = {
        "GITHUB_TOKEN": "tok",
        "GITHUB_REPOSITORY": "org/repo",
        "PR_NUMBER": "7",
        "GITHUB_OUTPUT": str(output_file),
    }
    with (
        patch.dict("os.environ", env, clear=False),
        patch("pickaroo.get_pr_comments", return_value=[]) as mock_get,
    ):
        cmd_find_comment()
    mock_get.assert_called_once_with("org/repo", "7", "tok")


def _build_messages_env(tmp_path, overrides=None):
    github_env = tmp_path / "github_env"
    github_env.write_text("")
    base = {
        "GITHUB_ENV": str(github_env),
        "EXTRAS": "true",
        "NUMBER_OF_REVIEWERS": "1",
        "PICKED_REVIEWERS": "alice",
        "PICKED_REVIEWER_MENTIONS": "<@U123>",
        "ALL_REVIEWER_MENTIONS": "<@U123>",
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


def test_cmd_build_messages_writes_message_and_thread_to_github_env(tmp_path):
    github_env, env = _build_messages_env(tmp_path)
    with patch.dict("os.environ", env, clear=False):
        cmd_build_messages()
    content = github_env.read_text()
    assert "MESSAGE=" in content
    assert "THREAD_MESSAGE=" in content


def test_cmd_build_messages_skips_thread_message_in_show_mode(tmp_path):
    github_env, env = _build_messages_env(
        tmp_path, {"SHOW": "true", "PICKED_REVIEWERS": ""}
    )
    with patch.dict("os.environ", env, clear=False):
        cmd_build_messages()
    content = github_env.read_text()
    assert "THREAD_MESSAGE=\n" in content


def test_cmd_build_messages_pr_title_with_special_chars_does_not_break(tmp_path):
    """Regression: PR titles with quotes and backticks must not corrupt GITHUB_ENV."""
    title = """It's a "test" with `backticks` and $dollar"""
    github_env, env = _build_messages_env(tmp_path, {"PR_TITLE": title})
    with patch.dict("os.environ", env, clear=False):
        cmd_build_messages()
    content = github_env.read_text()
    assert title in content


def test_cmd_build_messages_no_thread_with_enough_existing_reviewers(tmp_path):
    """When the number of existing reviewers equals the number requested, and the
    caller disabled EXTRAS, there's nothing to thread."""
    github_env, env = _build_messages_env(
        tmp_path,
        {
            "EXTRAS": "false",
            "NUMBER_OF_REVIEWERS": "2",
            "PICKED_REVIEWERS": "",
            "PICKED_REVIEWER_MENTIONS": "",
            "ALL_REVIEWER_MENTIONS": "<@U123>, <@U321>",
        },
    )
    with patch.dict("os.environ", env, clear=False):
        cmd_build_messages()
    content = github_env.read_text()
    assert "THREAD_MESSAGE=\n" in content


def _post_comment_env(overrides=None):
    base = {
        "GITHUB_TOKEN": "tok",
        "GITHUB_REPOSITORY": "org/repo",
        "PR_NUMBER": "7",
        "PICKED_REVIEWERS": "carol",
        "PREVIOUSLY_PICKED": "alice bob",
        "MESSAGES": '{"C0CH1": "1234567890.654321"}',
        "PREVIOUS_MESSAGES": "",
        "COMMENT_ID": "",
    }
    if overrides:
        base.update(overrides)
    return base


def test_cmd_post_comment_calls_post_pr_comment_when_no_comment_id():
    with (
        patch("pickaroo.post_pr_comment") as mock_post,
        patch("pickaroo.patch_pr_comment") as mock_patch,
    ):
        with patch.dict("os.environ", _post_comment_env(), clear=False):
            cmd_post_comment()
    mock_post.assert_called_once()
    args = mock_post.call_args[0]
    assert args[0] == "org/repo"
    assert args[1] == "7"
    assert args[2] == "tok"
    mock_patch.assert_not_called()


def test_cmd_post_comment_calls_patch_pr_comment_when_comment_id_present():
    with (
        patch("pickaroo.post_pr_comment") as mock_post,
        patch("pickaroo.patch_pr_comment") as mock_patch,
    ):
        with patch.dict(
            "os.environ", _post_comment_env({"COMMENT_ID": "99"}), clear=False
        ):
            cmd_post_comment()
    mock_patch.assert_called_once()
    args = mock_patch.call_args[0]
    assert args[0] == "org/repo"
    assert args[1] == "99"
    assert args[2] == "tok"
    mock_post.assert_not_called()


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


def test_get_requested_reviewers_returns_user_logins():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "users": [{"login": "alice"}, {"login": "bob"}],
        "teams": [],
    }
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response) as mock_get:
        result = get_requested_reviewers("org/repo", "42", "tok")

    assert result == ["alice", "bob"]
    url = mock_get.call_args[0][0]
    assert "org/repo/pulls/42/requested_reviewers" in url


def test_get_pr_reviews_returns_reviewer_logins():
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


def test_request_reviewers_posts_correct_payload():
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": 1}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response) as mock_post:
        request_reviewers("org/repo", "42", "tok", ["alice", "bob"])

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
    assert is_ooo("vacation time!", "") is True


def test_is_ooo_returns_true_for_ooo_emoji():
    assert is_ooo("", ":palm_tree:") is True
    assert is_ooo("", ":thermometer:") is True
    assert is_ooo("", ":face_with_medical_mask:") is True
    assert is_ooo("", ":airplane:") is True


def test_is_ooo_returns_false_for_future_ooo():
    """Future OOO indicators are treated as currently available."""
    assert is_ooo("upcoming vacation", ":crystal_ball:") is False


# ---------------------------------------------------------------------------
# Selection logic
# ---------------------------------------------------------------------------


def test_count_existing_reviewers_counts_valid_reviewers():
    result = count_existing_reviewers(
        existing_set={"alice", "bob"},
        include_set={"alice", "bob", "carol"},
        exclude_set=set(),
        collaborators_set={"alice", "bob", "carol"},
        author="dave",
    )
    assert result == 2


def test_count_existing_reviewers_excludes_reviewer_in_exclude_set():
    result = count_existing_reviewers(
        existing_set={"alice", "bob"},
        include_set={"alice", "bob"},
        exclude_set={"alice"},
        collaborators_set={"alice", "bob"},
        author="dave",
    )
    assert result == 1


def test_count_existing_reviewers_counts_reviewed_users():
    """Users who have already submitted a review count as existing reviewers."""
    result = count_existing_reviewers(
        existing_set={"alice", "bob"},
        include_set={"alice", "bob", "carol"},
        exclude_set=set(),
        collaborators_set={"alice", "bob", "carol"},
        author="dave",
    )
    assert result == 2


def test_count_existing_reviewers_deduplicates_requested_and_reviewed():
    """A user who is both requested and reviewed counts only once."""
    result = count_existing_reviewers(
        existing_set={"alice", "bob"},
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
        existing_set={"alice"},
    )
    assert set(result) == {"bob", "carol"}


def test_build_candidate_pool_excludes_already_requested():
    result = build_candidate_pool(
        include_set={"alice", "bob", "carol"},
        exclude_set=set(),
        collaborators_set={"alice", "bob", "carol"},
        author="dave",
        existing_set={"bob", "carol"},
    )
    assert set(result) == {"alice"}


def test_build_candidate_pool_excludes_already_reviewed():
    """Users who already submitted a review are not candidates for re-request."""
    result = build_candidate_pool(
        include_set={"alice", "bob", "carol"},
        exclude_set=set(),
        collaborators_set={"alice", "bob", "carol"},
        author="dave",
        existing_set={"bob", "carol"},
    )
    assert set(result) == {"alice"}


def test_build_candidate_pool_returns_empty_when_all_filtered():
    result = build_candidate_pool(
        include_set={"alice"},
        exclude_set={"alice"},
        collaborators_set={"alice"},
        author="dave",
        existing_set=set(),
    )
    assert result == []


def test_filter_by_slack_status_skips_when_no_mapping():
    result = filter_by_slack_status(["alice"], "", "slack-tok")
    assert result == ["alice"]


def test_filter_by_slack_status_exits_1_when_mapping_present_but_no_token():
    with patch("pickaroo.auth_test", return_value={"ok": False}):
        with pytest.raises(SystemExit) as exc_info:
            filter_by_slack_status(["alice"], '{"alice": "U123"}', "")
    assert exc_info.value.code == 1


def test_filter_by_slack_status_excludes_ooo_user():
    mapping = '{"alice": "U123"}'
    profile = {"status_text": "on vacation", "status_emoji": ":palm_tree:"}
    with (
        patch("pickaroo.auth_test", return_value={"ok": True}),
        patch("pickaroo.get_profile", return_value=profile),
    ):
        result = filter_by_slack_status(["alice"], mapping, "slack-tok")
    assert result == []


def test_filter_by_slack_status_includes_user_not_in_mapping():
    mapping = '{"bob": "U456"}'
    with (
        patch("pickaroo.auth_test", return_value={"ok": True}),
        patch(
            "pickaroo.get_profile", return_value={"status_text": "", "status_emoji": ""}
        ),
    ):
        result = filter_by_slack_status(["alice"], mapping, "slack-tok")
    assert result == ["alice"]


def test_filter_by_slack_status_includes_user_on_api_failure(capsys):
    mapping = '{"alice": "U123"}'
    with (
        patch("pickaroo.auth_test", return_value={"ok": True}),
        patch("pickaroo.get_profile", side_effect=Exception("network error")),
    ):
        result = filter_by_slack_status(["alice"], mapping, "slack-tok")
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
        "INCLUDE_TEAMS": "",
        "INCLUDE_USERS": "alice bob carol",
        "EXCLUDE_TEAMS": "",
        "EXCLUDE_USERS": "",
        "NUMBER_OF_REVIEWERS": "2",
        "NUMBER_OF_REPICKS": "1",
        "EXTRAS": "True",
        "GH_SLACK_USER_MAP": "",
        "SLACK_TOKEN": "",
        "GITHUB_OUTPUT": str(github_output),
    }
    if overrides:
        base.update(overrides)
    return github_output, base


def test_cmd_select_reviewers_calls_api_helpers_with_correct_args(tmp_path):
    """cmd_select_reviewers wires the correct (repo, pr_number, token) args to each API call."""
    github_output, env = _select_reviewers_env(tmp_path)

    with (
        patch.dict("os.environ", env, clear=False),
        patch(
            "pickaroo.get_collaborators", return_value=["alice", "bob", "carol"]
        ) as mock_collabs,
        patch("pickaroo.get_requested_reviewers", return_value=[]) as mock_requested,
        patch("pickaroo.get_pr_reviews", return_value=[]) as mock_reviews,
        patch("pickaroo.request_reviewers") as mock_request,
    ):
        cmd_select_reviewers()

    mock_collabs.assert_called_once_with("org/repo", "tok")
    mock_requested.assert_called_once_with("org/repo", "42", "tok")
    mock_reviews.assert_called_once_with("org/repo", "42", "tok")
    mock_request.assert_called_once()
    assert mock_request.call_args[0][0] == "org/repo"
    assert mock_request.call_args[0][1] == "42"
    assert mock_request.call_args[0][2] == "tok"


def test_cmd_select_reviewers_falls_back_to_repicks_when_reviewers_zero(
    tmp_path, capsys
):
    """number_of_reviewers=0 falls back to number_of_repicks with a deprecation warning."""
    github_output, env = _select_reviewers_env(
        tmp_path,
        {
            "INCLUDE_USERS": "alice bob carol",
            "NUMBER_OF_REVIEWERS": "0",
            "NUMBER_OF_REPICKS": "1",
        },
    )

    with (
        patch.dict("os.environ", env, clear=False),
        patch("pickaroo.get_collaborators", return_value=["alice", "bob", "carol"]),
        patch("pickaroo.get_requested_reviewers", return_value=[]),
        patch("pickaroo.get_pr_reviews", return_value=[]),
        patch("pickaroo.request_reviewers") as mock_request,
    ):
        cmd_select_reviewers()

    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "number_of_reviewers" in captured.err
    assert "newjersey.github.io" in captured.err
    mock_request.assert_called_once()


def test_cmd_select_reviewers_exits_1_when_both_zero(tmp_path):
    """Both number_of_reviewers and number_of_repicks <= 0 → exit 1."""
    github_output, env = _select_reviewers_env(
        tmp_path,
        {
            "NUMBER_OF_REVIEWERS": "0",
            "NUMBER_OF_REPICKS": "0",
        },
    )

    with patch.dict("os.environ", env, clear=False):
        with pytest.raises(SystemExit) as exc_info:
            cmd_select_reviewers()

    assert exc_info.value.code == 1


def test_cmd_select_reviewers_outputs_empty_when_no_candidates(tmp_path):
    """When candidate pool is empty after filtering, writes empty outputs and exits cleanly."""
    github_output, env = _select_reviewers_env(
        tmp_path,
        {
            "INCLUDE_USERS": "alice",
            "EXCLUDE_USERS": "alice",
            "NUMBER_OF_REVIEWERS": "1",
        },
    )

    with (
        patch.dict("os.environ", env, clear=False),
        patch("pickaroo.get_collaborators", return_value=["alice"]),
        patch("pickaroo.get_requested_reviewers", return_value=[]),
        patch("pickaroo.get_pr_reviews", return_value=[]),
        patch("pickaroo.request_reviewers") as mock_request,
    ):
        cmd_select_reviewers()

    content = github_output.read_text()
    assert "picked_reviewers=\n" in content
    assert "all_reviewers=\n" in content
    mock_request.assert_not_called()


def test_cmd_select_reviewers_no_extra_pick_when_extras_disabled(tmp_path):
    """When EXTRAS=false and slots are already filled, no additional reviewer is picked."""
    github_output, env = _select_reviewers_env(
        tmp_path,
        {
            "INCLUDE_USERS": "alice bob carol",
            "NUMBER_OF_REVIEWERS": "2",
            "EXTRAS": "false",
        },
    )

    with (
        patch.dict("os.environ", env, clear=False),
        patch("pickaroo.get_collaborators", return_value=["alice", "bob", "carol"]),
        patch("pickaroo.get_requested_reviewers", return_value=["alice", "bob"]),
        patch("pickaroo.get_pr_reviews", return_value=[]),
        patch("pickaroo.request_reviewers") as mock_request,
    ):
        cmd_select_reviewers()

    mock_request.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_send_messages
# ---------------------------------------------------------------------------


def _send_messages_env(tmp_path, overrides=None):
    output_file = tmp_path / "github_output"
    output_file.write_text("")
    base = {
        "CHANNEL_ID": "C0CH1",
        "MESSAGE": "hello world",
        "THREAD_MESSAGE": "",
        "MESSAGE_TS": "",
        "TOKEN": "xoxb-token",
        "USERNAME": "Pickaroo",
        "AVATAR_URL": "",
        "AVATAR_EMOJI": ":kangaroo:",
        "THREAD_USERNAME": "",
        "THREAD_AVATAR_URL": "",
        "THREAD_AVATAR_EMOJI": "",
        "GITHUB_OUTPUT": str(output_file),
    }
    if overrides:
        base.update(overrides)
    return output_file, base


def test_cmd_send_messages_posts_to_single_channel(tmp_path):
    output_file, env = _send_messages_env(tmp_path)

    with (
        patch.dict("os.environ", env, clear=False),
        patch("pickaroo.auth_test", return_value={"ok": True}),
        patch("pickaroo.post_message", return_value="1111.2222") as mock_post,
        patch("pickaroo.update_message") as mock_update,
    ):
        cmd_send_messages()

    mock_post.assert_called_once()
    mock_update.assert_not_called()
    import json

    content = output_file.read_text()
    messages = json.loads(content.split("messages=")[1].strip())
    assert messages == {"C0CH1": "1111.2222"}


def test_cmd_send_messages_posts_to_multiple_channels(tmp_path):
    output_file, env = _send_messages_env(tmp_path, {"CHANNEL_ID": "C0CH1 C0CH2"})

    with (
        patch.dict("os.environ", env, clear=False),
        patch("pickaroo.auth_test", return_value={"ok": True}),
        patch(
            "pickaroo.post_message", side_effect=["1111.2222", "3333.4444"]
        ) as mock_post,
        patch("pickaroo.update_message"),
    ):
        cmd_send_messages()

    assert mock_post.call_count == 2
    import json

    content = output_file.read_text()
    messages = json.loads(content.split("messages=")[1].strip())
    assert messages == {"C0CH1": "1111.2222", "C0CH2": "3333.4444"}


def test_cmd_send_messages_updates_existing_and_posts_new(tmp_path):
    output_file, env = _send_messages_env(
        tmp_path,
        {
            "CHANNEL_ID": "C0CH1 C0CH2",
            "MESSAGE_TS": '{"C0CH1": "1111.2222"}',
        },
    )

    with (
        patch.dict("os.environ", env, clear=False),
        patch("pickaroo.auth_test", return_value={"ok": True}),
        patch("pickaroo.post_message", return_value="3333.4444") as mock_post,
        patch("pickaroo.update_message") as mock_update,
    ):
        cmd_send_messages()

    mock_update.assert_called_once()
    assert mock_update.call_args[1]["channel"] == "C0CH1"
    mock_post.assert_called_once()
    assert mock_post.call_args[1]["channel"] == "C0CH2"


def test_cmd_send_messages_sends_thread_to_all_channels(tmp_path):
    output_file, env = _send_messages_env(
        tmp_path,
        {
            "CHANNEL_ID": "C0CH1 C0CH2",
            "THREAD_MESSAGE": "thread reply",
            "THREAD_USERNAME": "Pickaroo",
            "THREAD_AVATAR_EMOJI": ":kangaroo:",
        },
    )

    with (
        patch.dict("os.environ", env, clear=False),
        patch("pickaroo.auth_test", return_value={"ok": True}),
        patch(
            "pickaroo.post_message", side_effect=["1111.2222", "3333.4444", "t1", "t2"]
        ) as mock_post,
        patch("pickaroo.update_message"),
    ):
        cmd_send_messages()

    # 2 main messages + 2 thread replies = 4 calls
    assert mock_post.call_count == 4


def test_cmd_send_messages_ignores_ledger_channels_not_in_input(tmp_path):
    output_file, env = _send_messages_env(
        tmp_path,
        {
            "CHANNEL_ID": "C0CH2",
            "MESSAGE_TS": '{"C0CH1": "1111.2222", "C0CH2": "3333.4444"}',
        },
    )

    with (
        patch.dict("os.environ", env, clear=False),
        patch("pickaroo.auth_test", return_value={"ok": True}),
        patch("pickaroo.post_message") as mock_post,
        patch("pickaroo.update_message") as mock_update,
    ):
        cmd_send_messages()

    mock_update.assert_called_once()
    assert mock_update.call_args[1]["channel"] == "C0CH2"
    mock_post.assert_not_called()
    import json

    content = output_file.read_text()
    messages = json.loads(content.split("messages=")[1].strip())
    assert "C0CH1" not in messages


def test_cmd_send_messages_exits_1_on_bad_token(tmp_path):
    _, env = _send_messages_env(tmp_path)

    with (
        patch.dict("os.environ", env, clear=False),
        patch("pickaroo.auth_test", return_value={"ok": False}),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cmd_send_messages()
    assert exc_info.value.code == 1
