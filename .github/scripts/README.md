# Python Scripts for GitHub Actions

Python scripting was introduced to increase maintainability and testability of the complex scripting used for the shared actions in this repo, which enable various automations for our org.

The only dependencies we currently have are on `requests` and `pytest`. `requests` is available by default on GH ubuntu runners, so we only need to install dependencies when we're running tests.

## Pickaroo

This script supports handling all of the primary tasks of the Pickaroo workflow:

- Querying for the PR comment that stores slack message timestamp and previously requested reviewers
- Building the correct Slack messages to send based on selected reviewers and other inputs
- Posting/Updating the PR comment with fresh metadata
