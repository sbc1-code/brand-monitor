# Brand Monitor

Automated brand mentions and syndication tracking for a multi-brand portfolio.

## What It Does

Daily scheduled pipeline that:

1. **Scans** Google News RSS, Reddit, and known trade publication feeds for brand mentions
2. **Deduplicates** against a cumulative mention log (Trigger 1: anything new?)
3. **Scores** each mention by source authority, content depth, recency, and sentiment (Trigger 2: is it worthy?)
4. **Reports** via HTML report deployed to GitLab Pages
5. **Notifies** by creating a GitLab issue when worthy mentions are found

## Brands Tracked

- BrandAlpha (parent brand)
- BrandBeta Pro (product line A)
- BrandGamma Systems (product line B)
- BrandDelta Locators (product line C)
- BrandEpsilon Track (product line D)
- BrandZeta Live (mobile app)

## Pipeline Stages

```
scan -> dedup -> score -> report -> notify -> pages
```

## Configuration

- `config/brands.json` - Brand keywords and scan settings
- `config/sources.json` - Data source configs (active + future API stubs)
- `config/scoring.json` - Signal scoring rules and thresholds

## API Integrations

Implemented and gated by config/vars:
- Google Custom Search API (set `GOOGLE_CSE_KEY` + `GOOGLE_CSE_CX`, then enable `google_custom_search` in `config/sources.json`)

Planned stubs:
- YouTube Data API v3 (set `YOUTUBE_API_KEY`)
- Google Analytics 4 (set `GA4_SERVICE_ACCOUNT_JSON`)

Set CI/CD variables and enable each source in `config/sources.json`.

## Running Locally

```bash
pip install -r requirements.txt
python scripts/scan.py
python scripts/dedup.py
python scripts/score.py
python scripts/report.py
```

## Report

Latest report: [GitLab Pages](https://pages.example.com/brand-monitor)
