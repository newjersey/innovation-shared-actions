# Pickaroo: PR reviewers picker

This GitHub Action selects and assigns PR reviewers from GitHub groups.

The Pickaroo action at `.github/actions/pickaroo/action.yml` will randomly select reviewers from the included team(s) who are collaborators on the repository, ignoring anyone in the excluded team(s). It will not pick the PR author, and will not pick anyone who has already been requested for review.

It might, however, pick people who have already submitted a review (this is an edge case to polish).

## Inputs and Secrets

### Inputs

| Name                  | Required | Type   | Description                                                                |
| --------------------- | -------- | ------ | -------------------------------------------------------------------------- |
| `include-teams`       | Yes      | string | The github teams to pick reviewers from (space delimited)                  |
| `exclude-teams`       | No       | string | The github teams to exclude reviewers from (space delimited)               |
| `number-of-reviewers` | No       | string | The number of reviewers to select, defaults to 1                           |
| `token`               | Yes      | string | Github token with org:teams:read and repo:pull_requests:write permissions. |
