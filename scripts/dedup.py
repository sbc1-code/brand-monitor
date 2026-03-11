"""
Deduplication Engine
Compares raw_mentions.csv against mention_log.csv to find genuinely new mentions.
Outputs: new_mentions.csv (only what's new since last scan)

This is Trigger 1: "Is there anything new?"
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def load_csv(filepath):
    """Load CSV file into list of dicts."""
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_known_ids(filepath):
    """Load just the mention_ids from the cumulative log."""
    known = set()
    if not filepath.exists():
        return known
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            known.add(row.get("mention_id", ""))
    return known


def main():
    raw_file = DATA_DIR / "raw_mentions.csv"
    log_file = DATA_DIR / "mention_log.csv"
    new_file = DATA_DIR / "new_mentions.csv"

    print("=== Deduplication ===")

    # Load raw scan results
    raw_mentions = load_csv(raw_file)
    print(f"Raw mentions from scan: {len(raw_mentions)}")

    # Load known mention IDs
    known_ids = load_known_ids(log_file)
    print(f"Known mentions in log: {len(known_ids)}")

    # Filter to truly new
    new_mentions = [m for m in raw_mentions if m.get("mention_id") not in known_ids]
    print(f"New mentions found: {len(new_mentions)}")

    if not new_mentions:
        print("No new mentions. Pipeline can stop here.")
        # Write empty file so downstream stages know
        with open(new_file, "w", newline="", encoding="utf-8") as f:
            if raw_mentions:
                writer = csv.DictWriter(f, fieldnames=raw_mentions[0].keys())
                writer.writeheader()
            else:
                f.write("")
        # Exit with code 0 but write a flag file
        flag = DATA_DIR / "scan_result.txt"
        flag.write_text("NO_NEW_MENTIONS")
        return 0

    # Write new mentions
    with open(new_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=new_mentions[0].keys())
        writer.writeheader()
        writer.writerows(new_mentions)

    print(f"Wrote: {new_file}")

    # Write flag
    flag = DATA_DIR / "scan_result.txt"
    flag.write_text(f"NEW_MENTIONS:{len(new_mentions)}")

    return len(new_mentions)


if __name__ == "__main__":
    count = main()
    sys.exit(0)
