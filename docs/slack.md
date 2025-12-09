This documentation as moved to: https://newjersey.github.io/innovation-engineering/guides/shared-github-actions/#slack-notification

---

# Slack Notification Shared Workflow

This is a GitHub Actions workflow that sends notifications to Slack channels. It supports posting a primary message and an optional threaded follow-up message. Repositories within the same GitHub organization can call this workflow to standardize Slack notifications across teams.

---

## How It Works

This workflow wraps the official `slackapi/slack-github-action@v2` integration. It sends:

1. **A primary Slack message** to a specified channel  
2. **An optional threaded message** using the timestamp of the first message  

It calls Slack’s `chat.postMessage` API method under the hood.

[Slack action documentation](https://docs.slack.dev/tools/slack-github-action/sending-techniques/sending-data-slack-api-method/)

---

## Requirements

### 1. Repo must be in the same organization  

This workflow consumes an **organization-level secret**.  

GitHub only allows access to shared workflow secrets if the calling repository is **in the same GitHub org**.

### 2. Add the Slack Notification Bot to Your Slack Channel 

Slack will block messages unless the bot is a member of the channel.

**To add the bot:**

1. Open the Slack channel  
2. Add "Notification Bot" to the channel 
3. Ensure the bot appears in the channel’s integrations list

If you need to make changes to the Skack bot or need to access the key directly, reach out to Tech Ops so you can be added as a [collaborator](https://app.slack.com/app-settings/TDU1D00PK/A09QJADPX32/collaborators).

### 3. Required Secret: `SLACK_OAUTH_TOKEN`  

The workflow expects a secret named: `SLACK_OAUTH_TOKEN` (this is already installed)

This must be configured as an **organization secret**, accessible to any repo using the workflow.

---

## Inputs and Secrets

### Inputs

| Name             | Required | Type   | Description                          |
|------------------|----------|--------|--------------------------------------|
| `channel_id`     | Yes      | string | Slack channel ID (ex: `C09Q36G9HMX`).|
| `message`        | Yes      | string | Main message posted to the channel.  |
| `thread_message` | No       | string | Optional threaded message.           |

### Secrets

| Name                | Required | Description |
|---------------------|----------|-------------|
| `SLACK_OAUTH_TOKEN` | No (but required to function) | Slack bot OAuth token, mapped to `SLACK_BOT_TOKEN` internally. |

---

## Using This Workflow in Your Repository

Create a new workflow file, e.g. `.github/workflows/notify.yml`:

```yaml
name: 'Notify Slack'

on:
    workflow_dispatch:

jobs:
    request-pr-review:
        uses: newjersey/innovation-shared-actions/.github/workflows/slack.yml@main
        with:
            channel_id: C09Q36G9HMX #sandbox
            message: "Something cool happened!"
            thread_message: "And everything is great!" # optional
        secrets: inherit
```
