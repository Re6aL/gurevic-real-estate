# Security notes

The website repository is public. Only information intended for publication may
be committed here.

- Never commit Notion tokens, `.env` files, private CRM exports, client contact
  details, contracts, exact private addresses, or API keys.
- The Notion integration must have read-only access only to the public listing
  database and no access to other workspaces or databases.
- GitHub Secrets are used only by the scheduled `notion-sync` workflow. The
  workflow has no pull-request trigger, so forks cannot receive these secrets.
- Keep write access to this repository limited to trusted people. Anyone able
  to change the workflow on `main` could otherwise misuse its access to secrets.
- If a token may have been exposed, revoke it in Notion immediately and create
  a new read-only integration token.
