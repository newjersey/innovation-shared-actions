import os
import sys
import re
import requests


# ---------------------------------------------------------------------------
# Pure logic helpers
# ---------------------------------------------------------------------------


def parse_pickaroo_comment(body: str) -> dict:
    """Extract message_ts and previously_picked from a pickaroo PR comment body."""
    result = {}
    ts_match = re.search(r'message_ts: (\d+\.\d+)', body)
    if ts_match:
        result['message_ts'] = ts_match.group(1)
    pp_match = re.search(r'previously_picked: (.+)', body)
    if pp_match:
        result['previously_picked'] = pp_match.group(1).rstrip()
    return result


def deduplicate_reviewers(previously_picked: str, new_reviewers: str) -> list:
    """Merge two space-delimited reviewer strings, deduplicate, preserve insertion order."""
    combined = f"{previously_picked} {new_reviewers}".split()
    return list(dict.fromkeys(item for item in combined if item))


def build_comment_body(message_ts: str, previously_picked: str) -> str:
    """Format the PR comment body with pickaroo metadata."""
    return (
        "Pickaroo selected and notified reviewers for this PR! 🦘\n\n"
        f"message_ts: {message_ts}\n"
        f"previously_picked: {previously_picked}"
    )


def build_main_message(
    pr_url: str,
    pr_type: str,
    repo_name: str,
    pr_number: str,
    author_mention: str,
    pr_title: str,
    current_reviewer_mentions: str,
) -> str:
    """Build the main Slack message string.

    Uses literal \\n (backslash-n) rather than actual newlines — the slack-message
    action converts these to real newlines before sending to Slack.
    """
    message = (
        f"[ <{pr_url}|PR {pr_type}> ] {repo_name} - #{pr_number} by {author_mention}:"
        r"\n\n"
        f"**{pr_title}**"
    )
    if current_reviewer_mentions:
        message += r"\n\n" + f"Reviewers: {current_reviewer_mentions}"
    return message


def build_thread_message(
    new_reviewer_mentions: str,
    pr_author_mention: str,
    repository: str,
    run_id: str,
) -> str:
    """Build the Slack thread reply string.

    The caller decides whether to invoke this function at all — show mode
    logic belongs in the build-messages subcommand, not here.
    """
    if new_reviewer_mentions:
        return f"Hey {new_reviewer_mentions} 🫵! Please review this pull request 🦘🙏"
    return (
        f"Sorry {pr_author_mention}, likely due to their Slack status no potential reviewers "
        f"are available. "
        f"<https://github.com/{repository}/actions/runs/{run_id}|Check workflow run> for details. "
        f"Ask Eeny for help and/or manually assign some reviewers."
    )


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

_GH_API = "https://api.github.com"
_GH_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def _gh_headers(token: str) -> dict:
    return {**_GH_HEADERS, "Authorization": f"Bearer {token}"}


def get_pr_comments(repo: str, pr_number: str, token: str) -> list:
    """GET /repos/{repo}/issues/{pr_number}/comments"""
    url = f"{_GH_API}/repos/{repo}/issues/{pr_number}/comments"
    response = requests.get(url, headers=_gh_headers(token))
    response.raise_for_status()
    return response.json()


def post_pr_comment(repo: str, pr_number: str, token: str, body: str) -> dict:
    """POST /repos/{repo}/issues/{pr_number}/comments"""
    url = f"{_GH_API}/repos/{repo}/issues/{pr_number}/comments"
    response = requests.post(url, headers=_gh_headers(token), json={"body": body})
    response.raise_for_status()
    return response.json()


def patch_pr_comment(repo: str, comment_id: str, token: str, body: str) -> dict:
    """PATCH /repos/{repo}/issues/comments/{comment_id}"""
    url = f"{_GH_API}/repos/{repo}/issues/comments/{comment_id}"
    response = requests.patch(url, headers=_gh_headers(token), json={"body": body})
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    commands = {
        "find-comment": cmd_find_comment,
        "build-messages": cmd_build_messages,
        "post-comment": cmd_post_comment,
    }
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in commands:
        print(f"Unknown command: {command!r}. Available: {', '.join(commands)}", file=sys.stderr)
        sys.exit(1)
    commands[command]()


def cmd_find_comment():
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = os.environ["PR_NUMBER"]
    github_output = os.environ["GITHUB_OUTPUT"]

    comments = get_pr_comments(repo, pr_number, token)
    pickaroo_comments = [c for c in comments if "message_ts:" in c.get("body", "")]

    if not pickaroo_comments:
        print("No existing pickaroo comment found")
        return

    last = pickaroo_comments[-1]
    comment_id = str(last["id"])
    parsed = parse_pickaroo_comment(last["body"])

    print(f"Found existing pickaroo comment: id={comment_id}, message_ts={parsed.get('message_ts', '')}")

    with open(github_output, "a") as f:
        if "message_ts" in parsed:
            f.write(f"message-ts={parsed['message_ts']}\n")
        f.write(f"comment-id={comment_id}\n")
        if "previously_picked" in parsed:
            f.write(f"previously-picked={parsed['previously_picked']}\n")


def cmd_build_messages():
    github_env = os.environ["GITHUB_ENV"]
    show = os.environ.get("SHOW", "false").lower() == "true"

    new_reviewer_mentions = os.environ.get("NEW_REVIEWER_MENTIONS", "")
    current_reviewer_mentions = os.environ.get("CURRENT_REVIEWER_MENTIONS", "")
    author_mention = os.environ.get("AUTHOR_MENTION", "")
    pr_url = os.environ["PR_URL"]
    pr_number = os.environ["PR_NUMBER"]
    pr_title = os.environ["PR_TITLE"]
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    repo_name = repository.split("/")[1]
    pr_type = "Show" if show else "Review"

    message = build_main_message(
        pr_url=pr_url,
        pr_type=pr_type,
        repo_name=repo_name,
        pr_number=pr_number,
        author_mention=author_mention,
        pr_title=pr_title,
        current_reviewer_mentions=current_reviewer_mentions,
    )

    if show:
        thread_message = ""
    else:
        thread_message = build_thread_message(
            new_reviewer_mentions=new_reviewer_mentions,
            pr_author_mention=author_mention,
            repository=repository,
            run_id=run_id,
        )

    with open(github_env, "a") as f:
        f.write(f"MESSAGE={message}\n")
        f.write(f"THREAD_MESSAGE={thread_message}\n")


def cmd_post_comment():
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = os.environ["PR_NUMBER"]
    reviewers = os.environ.get("REVIEWERS", "")
    previously_picked = os.environ.get("PREVIOUSLY_PICKED", "")
    message_ts = os.environ.get("MESSAGE_TS", "")
    comment_id = os.environ.get("COMMENT_ID", "")

    all_picked = deduplicate_reviewers(previously_picked, reviewers)
    body = build_comment_body(message_ts, " ".join(all_picked))

    if comment_id and comment_id != "null":
        print(f"Updating existing comment {comment_id} on PR #{pr_number}")
        patch_pr_comment(repo, comment_id, token, body)
        print("Successfully updated PR comment")
    else:
        print(f"Posting new comment to PR #{pr_number}")
        post_pr_comment(repo, pr_number, token, body)
        print("Successfully posted PR comment")


if __name__ == "__main__":
    main()
