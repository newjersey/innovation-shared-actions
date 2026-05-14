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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    commands = {
        "auth-test": cmd_auth_test,
        "post-message": cmd_post_message,
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
