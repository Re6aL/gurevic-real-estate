# November 2026 update — work log

Source: owner-provided eight-page change brief, two agreement PDFs and portrait, received 2026-11-05. The source brief contains credentials and must never be committed. Private working files remain outside this repository.

## Implemented

- Added the director portrait, legal company details, official registry link and downloadable agreement samples.
- Corrected the apartment-sale commission to 5% including VAT, paid only by the seller; other cases are by written agreement.
- Added Montenegrin as the eighth complete site language under `/me/`; updated all new content in every language.
- Added buyer pages for twelve areas, a separate new-development route, service FAQ and sourced guides on buying, taxes, residence, documents/legalisation and returns/seasonality.
- Added consent-gated Yandex Metrica 113834531. Session replay, click map and form-content capture are disabled. GA4/GTM and webmaster verification remain optional empty configuration values.
- Fixed shared form alignment and Hebrew RTL contact layouts; optimised the portrait from 5.9 MB to generated 0.2 MB derivatives.
- Prepared `gurevic.estate` canonical URLs, `CNAME`, sitemap, robots rules and Cloudflare Worker origins.
- Reconnected Notion. `Website Leads` remains the complete incoming queue; its Language options now include Crnogorski. The older `Klijenati i zahtevi` database is retained unchanged for its existing records.
- Created private Notion databases `AI Visibility Monitor` (20 requested baseline provider/query combinations) and `AML Review Register` (minimal-data, human-reviewed workflow; no passport uploads).

## Validation

- Strict generator check: 720 page specifications, zero missing translations or template errors.
- Built output: 728 generated files.
- Link and HTML check: 726 pages, 118,992 internal links, zero errors and zero warnings.
- Python sync/generator tests: 44 passed. Cloudflare Worker tests: 25 passed.
- Desktop, mobile Montenegrin and mobile Hebrew screenshots reviewed; no document-width overflow was found.

## External setup still required

- Add the GitHub Pages DNS records in Spaceship, then enable the GitHub Pages custom domain and HTTPS. Browser automation currently cannot create or attach to a Chrome tab because the Chrome extension returns a `timeoutMs` error.
- Forms continue to use the safe WhatsApp/Telegram/e-mail fallback until a dedicated Notion integration token is stored in Cloudflare. Telegram notifications additionally require a bot token and destination chat ID.
- Add optional GA4/GTM and search-engine verification IDs if those accounts are wanted.

## Owner questions

- Both supplied agreement PDFs contain exclusivity clauses. Request a separate non-exclusive sample if the first download should be presented as non-exclusive.
- The brief sentence requesting an additional property field ends after “add field only”; the field name is missing.
- Confirm the AML responsible person, authorised users, retention period and counsel-approved procedure before real client cases are entered.

Existing untracked `SITE_AUDIT_2026-08-21.md` belongs to the user and is excluded from this update.
