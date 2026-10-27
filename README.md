# Orrivon AI Client Hunter — Local MVP

A small **Windows desktop prototype** for researching B2B prospects and drafting personalized outreach. Runs on Python's standard library (Tkinter, SQLite, urllib) with no paid API required for core features.

> **Not** a mass-scraper or auto-DM bot. Does not send emails, WhatsApp messages, or LinkedIn messages. Human review and manual outreach only. Public source data can be missing, incorrect or outdated; verify every prospect.

## Quick start (Windows)

1. Extract ZIP to `Desktop\AI-Business\AI-Client-Hunter` or any folder.
2. Open that folder in VS Code.
3. VS Code Terminal → run `python app.py` (or `py app.py`).
4. Select `Dubai, UAE` + `Salons & barbers` and click **Find businesses**. Internet access is required for discovery and website audit. One search could take 10–50 seconds depending on a third-party server.
5. Select a business → **Open website** / **Audit site** → **Draft template** → edit draft → **Save edited draft** → **Approve** → **Copy**. Send manually, only if outreach is appropriate and lawfully compliant.
6. **Export CSV** for portfolio/CRM tracking. The local SQLite database is automatically created in `data/client_hunter.sqlite3`.

If the GUI fails to open, run `python -m tkinter` to confirm Tkinter exists. If you see a command-not-found error, try `py app.py`.

## Optional: real local AI drafts (no paid API)

1. Install [Ollama](https://ollama.com/download) separately, if desired.
2. Open another terminal: `ollama pull qwen2.5:0.5b`.
3. Keep Ollama running, then select a lead and click **Local AI (optional)**. The app contacts only the local `127.0.0.1:11434` endpoint.
4. This is a very small model to reduce memory usage on an 8GB laptop; writing quality may need editing. Default **Draft template** works without Ollama.

## Features

- Local public business discovery by city + sector (small Overpass queries)
- Deduplication and storage in SQLite
- Basic homepage checks: title, meta description, mobile viewport tag, contact/booking links, HTTPS
- Transparent evidence-based research score; this is **not** a full SEO audit or guaranteed diagnosis
- One-click first-draft generation with local rule-based template, optional Ollama drafting
- Approval + manual outreach tracking (`New`, `Drafted`, `Approved`, `Contacted`, etc.)
- Editable messages, clipboard copy, CSV export
- Manual prospect entry and opening original OpenStreetMap listing

## Important limits & responsible use

- **OpenStreetMap data © OpenStreetMap contributors, ODbL**. See https://www.openstreetmap.org/copyright. Preserve attribution when redistributing exports or derived datasets.
- The public Overpass endpoint (`overpass-api.de`) is community-run, best-effort, subject to policies and rate limits. This MVP uses very small queries (max 70 records, limited radius), at least 45s between searches, and prevents duplicate searches in a session. Do not scale it for commercial bulk use without appropriate infrastructure and permission. It can return HTTP 429/504 errors; try again later, not in a rapid loop.
- This tool **does not guarantee contact emails**. Only emails explicitly listed in mapped business tags are imported, and may be inaccurate. Never fabricate email addresses.
- Homepages may block automated fetching or disallow robots; the audit respects robots.txt when it can determine permission. It doesn't log into sites or crawl directories.
- Scores are **research priorities** based on detected page features and absence of an OSM website. They do not establish that a business needs a particular service.
- No automatic outreach. Review each prospect, respect terms and marketing laws, provide clear identity and opt-out where applicable, and do not contact people who have opted out.
- SQLite database + CSV contain business records, so keep them private. Never upload `data/` to GitHub; `.gitignore` excludes it.

## Project structure

```text
Orrivon_AI_Client_Hunter/
  app.py               # Desktop UI
  core.py              # Business discovery, audit, drafting, persistence
  README.md
  requirements.txt     # No pip dependencies
  .gitignore
  tests/test_core.py
  data/                # Local SQLite DB created on first launch, gitignored
```

## Tests

Run: `python -m unittest discover -s tests -v`

## Roadmap

- Real lead filters (website quality, contact availability) + source-validation checks
- Website audit report output (PDF/HTML)
- Better lead qualification workflows and opt-out suppression list
- Case study + portfolio video
- Integration with the earlier CleanOps CRM architecture (not currently integrated)

Built as an Orrivon Digital portfolio prototype.
