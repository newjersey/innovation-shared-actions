import json
import os
import random
import re
import sys

import requests

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def parse_pickaroo_comment(body: str) -> dict:
    """Extract message_ts and previously_picked from a pickaroo PR comment body."""
    result = {}
    ts_match = re.search(r"message_ts: (\d+\.\d+)", body)
    if ts_match:
        result["message_ts"] = ts_match.group(1)
    pp_match = re.search(r"previously_picked: (.+)", body)
    if pp_match:
        result["previously_picked"] = pp_match.group(1).rstrip()
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
    all_reviewer_mentions: str,
) -> str:
    """Build the main Slack message string."""
    message = (
        f"[ <{pr_url}|PR {pr_type}> ] {repo_name} - #{pr_number} by {author_mention}:"
        r"\n\n"
        f"**{pr_title}**"
    )
    if all_reviewer_mentions:
        message += r"\n\n" + f"Reviewers: {all_reviewer_mentions}"
    return message


_THREAD_MESSAGE_TEMPLATES = [
    "Hey {mentions}! It's Pickaroo :kangaroo: and I pick-a-you to review this pull request :pray:",
    "Hi {mentions}, you're up to bat! :baseball_batter:",
    "Tag!! {mentions} :index_pointing_at_the_viewer: you've been PICKED.",
    "Congrats {mentions}! You've been volun-told to review this PR. Off you go :nail_care:",
    "Um... hey {mentions}... could you :point_right::point_left: maybe review this? ...no rush! :see_no_evil: ...pls? :homer-disappear:",
    "The code cries out, {mentions}! A PR of unknown consequence awaits your review.",
]


def build_thread_message(
    picked_reviewer_mentions: str,
    pr_author_mention: str,
    repository: str,
    run_id: str,
) -> str:
    """Build the Slack thread reply string."""
    if picked_reviewer_mentions:
        template = random.choice(_THREAD_MESSAGE_TEMPLATES)
        return template.format(mentions=picked_reviewer_mentions)
    return (
        f"Sorry {pr_author_mention}, likely due to their Slack status no potential reviewers "
        f"are available. "
        f"<https://github.com/{repository}/actions/runs/{run_id}|Check workflow run> for details. "
        f"Ask Eeny for help and/or manually assign some reviewers to the PR."
    )


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

_GH_API = "https://api.github.com"
_GH_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _gh_headers(token: str) -> dict:
    return {**_GH_HEADERS, "Authorization": f"Bearer {token}"}


def _next_page(link_header: str) -> str:
    """Extract the next-page URL from a GitHub Link header, or return empty string."""
    for part in link_header.split(","):
        url, _, rel = part.strip().partition(";")
        if rel.strip() == 'rel="next"':
            return url.strip().strip("<>")
    return ""


def get_pr_comments(repo: str, pr_number: str, token: str) -> list:
    """GET /repos/{repo}/issues/{pr_number}/comments (all pages)"""
    url = f"{_GH_API}/repos/{repo}/issues/{pr_number}/comments"
    params: dict = {"per_page": 100}
    headers = _gh_headers(token)
    all_comments: list = []
    while url:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        all_comments.extend(response.json())
        url = _next_page(response.headers.get("Link", ""))
        params = {}
    return all_comments


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
# GitHub API helpers — reviewer selection
# ---------------------------------------------------------------------------


def get_team_members(org: str, team: str, token: str) -> list:
    """GET /orgs/{org}/teams/{team}/members — returns list of login strings."""
    url = f"{_GH_API}/orgs/{org}/teams/{team}/members"
    headers = _gh_headers(token)
    all_members = []
    params = {"per_page": 100}
    while url:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        all_members.extend(m["login"] for m in response.json())
        url = _next_page(response.headers.get("Link", ""))
        params = {}
    return all_members


def get_collaborators(repo: str, token: str) -> list:
    """GET /repos/{repo}/collaborators — returns list of login strings (paginated).

    Uses the default affiliation=all, which includes outside collaborators.
    This matches the original bash behavior.
    """
    url = f"{_GH_API}/repos/{repo}/collaborators"
    headers = _gh_headers(token)
    all_collaborators = []
    params = {"per_page": 100}
    while url:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        all_collaborators.extend(c["login"] for c in response.json())
        url = _next_page(response.headers.get("Link", ""))
        params = {}
    return all_collaborators


def get_requested_reviewers(repo: str, pr_number: str, token: str) -> list:
    """GET /repos/{repo}/pulls/{pr_number}/requested_reviewers — returns list of user login strings."""
    url = f"{_GH_API}/repos/{repo}/pulls/{pr_number}/requested_reviewers"
    response = requests.get(url, headers=_gh_headers(token))
    response.raise_for_status()
    return [u["login"] for u in response.json().get("users", [])]


def get_pr_reviews(repo: str, pr_number: str, token: str) -> list:
    """GET /repos/{repo}/pulls/{pr_number}/reviews — returns unique reviewer login strings.

    A reviewer may appear multiple times (e.g. requested changes then approved),
    so results are deduplicated while preserving first-seen order.
    """
    url = f"{_GH_API}/repos/{repo}/pulls/{pr_number}/reviews"
    headers = _gh_headers(token)
    all_reviews = []
    params = {"per_page": 100}
    while url:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        all_reviews.extend(r["user"]["login"] for r in response.json())
        url = _next_page(response.headers.get("Link", ""))
        params = {}
    seen: set = set()
    unique = []
    for login in all_reviews:
        if login not in seen:
            seen.add(login)
            unique.append(login)
    return unique


def request_reviewers(repo: str, pr_number: str, token: str, reviewers: list) -> dict:
    """POST /repos/{repo}/pulls/{pr_number}/requested_reviewers"""
    url = f"{_GH_API}/repos/{repo}/pulls/{pr_number}/requested_reviewers"
    response = requests.post(
        url, headers=_gh_headers(token), json={"reviewers": reviewers}
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Slack helpers
# ---------------------------------------------------------------------------

_OOO_PATTERNS = re.compile(
    r"(out of office|ooo|vacation|holiday|sabbatical|bereavement"
    r"|\bsick\b|\bill\b|\bleave\b|\baway\b|\btravel"
    r"|:face_with_thermometer:|:face_vomiting:|:sneezing_face:|:nauseated_face:"
    r"|:thermometer:|:mask:|:face_with_medical_mask:|:hospital:"
    r"|:palm_tree:|:beach_with_umbrella:|:airplane:|:luggage:)",
    re.IGNORECASE,
)
_FUTURE_OOO_PATTERNS = re.compile(
    r"(\bupcoming\b|\bfuture\b|\bplanned\b|:crystal_ball:)",
    re.IGNORECASE,
)


def is_ooo(status_text: str, status_emoji: str) -> bool:
    """Return True if the user appears to be out of office / unavailable.

    Future OOO indicators (crystal_ball, upcoming, etc.) are treated as
    currently available (returns False).
    """
    combined = f"{status_text} {status_emoji}"
    if _FUTURE_OOO_PATTERNS.search(combined):
        return False
    return bool(_OOO_PATTERNS.search(combined))


def validate_slack_token(token: str) -> bool:
    """POST https://slack.com/api/auth.test — returns True if token is valid."""
    response = requests.post(
        "https://slack.com/api/auth.test",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return bool(response.json().get("ok", False))


def get_slack_status(slack_user_id: str, token: str) -> tuple:
    """GET https://slack.com/api/users.profile.get — returns (status_text, status_emoji).

    On API error (ok=false), profile is absent and this returns ("", ""), which
    is_ooo treats ("", "") as not OOO (include-on-error behavior).
    """
    response = requests.get(
        "https://slack.com/api/users.profile.get",
        params={"user": slack_user_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    profile = response.json().get("profile", {})
    return (profile.get("status_text", ""), profile.get("status_emoji", ""))


# ---------------------------------------------------------------------------
# Selection logic
# ---------------------------------------------------------------------------


def count_valid_existing(
    requested: list,
    reviewed: list,
    include_set: set,
    exclude_set: set,
    collaborators_set: set,
    author: str,
) -> int:
    """Count reviewers (requested or already reviewed) valid for this include pool.

    A reviewer counts only if they are in the include set, not in the exclude
    set, are a repository collaborator, and are not the PR author. Slack OOO
    status is intentionally not checked here — existing assignments always count.
    Requested and reviewed lists are unioned so a reviewer who did both counts once.
    """
    all_reviewers = set(requested) | set(reviewed)
    return sum(
        1
        for r in all_reviewers
        if r in include_set
        and r not in exclude_set
        and r in collaborators_set
        and r != author
    )


def build_candidate_pool(
    include_set: set,
    exclude_set: set,
    collaborators_set: set,
    author: str,
    already_requested: list,
    already_reviewed: list,
) -> list:
    """Return eligible candidates for new reviewer picks.

    Excludes anyone who is currently a requested reviewer or has already
    submitted a review — they don't need to be requested again.
    """
    already_set = set(already_requested) | set(already_reviewed)
    return [
        u
        for u in include_set
        if u not in exclude_set
        and u in collaborators_set
        and u != author
        and u not in already_set
    ]


def filter_ooo_candidates(
    candidates: list,
    gh_slack_mapping: dict,
    slack_token: str,
) -> list:
    """Remove candidates whose Slack status indicates current unavailability.

    Users not present in gh_slack_mapping are always included. On Slack API
    failure, the user is included with a warning.
    """
    available = []
    for member in candidates:
        slack_user_id = gh_slack_mapping.get(member)
        if not slack_user_id:
            available.append(member)
            continue
        try:
            status_text, status_emoji = get_slack_status(slack_user_id, slack_token)
        except Exception as e:
            print(
                f"WARNING: Slack API call failed for {member}: {e} — including user anyway"
            )
            available.append(member)
            continue
        if not is_ooo(status_text, status_emoji):
            available.append(member)
        else:
            print(
                f"  ==> Excluding {member} due to Slack status: {status_emoji} {status_text}"
            )
    return available


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_select_reviewers():
    """Select reviewers for a PR using smart counting.

    Reads configuration from environment variables, counts how many valid
    reviewers are already requested, and picks only as many as needed to
    reach the target number.
    """
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = os.environ["GH_PR_NUMBER"]
    pr_author = os.environ.get("GH_PR_AUTHOR", "")
    include_teams = os.environ.get("GH_INCLUDE_TEAMS", "").split()
    include_users = os.environ.get("GH_INCLUDE_USERS", "").split()
    exclude_teams = os.environ.get("GH_EXCLUDE_TEAMS", "").split()
    exclude_users = os.environ.get("GH_EXCLUDE_USERS", "").split()
    github_output = os.environ["GITHUB_OUTPUT"]

    try:
        number_of_reviewers = int(os.environ.get("GH_NUMBER_OF_REVIEWERS", "0"))
    except ValueError:
        number_of_reviewers = 0

    try:
        number_of_repicks = int(os.environ.get("GH_NUMBER_OF_REPICKS", "0"))
    except ValueError:
        number_of_repicks = 0

    if number_of_reviewers > 0:
        n = number_of_reviewers
    elif number_of_repicks > 0:
        print(
            "WARNING: number_of_reviewers is not set or <= 0; falling back to number_of_repicks. "
            "This configuration is deprecated. Please set number_of_reviewers directly. "
            "See: https://newjersey.github.io/innovation-engineering/guides/github-actions/action-pickaroo/",
            file=sys.stderr,
        )
        n = number_of_repicks
    else:
        print(
            "ERROR: number_of_reviewers is required and must be a positive integer. Did you mean to configure a SHOW pr?",
            file=sys.stderr,
        )
        sys.exit(1)

    org = repo.split("/")[0]

    # Build include pool
    include_set = set()
    for team in include_teams:
        print(f"Fetching members for include team: {team}")
        include_set.update(get_team_members(org, team, token))
    include_set.update(include_users)
    print(f"Include pool: {sorted(include_set)}")

    # Build exclude set
    exclude_set = set()
    for team in exclude_teams:
        print(f"Fetching members for exclude team: {team}")
        exclude_set.update(get_team_members(org, team, token))
    exclude_set.update(exclude_users)
    print(f"Exclude set: {sorted(exclude_set)}")

    print("Fetching repository collaborators")
    collaborators_set = set(get_collaborators(repo, token))

    print(f"Fetching existing reviewers for PR #{pr_number}")
    requested = get_requested_reviewers(repo, pr_number, token)
    print(f"Currently requested reviewers: {requested}")
    reviewed = get_pr_reviews(repo, pr_number, token)
    print(f"Already reviewed by: {reviewed}")

    valid_existing = count_valid_existing(
        requested, reviewed, include_set, exclude_set, collaborators_set, pr_author
    )
    print(f"Valid existing reviewers: {valid_existing} / {n} required")

    # Always pick at least 1: if slots are full, add 1 more for authors who want
    # extra coverage; if slots are short, fill them all.
    to_pick = max(1, n - valid_existing)

    candidates = build_candidate_pool(
        include_set, exclude_set, collaborators_set, pr_author, requested, reviewed
    )

    if not candidates:
        print("WARNING: No eligible candidates found after filtering")
        with open(github_output, "a") as f:
            f.write("picked_reviewers=\n")
            f.write(f"all_reviewers={' '.join(requested)}\n")
        return

    # Optional Slack OOO filtering
    gh_slack_mapping_str = os.environ.get("GH_SLACK_USER_MAP", "")
    slack_token = os.environ.get("SLACK_TOKEN", "")
    if gh_slack_mapping_str and slack_token:
        try:
            gh_slack_mapping = json.loads(gh_slack_mapping_str)
        except json.JSONDecodeError:
            print(
                "WARNING: GH_SLACK_USER_MAP is not valid JSON — skipping Slack filtering"
            )
            gh_slack_mapping = {}
        if gh_slack_mapping:
            print("Validating Slack token...")
            if not validate_slack_token(slack_token):
                print("ERROR: Slack token validation failed", file=sys.stderr)
                sys.exit(1)
            print("Filtering candidates by Slack status...")
            candidates = filter_ooo_candidates(
                candidates, gh_slack_mapping, slack_token
            )
            if not candidates:
                print("WARNING: All candidates filtered out by Slack status")
                with open(github_output, "a") as f:
                    f.write("picked_reviewers=\n")
                    f.write(f"all_reviewers={' '.join(requested)}\n")
                return

    pick_count = min(to_pick, len(candidates))
    picked = random.sample(candidates, pick_count)
    print(f"Selected reviewers: {picked}")

    request_reviewers(repo, pr_number, token, picked)
    print(f"Successfully requested reviewers: {picked}")

    all_reviewers = requested + picked
    with open(github_output, "a") as f:
        f.write(f"picked_reviewers={' '.join(picked)}\n")
        f.write(f"all_reviewers={' '.join(all_reviewers)}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    commands = {
        "find-comment": cmd_find_comment,
        "build-messages": cmd_build_messages,
        "post-comment": cmd_post_comment,
        "select-reviewers": cmd_select_reviewers,
    }
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in commands:
        print(
            f"Unknown command: {command!r}. Available: {', '.join(commands)}",
            file=sys.stderr,
        )
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

    last = pickaroo_comments[0]
    comment_id = str(last["id"])
    parsed = parse_pickaroo_comment(last["body"])

    print(
        f"Found existing pickaroo comment: id={comment_id}, message_ts={parsed.get('message_ts', '')}"
    )

    with open(github_output, "a") as f:
        if "message_ts" in parsed:
            f.write(f"message-ts={parsed['message_ts']}\n")
        f.write(f"comment-id={comment_id}\n")
        if "previously_picked" in parsed:
            f.write(f"previously-picked={parsed['previously_picked']}\n")


def cmd_build_messages():
    github_env = os.environ["GITHUB_ENV"]
    show = os.environ.get("SHOW", "false").lower() == "true"

    picked_reviewer_mentions = os.environ.get("PICKED_REVIEWER_MENTIONS", "")
    all_reviewer_mentions = os.environ.get("ALL_REVIEWER_MENTIONS", "")
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
        all_reviewer_mentions=all_reviewer_mentions,
    )

    if show:
        thread_message = ""
    else:
        thread_message = build_thread_message(
            picked_reviewer_mentions=picked_reviewer_mentions,
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
    reviewers = os.environ.get("PICKED_REVIEWERS", "")
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
