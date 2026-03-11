"""
Report Generator
Generates HTML report from scored mentions using Jinja2 template.
Updates cumulative mention_log.csv with new entries.
Outputs: public/index.html (for GitLab Pages)
"""

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TEMPLATES_DIR = ROOT / "templates"
PUBLIC_DIR = ROOT / "public"

with open(ROOT / "config" / "scoring.json") as f:
    SCORING = json.load(f)

THRESHOLDS = SCORING["thresholds"]


def load_csv(filepath):
    """Load CSV into list of dicts."""
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def update_mention_log(scored_mentions):
    """Append new scored mentions to the cumulative log."""
    log_file = DATA_DIR / "mention_log.csv"
    existing = load_csv(log_file)
    existing_ids = {m.get("mention_id") for m in existing}

    new_entries = [m for m in scored_mentions if m.get("mention_id") not in existing_ids]

    if not new_entries:
        print("No new entries to add to log.")
        return existing

    all_entries = existing + new_entries

    # Determine fieldnames from all entries
    fieldnames = list(all_entries[0].keys()) if all_entries else []
    # Ensure all fields from new entries are included
    for entry in new_entries:
        for key in entry.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with open(log_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_entries)

    print(f"Updated mention_log.csv: {len(existing)} existing + {len(new_entries)} new = {len(all_entries)} total")
    return all_entries


def generate_report(scored_mentions, all_mentions):
    """Generate HTML report using Jinja2 template."""
    now = datetime.now(timezone.utc)
    scan_date = now.strftime("%B %d, %Y")

    # Brand stats
    brand_counts = Counter(m.get("brand_name", "") for m in scored_mentions)
    brand_stats = [
        {"name": name, "count": count}
        for name, count in brand_counts.most_common()
    ]

    # Content type distribution
    type_counts = Counter(m.get("source_type", "") for m in scored_mentions)
    total = len(scored_mentions) or 1
    type_stats = [
        {
            "type": t.replace("_", " ").title(),
            "count": c,
            "percentage": round(c / total * 100)
        }
        for t, c in type_counts.most_common()
    ]

    # Group mentions by brand
    brands_with_mentions = {}
    for m in scored_mentions:
        brand = m.get("brand_name", "Other")
        if brand not in brands_with_mentions:
            brands_with_mentions[brand] = []
        brands_with_mentions[brand].append(m)

    # Highlights (above highlight threshold)
    highlights = [
        m for m in scored_mentions
        if int(m.get("signal_score", 0)) >= THRESHOLDS["highlight"]
    ]

    # Worthy mentions (above notify threshold)
    worthy = [
        m for m in scored_mentions
        if int(m.get("signal_score", 0)) >= THRESHOLDS["notify"]
    ]

    # Summary stats
    summary = {
        "total_new": len(scored_mentions),
        "total_cumulative": len(all_mentions),
        "highlights": len(highlights),
        "worthy": len(worthy),
        "brands_mentioned": len(brand_counts),
        "top_score": max((int(m.get("signal_score", 0)) for m in scored_mentions), default=0),
    }

    # Load and render template
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("report.html")

    html = template.render(
        scan_date=scan_date,
        scan_period="Daily Scan",
        summary=summary,
        brand_stats=brand_stats,
        type_stats=type_stats,
        brands_with_mentions=brands_with_mentions,
        highlights=highlights,
        worthy=worthy,
        all_new_mentions=scored_mentions,
        all_cumulative=all_mentions,
        thresholds=THRESHOLDS,
    )

    # Write report
    PUBLIC_DIR.mkdir(exist_ok=True)
    output = PUBLIC_DIR / "index.html"
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report generated: {output}")
    return output


def main():
    scored_file = DATA_DIR / "scored_mentions.csv"

    print("=== Report Generation ===")

    # Check flag
    flag = DATA_DIR / "scan_result.txt"
    if flag.exists():
        status = flag.read_text().strip()
        if status == "NO_NEW_MENTIONS":
            print("No new mentions. Skipping report generation.")
            # Still generate a "no new mentions" page
            generate_empty_report()
            return 0
        if status == "NO_WORTHY_MENTIONS":
            print("New mentions found but none above notify threshold.")
            # Still update log and generate report (just won't trigger notify)

    # Load scored mentions
    scored = load_csv(scored_file)
    if not scored:
        print("No scored mentions to report.")
        generate_empty_report()
        return 0

    print(f"Scored mentions: {len(scored)}")

    # Update cumulative log
    all_mentions = update_mention_log(scored)

    # Generate HTML report
    generate_report(scored, all_mentions)

    return len(scored)


def generate_empty_report():
    """Generate a minimal report when there's nothing new."""
    now = datetime.now(timezone.utc)
    PUBLIC_DIR.mkdir(exist_ok=True)

    # Load cumulative stats
    all_mentions = load_csv(DATA_DIR / "mention_log.csv")
    brand_counts = Counter(m.get("brand_name", "") for m in all_mentions)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("report.html")

    html = template.render(
        scan_date=now.strftime("%B %d, %Y"),
        scan_period="Daily Scan (no new mentions)",
        summary={
            "total_new": 0,
            "total_cumulative": len(all_mentions),
            "highlights": 0,
            "worthy": 0,
            "brands_mentioned": len(brand_counts),
            "top_score": 0,
        },
        brand_stats=[{"name": n, "count": c} for n, c in brand_counts.most_common()],
        type_stats=[],
        brands_with_mentions={},
        highlights=[],
        worthy=[],
        all_new_mentions=[],
        all_cumulative=all_mentions,
        thresholds=THRESHOLDS,
    )

    output = PUBLIC_DIR / "index.html"
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Empty report generated: {output}")


if __name__ == "__main__":
    count = main()
    sys.exit(0)
