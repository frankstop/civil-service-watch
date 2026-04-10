# civil-service-watch

Automated daily monitoring of civil service exam pages and job postings across New York City, New York State, surrounding counties, federal government, and MTA.

[![Daily Civil Service Watch](https://github.com/frankstop/civil-service-watch/actions/workflows/daily.yml/badge.svg)](https://github.com/frankstop/civil-service-watch/actions/workflows/daily.yml)

---

## What It Does

Every day, a GitHub Actions workflow automatically:

1. **Fetches** official civil service exam/schedule pages for all configured sources
2. **Extracts** exam titles, filing deadlines, and posting dates from the HTML
3. **Compares** today's content to the previous snapshot
4. **Writes** a clean `latest_report.md` and `latest_report.json` summary
5. **Commits** updated data back to the repo
6. **Publishes** results to a GitHub Pages dashboard

You only need to check when there is an actual change.

---

## Sources Monitored

| Source | Region |
|---|---|
| NYC DCAS | New York City |
| NYS Civil Service | New York State |
| USAJOBS | Federal |
| Nassau County Civil Service | Nassau County |
| Suffolk County Civil Service | Suffolk County |
| Westchester County Civil Service | Westchester County |
| Rockland County Civil Service | Rockland County |
| Orange County Civil Service | Orange County |
| NY Courts | NYS Courts |
| MTA | NYC Metro |

Add or remove sources in [`sources.json`](sources.json).

---

## Dashboard

After the first workflow run, a live dashboard is available at:

```
https://frankstop.github.io/civil-service-watch/
```

---

## Repository Structure

```
civil-service-watch/
├─ .github/
│  └─ workflows/
│     └─ daily.yml          # scheduled GitHub Actions workflow
├─ data/
│  ├─ raw/                  # raw HTML snapshots (gitignored)
│  └─ normalized/           # JSON snapshots per source
├─ history/                 # dated diff/comparison records
├─ docs/
│  ├─ index.html            # GitHub Pages dashboard
│  └─ latest.json           # machine-readable latest report
├─ src/
│  ├─ fetch.py              # download pages → data/normalized/
│  ├─ extract.py            # parse HTML for titles, dates, links
│  ├─ compare.py            # diff current vs previous → history/
│  ├─ build_report.py       # write latest_report.md/.json
│  └─ utils.py              # shared helpers
├─ sources.json             # list of sites to monitor
├─ requirements.txt
├─ latest_report.md         # most recent human-readable report
├─ latest_report.json       # most recent machine-readable report
└─ README.md
```

---

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the full pipeline
python src/fetch.py
python src/extract.py
python src/compare.py
python src/build_report.py

# View the report
cat latest_report.md
```

---

## Enabling GitHub Pages

1. Go to **Settings → Pages** in this repository.
2. Under **Source**, select **GitHub Actions**.
3. The `daily.yml` workflow will deploy the `docs/` folder on each run.

---

## Enabling the Daily Schedule

The workflow runs automatically at **07:00 UTC** every day via the `cron` trigger in `.github/workflows/daily.yml`. No further setup is required after pushing to GitHub.

To trigger a manual run: **Actions → Daily Civil Service Watch → Run workflow**.

---

## Optional Notifications

To add email, Discord, or Slack notifications, add the corresponding step to `.github/workflows/daily.yml` and store your webhook/SMTP credentials as GitHub Secrets.

---

## Upgrade Path

After the basic version is running, consider adding:

- Per-site HTML parsers for deeper structured extraction
- Smarter exam-title normalization and deduplication
- Filtering by job family or region
- Email digest via SMTP GitHub Action
- RSS feed generation
- iPhone-friendly Progressive Web App dashboard
