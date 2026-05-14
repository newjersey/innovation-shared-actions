import json
import os
import sys

import requests

# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------


def auth_test(token: str) -> dict:
    """POST https://slack.com/api/auth.test — returns the JSON response."""
    response = requests.post(
        "https://slack.com/api/auth.test",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return response.json()


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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    commands = {
        "auth-test": cmd_auth_test,
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
