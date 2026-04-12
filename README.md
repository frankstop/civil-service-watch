# Civil Service Watch

Automated monitoring for civil service exams, public-sector hiring pages, and related announcement portals across New York agencies and nearby jurisdictions.

[![Daily Civil Service Watch](https://github.com/frankstop/civil-service-watch/actions/workflows/daily.yml/badge.svg)](https://github.com/frankstop/civil-service-watch/actions/workflows/daily.yml)

Live dashboard: [frankstop.github.io/civil-service-watch](https://frankstop.github.io/civil-service-watch/)

## Overview

Civil Service Watch runs a daily pipeline that:

1. Fetches each configured source page.
2. Extracts structured records when possible.
3. Classifies failures such as `not_found`, `bot_blocked`, and `forbidden`.
4. Compares the latest normalized records against the last committed snapshot.
5. Builds a Markdown report, JSON report, and GitHub Pages dashboard.
6. Commits updated artifacts back to the repository through GitHub Actions.

The project is alert-first. The main goal is to surface meaningful changes and actionable listings, not to mirror every source site perfectly.

## Current Coverage

Configured sources live in [`sources.json`](sources.json).

| Source | Region | Current behavior |
|---|---|---|
| NYC DCAS | New York City | Structured table extraction |
| NYS Civil Service | New York State | Structured table extraction |
| USAJOBS | Federal | Search summary normalization |
| Nassau County Civil Service | Nassau County | Structured listing extraction from the source site's first-party XHR |
| Suffolk County Civil Service | Suffolk County | Currently blocked by bot protection |
| Westchester County Civil Service | Westchester County | Structured table extraction |
| Rockland County Civil Service | Rockland County | Currently forbidden from automation |
| Orange County Civil Service | Orange County | Structured text-based listing extraction |
| NY Courts | NYS Courts | Currently blocked by bot protection |
| MTA | NYC Metro | Curated career/exam entry points |

As of the latest generated report, 7 sources are accessible from automation and 3 remain restricted by source controls. Those restricted links remain in the report because they are still useful for human follow-up, but the project does not attempt to recover them with alternate endpoints or browser-assisted fetching.

## How It Works

The pipeline is split into four small scripts:

- [`src/fetch.py`](src/fetch.py)
  - Downloads each source.
  - Saves raw HTML under `data/raw/`.
  - Stores Nassau's listing XHR snapshot under `data/raw/nassau_county_listings.html`.
  - Stores normalized fetch metadata under `data/normalized/<source>.json`.
  - Records HTTP status, resolved URL, fetch classification, and a stable content hash.

- [`src/extract.py`](src/extract.py)
  - Re-processes fetched snapshots into structured output.
  - Writes `data/normalized/<source>_extracted.json`.
  - Produces normalized records, summary notes, links, dates, and record fingerprints.

- [`src/compare.py`](src/compare.py)
  - Compares today’s extracted records against the last committed version.
  - Prefers record-level fingerprints over noisy whole-page diffs.
  - Writes a dated entry in `history/`.

- [`src/build_report.py`](src/build_report.py)
  - Generates `latest_report.md`, `latest_report.json`, `docs/latest.json`, and `docs/history.json`.
  - These outputs drive both the repository report and the GitHub Pages dashboard.

Source-aware parsing lives in [`src/source_extractors.py`](src/source_extractors.py). That module handles table extraction, Orange County’s text-based list format, MTA’s curated career links, and the general fallback logic used by the pipeline.

## Repository Layout

```text
civil-service-watch/
├─ .github/
│  └─ workflows/
│     └─ daily.yml
├─ data/
│  ├─ raw/
│  └─ normalized/
├─ docs/
│  ├─ history.json
│  ├─ index.html
│  └─ latest.json
├─ history/
├─ src/
│  ├─ build_report.py
│  ├─ compare.py
│  ├─ extract.py
│  ├─ fetch.py
│  ├─ source_extractors.py
│  └─ utils.py
├─ tests/
├─ latest_report.json
├─ latest_report.md
├─ requirements.txt
├─ sources.json
└─ README.md
```

## Generated Data

### Normalized fetch snapshot

Each source writes `data/normalized/<source>.json` with fields such as:

- `status`
- `status_detail`
- `http_status`
- `resolved_url`
- `content_hash`
- `summary_note`
- `record_count`
- `error`

### Extracted source snapshot

Each successful source writes `data/normalized/<source>_extracted.json` with fields such as:

- `records`
- `record_count`
- `record_fields_present`
- `record_fingerprint`
- `summary_note`
- `exam_titles`
- `dates`
- `links`

### Daily report

The main report files are:

- [`latest_report.md`](latest_report.md)
- [`latest_report.json`](latest_report.json)
- [`docs/latest.json`](docs/latest.json)
- [`docs/history.json`](docs/history.json)

The dashboard in [`docs/index.html`](docs/index.html) fetches `docs/latest.json` for the latest run and `docs/history.json` for the historical archive view.

## Dashboard Behavior

The GitHub Pages dashboard is designed to be readable without opening the repo:

- Shows overall counts for sources, changes, and fetch errors.
- Shows a PR-friendly source-health summary and daily delta rollup.
- Includes a History tab with prior daily runs and per-source daily summaries.
- Renders structured records for sources that expose exam/job rows.
- Shows summary notes for sources where a compact summary is more useful than raw page text.
- Preserves real error categories for failed sources instead of a generic “check URL” message.

## Running Locally

### Prerequisites

- Python 3.12+
- Internet access for live source fetches

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run the pipeline

```bash
python src/fetch.py
python src/extract.py
python src/compare.py
python src/build_report.py
```

### Run tests

```bash
python -m unittest discover -s tests -v
```

### Inspect results

```bash
cat latest_report.md
python -m json.tool latest_report.json | less
```

## GitHub Actions and Pages

The scheduled workflow is defined in [`.github/workflows/daily.yml`](.github/workflows/daily.yml).

It currently:

1. Installs Python dependencies.
2. Runs the four pipeline scripts.
3. Commits updated normalized data and reports.
4. Deploys the `docs/` directory to GitHub Pages.

To enable Pages:

1. Open repository **Settings → Pages**.
2. Set **Source** to **GitHub Actions**.

To trigger the workflow manually:

1. Open **Actions**.
2. Select **Daily Civil Service Watch**.
3. Choose **Run workflow**.

## Known Limitations

- Some public-sector sites use bot protection, JavaScript challenges, or restrictive edge rules that block plain HTTP automation.
- Not every source currently exposes structured records in static HTML.
- Some sites are better represented as “official entry points” than as row-by-row exam tables.

Current blocked/problematic sources:

- Suffolk County Civil Service
- Rockland County Civil Service
- NY Courts

These are intentionally reported as blocked or forbidden when automation cannot reach them. The project does not recover them with alternate endpoints or browser-assisted fetching. Their official links remain in the reports so a human can still inspect them directly.

## Development Notes

- Keep changes additive and source-aware. One generic scraper path is not enough for these sites.
- Prefer comparing normalized records instead of whole-page text whenever possible.
- When adding a source, update both `sources.json` and `src/source_extractors.py` if that source needs custom parsing.
- Regenerate report artifacts after any source or parser change so the dashboard stays consistent with the code.

## Roadmap

Likely next improvements:

- Expand source-specific field coverage further for job-board style listings.
- Add more fixture-backed regressions as new source layouts are introduced.
- Surface richer source-health summaries in the dashboard UI.
