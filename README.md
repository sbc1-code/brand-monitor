# Brand Monitor

Self-hosted brand mention monitoring for teams that need a lightweight public report without buying an enterprise media-monitoring suite.

Live report: [sbc1-code.github.io/brand-monitor](https://sbc1-code.github.io/brand-monitor/)

## What It Does

The pipeline:

1. Scans Google News RSS, Reddit search, and configured RSS feeds for brand mentions.
2. Verifies that the brand actually appears in the result text.
3. Deduplicates against a cumulative mention log.
4. Scores each mention by source authority, content depth, recency, sentiment, and first-party/partner flags.
5. Generates a static HTML report for GitHub Pages.
6. Creates a GitHub issue when mentions pass the notification threshold.

## Default Configuration

The checked-in config tracks real public example brands so the repo works immediately after cloning or forking:

- OpenAI
- GitHub
- Vercel

Replace `config/brands.json` with your own brands, keywords, product patterns, and first-party domains before using it for your organization.

## Configuration Files

- `config/brands.json` - brands, keywords, product patterns, and exclude patterns
- `config/sources.json` - no-key feeds plus optional API source toggles
- `config/scoring.json` - scoring weights and report/notify/highlight thresholds

## Running Locally

```bash
pip install -r requirements.txt
python scripts/scan.py
python scripts/dedup.py
python scripts/score.py
python scripts/report.py
```

The report writes to both `index.html` and `public/index.html`.

## GitHub Actions

`.github/workflows/update-report.yml` runs daily and on manual dispatch:

```text
scan -> dedup -> score -> report -> notify -> commit report
```

GitHub provides `GITHUB_TOKEN` automatically for issue creation. Optional API-backed sources need secrets before being enabled:

- Google Custom Search API: `GOOGLE_CSE_KEY` and `GOOGLE_CSE_CX`
- YouTube Data API: `YOUTUBE_API_KEY` (scanner is disabled until implemented)
- GA4 referral data: `GA4_SERVICE_ACCOUNT_JSON` (not enabled by default)

## Production Notes

- The cumulative mention log can be committed as `data/mention_log.csv`; keep it public only if your monitored brands and mentions are safe to expose.
- The default no-key sources can rate-limit or return quiet periods. Treat zero mentions as a signal to inspect scanner health, not automatic proof that no mentions exist.
- External titles/snippets are rendered with Jinja autoescaping enabled.

## Tests

```bash
python -m unittest discover -s tests
```
