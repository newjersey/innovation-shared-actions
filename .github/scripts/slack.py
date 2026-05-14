import json
import os
import sys

import requests

# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------


def auth_test(token: str) -> dict:
    """Validate a Slack token. Returns the JSON response.

    https://docs.slack.dev/reference/methods/auth.test
    """
    response = requests.post(
        "https://slack.com/api/auth.test",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return response.json()


def post_message(
    token: str,
    channel: str,
    text: str,
    username: str,
    icon_url: str,
    icon_emoji: str,
    thread_ts: str = "",
) -> str:
    """Post a message to Slack via chat.postMessage. Returns the message timestamp.

    https://docs.slack.dev/reference/methods/chat.postMessage
    """
    text = text.replace("\\n", "\n")
    payload = {"channel": channel, "markdown_text": text}
    if username:
        payload["username"] = username
    # prefer a url over emoji, contrary to the API
    if icon_url:
        payload["icon_url"] = icon_url
    elif icon_emoji:
        payload["icon_emoji"] = icon_emoji

    if thread_ts:
        payload["thread_ts"] = thread_ts

    response = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data.get('error', 'unknown')}")
    return data["ts"]


def update_message(
    token: str,
    channel: str,
    ts: str,
    text: str,
    username: str,
    icon_url: str,
    icon_emoji: str,
) -> str:
    """Update an existing Slack message via chat.update. Returns the message timestamp.

    https://docs.slack.dev/reference/methods/chat.update
    """
    text = text.replace("\\n", "\n")
    payload = {"channel": channel, "ts": ts, "markdown_text": text}
    if username:
        payload["username"] = username
    if icon_url:
        payload["icon_url"] = icon_url
    elif icon_emoji:
        payload["icon_emoji"] = icon_emoji

    response = requests.post(
        "https://slack.com/api/chat.update",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data.get('error', 'unknown')}")
    return data["ts"]


def find_message(token: str, channel: str, message_ts: str) -> bool:
    """Check if a message exists in a Slack channel using conversations.history.

    Returns True if the message is found with matching timestamp, False otherwise.

    https://docs.slack.dev/reference/methods/conversations.history
    """
    response = requests.get(
        "https://slack.com/api/conversations.history",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "channel": channel,
            "latest": message_ts,
            "limit": "1",
            "inclusive": "true",
        },
    )
    response.raise_for_status()
    data = response.json()

    if not data.get("ok"):
        return False

    messages = data.get("messages", [])
    if not messages:
        return False

    return messages[0].get("ts") == message_ts


def get_profile(token: str, user_id: str) -> dict:
    """Fetch a Slack user's profile via users.profile.get.

    Returns the profile dict (display_name, real_name, image_512, fields, etc.).

    https://docs.slack.dev/reference/methods/users.profile.get
    """
    response = requests.get(
        "https://slack.com/api/users.profile.get",
        headers={"Authorization": f"Bearer {token}"},
        params={"user": user_id},
    )
    response.raise_for_status()
    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data.get('error', 'unknown')}")

    return data.get("profile", {})


def list_users(token: str) -> list[str]:
    """Fetch all active, non-bot user IDs from Slack via users.list (paginated).

    Excludes deleted users, bots, and slackbot.

    https://docs.slack.dev/reference/methods/users.list
    """
    all_ids = []
    cursor = ""

    while True:
        params = {"limit": "300"}
        if cursor:
            params["cursor"] = cursor

        response = requests.get(
            "https://slack.com/api/users.list",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            raise RuntimeError(f"Slack API error: {data.get('error', 'unknown')}")

        for member in data.get("members", []):
            if (
                not member.get("deleted", False)
                and not member.get("is_bot", False)
                and member.get("name") != "slackbot"
            ):
                all_ids.append(member["id"])

        cursor = data.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            break

    return all_ids


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_auth_test():
    """Validate a Slack token. Exits 1 if invalid."""
    token = os.environ["TOKEN"]
    github_output = os.environ.get("GITHUB_OUTPUT", "")

    data = auth_test(token)

    if not data.get("ok"):
        error = data.get("error", "unknown_error")
        print(f"ERROR: Slack Auth failed: {error}", file=sys.stderr)
        sys.exit(1)

    print("Slack token is valid.")
    if github_output:
        with open(github_output, "a") as f:
            f.write("valid=true\n")


def cmd_post_message():
    """Post a new message to a Slack channel."""
    token = os.environ["TOKEN"]
    channel = os.environ["CHANNEL_ID"]
    text = os.environ["MESSAGE"]
    username = os.environ.get("USERNAME", "")
    icon_url = os.environ.get("AVATAR_URL", "")
    icon_emoji = os.environ.get("AVATAR_EMOJI", "")
    thread_ts = os.environ.get("THREAD_TS", "")
    github_output = os.environ.get("GITHUB_OUTPUT", "")

    ts = post_message(
        token=token,
        channel=channel,
        text=text,
        username=username,
        icon_url=icon_url,
        icon_emoji=icon_emoji,
        thread_ts=thread_ts,
    )

    print(f"Successfully sent message (ts: {ts})")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"ts={ts}\n")


def cmd_update_message():
    """Update an existing Slack message."""
    token = os.environ["TOKEN"]
    channel = os.environ["CHANNEL_ID"]
    message_ts = os.environ["MESSAGE_TS"]
    text = os.environ["MESSAGE"]
    username = os.environ.get("USERNAME", "")
    icon_url = os.environ.get("AVATAR_URL", "")
    icon_emoji = os.environ.get("AVATAR_EMOJI", "")
    github_output = os.environ.get("GITHUB_OUTPUT", "")

    ts = update_message(
        token=token,
        channel=channel,
        ts=message_ts,
        text=text,
        username=username,
        icon_url=icon_url,
        icon_emoji=icon_emoji,
    )

    print(f"Successfully updated message (ts: {ts})")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"ts={ts}\n")


def cmd_find_message():
    """Find a message in a Slack channel. Exits 1 if not found."""
    token = os.environ["TOKEN"]
    channel = os.environ["CHANNEL_ID"]
    message_ts = os.environ["MESSAGE_TS"]

    if not find_message(token, channel, message_ts):
        print(
            f"ERROR: Message {message_ts} not found in channel {channel}. Is your channel_id correct?",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Found parent message (ts: {message_ts})")


def cmd_list_users():
    """Fetch all active Slack user IDs and output as JSON array."""
    token = os.environ["TOKEN"]
    github_output = os.environ.get("GITHUB_OUTPUT", "")

    user_ids = list_users(token)

    print(f"Found {len(user_ids)} active users")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"user_ids={json.dumps(user_ids)}\n")


def cmd_map_github_to_slack():
    """Build a GitHub-to-Slack user mapping from Slack profile fields.

    Fetches all active users, reads their profiles, and extracts GitHub
    usernames from configured profile fields. Outputs a JSON mapping to
    GITHUB_OUTPUT as 'github-slack-mapping'.

    Env vars:
      TOKEN: Slack OAuth token
      SLACK_FIELD: Profile field key containing GitHub username
      BACKUP_FIELD: (optional) Fallback field to regex-match "GH: <username>"
      GITHUB_OUTPUT: Path to GitHub Actions output file
    """
    import re

    token = os.environ["TOKEN"]
    slack_field = os.environ["SLACK_FIELD"]
    backup_field = os.environ.get("BACKUP_FIELD", "")
    github_output = os.environ.get("GITHUB_OUTPUT", "")

    user_ids = list_users(token)
    print(f"Found {len(user_ids)} active users")

    github_slack_map = {}

    for user_id in user_ids:
        try:
            profile = get_profile(token, user_id)
        except RuntimeError as e:
            print(f"  Skipping {user_id}: {e}")
            continue

        display_name = profile.get("display_name") or profile.get("real_name") or "Unknown"
        fields = profile.get("fields") or {}

        github_username = ""
        primary = fields.get(slack_field, {})
        if primary and primary.get("value"):
            github_username = primary["value"]

        if not github_username and backup_field:
            backup = fields.get(backup_field, {})
            backup_value = backup.get("value", "") if backup else ""
            if backup_value:
                match = re.search(r"(?:GH|GitHub):\s*([A-Za-z0-9_-]+)", backup_value, re.IGNORECASE)
                if match:
                    github_username = match.group(1)

        if github_username:
            print(f"  Found GitHub username for {display_name} ({user_id}): {github_username}")
            github_slack_map[github_username] = {
                "id": user_id,
                "username": display_name,
                "avatar_url": profile.get("image_512", ""),
            }

    print(f"Mapped {len(github_slack_map)} GitHub users")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"github-slack-mapping={json.dumps(github_slack_map)}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    commands = {
        "auth-test": cmd_auth_test,
        "post-message": cmd_post_message,
        "update-message": cmd_update_message,
        "find-message": cmd_find_message,
        "list-users": cmd_list_users,
        "map-github-to-slack": cmd_map_github_to_slack,
    }
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in commands:
        print(
            f"Unknown command: {command!r}. Available: {', '.join(commands)}",
            file=sys.stderr,
        )
        sys.exit(1)
    commands[command]()


if __name__ == "__main__":
    main()
