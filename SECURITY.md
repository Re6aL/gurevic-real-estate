# Security notes

The website repository is public. Only information intended for publication may
be committed here.

- Never commit Notion tokens, `.env` files, private CRM exports, client contact
  details, contracts, exact private addresses, or API keys.
- Keep write access to this repository limited to trusted people. Anyone able
  to change the workflow on `main` could otherwise misuse its access to secrets.

## Listing data (Notion → GitHub Actions → site)

- The `website` Notion integration has **Read content only** and is connected only
  to the public listing databases ("Objekati" for sales/investments and
  "Najam / Аренда" for long-term rentals) — never to "Website Leads" or other
  workspaces/databases.
- `tools/notion_sync.py` reads only the whitelisted columns in `FIELD_MAP` /
  `FIELD_MAP_RENT`. Owner names, commission, cadastral data (List Nep., Cadastral
  Municipality), documents, people, phone numbers and exact addresses are never
  read or published; only the district is derived from the address. E-mails and
  phone numbers found in description texts are stripped.
- Listings marked `Confidential` (default for hotels, commercial objects,
  businesses and investment land) are anonymized: no CRM title, no photos, no map
  coordinates. The workflow re-applies this after the Dropbox photo sync
  (`notion_sync.py --sanitize`) and removes their photo folders.
- GitHub Secrets (`NOTION_TOKEN`, `NOTION_DB_ID`, `NOTION_RENT_DB_ID`, Dropbox
  credentials) are used only by the scheduled/manual `notion-sync` workflow. The
  workflow has no pull-request trigger, so forks cannot receive these secrets.
  Third-party actions are pinned by commit SHA; Python dependencies are pinned in
  `tools/requirements.txt` and installed into a temporary virtualenv.

## Website leads (forms → Cloudflare Worker → Notion "Website Leads")

- Form submissions go to the Cloudflare Worker in `api/lead-worker/`. Its secrets
  (`NOTION_TOKEN`, `NOTION_LEADS_DB_ID`, optional `TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_CHAT_ID`) live only in Cloudflare (`wrangler secret put`), never in
  the repository or in the static site.
- The Worker uses a **separate** Notion integration `website-leads` with the
  **Insert content capability only**, connected only to "Website Leads". A leaked
  token can add rows but cannot read leads or CRM data. Do not reuse the
  read-only `website` token there, and never give `website-leads` read access.
- The Worker accepts only `POST` from the origins in `ALLOWED_ORIGINS`, limits
  the body to 32 KB, validates fields, drops honeypot/too-fast submissions,
  requires consent, never echoes secrets and logs only error codes (persistent
  Cloudflare logs are disabled). Telegram notifications omit e-mail, phone,
  cadastral and company registration numbers. Add a Cloudflare rate-limiting
  rule for the Worker route.
- Forms never ask for passport data or financial documents.

## Data retention

- "Website Leads" holds personal data. Delete `Spam` rows immediately; review
  `Closed` leads quarterly and delete them 12 months after closing unless a
  contract was signed. Move owners' cadastral data into the private CRM once the
  object is taken on. Keep the database private (no "Share to web").
- The retention period must match the text of the site's `privacy/` page.

## If a token may have been exposed

Revoke it in Notion (my-integrations → integration → Secrets → refresh),
Cloudflare or Dropbox immediately, create a new one with the same minimal
capabilities and update the GitHub / Cloudflare secret.
