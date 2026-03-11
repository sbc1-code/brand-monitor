"""
Signal Scoring Engine
Scores new mentions based on source authority, content depth, recency, and sentiment.
Outputs: scored_mentions.csv with signal_score column added.

This is Trigger 2: "Is it worthy?"
Only mentions above the notify threshold generate alerts.
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"

with open(CONFIG_DIR / "scoring.json") as f:
    SCORING = json.load(f)

with open(CONFIG_DIR / "brands.json") as f:
    BRANDS = json.load(f)

THRESHOLDS = SCORING["thresholds"]


def score_source_authority(source_type):
    """Score based on source type."""
    weights = SCORING["scoring_rules"]["source_authority"]["weights"]
    return weights.get(source_type, 10)


def score_content_depth(title, snippet, brand_keywords):
    """Score based on how substantive the mention is."""
    text = f"{title} {snippet}".lower()
    rules = SCORING["scoring_rules"]["content_depth"]

    # Check for product-specific mention
    product_terms = [
        "minireel", "microdrain", "mini pro", "compact", "sr-24", "sr-20",
        "epsilon scout", "gammacam pro", "smartsense", "digital self-leveling",
        "brandzeta live", "brandalpha", "brandbeta"
    ]
    for term in product_terms:
        if term.lower() in text:
            return rules["product_specific"]

    # Check for deep mention (longer text, multiple keyword hits)
    keyword_hits = sum(1 for kw in brand_keywords if kw.strip('"').lower() in text)
    if keyword_hits >= 2 or len(snippet) > 300:
        return rules["deep_mention"]

    return rules["brand_only"]


def score_recency(published_date):
    """Score based on how recent the content is."""
    rules = SCORING["scoring_rules"]["recency"]

    if not published_date:
        return rules["within_90_days"]  # Unknown date, assume moderate

    try:
        pub = datetime.strptime(published_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days_ago = (now - pub).days

        if days_ago <= 7:
            return rules["within_7_days"]
        elif days_ago <= 30:
            return rules["within_30_days"]
        elif days_ago <= 90:
            return rules["within_90_days"]
        elif days_ago <= 180:
            return rules["within_180_days"]
        else:
            return rules["older"]
    except ValueError:
        return rules["within_90_days"]


def score_sentiment(title, snippet):
    """Basic sentiment detection from text."""
    rules = SCORING["scoring_rules"]["sentiment"]
    text = f"{title} {snippet}".lower()

    negative_signals = [
        "complaint", "problem", "issue", "broken", "doesn't work",
        "poor quality", "disappointed", "waste of money", "terrible",
        "water ingress", "not working", "bug", "crash"
    ]
    positive_signals = [
        "excellent", "best", "recommended", "impressive", "reliable",
        "professional-grade", "top pick", "love it", "worth", "durable",
        "game changer", "easy to use"
    ]

    neg_count = sum(1 for s in negative_signals if s in text)
    pos_count = sum(1 for s in positive_signals if s in text)

    if neg_count > pos_count:
        return rules["negative"], "negative"
    elif pos_count > neg_count:
        return rules["positive"], "positive"
    return rules["neutral"], "neutral"


def score_first_party(is_first_party, is_partner):
    """Penalty for first-party or partner content."""
    rules = SCORING["scoring_rules"]["first_party_penalty"]
    if str(is_first_party).lower() == "true":
        return rules["first_party"]
    if str(is_partner).lower() == "true":
        return rules["partner_reseller"]
    return 0


def score_mention(mention):
    """Calculate total signal score for a mention."""
    # Find brand config for keywords
    brand_config = next(
        (b for b in BRANDS["brands"] if b["id"] == mention.get("brand_id")),
        {"keywords": []}
    )

    authority = score_source_authority(mention.get("source_type", ""))
    depth = score_content_depth(
        mention.get("title", ""),
        mention.get("snippet", ""),
        brand_config["keywords"]
    )
    recency = score_recency(mention.get("published_date", ""))
    sentiment_score, sentiment_label = score_sentiment(
        mention.get("title", ""), mention.get("snippet", "")
    )
    first_party = score_first_party(
        mention.get("is_first_party", "False"),
        mention.get("is_partner_or_reseller", "False")
    )

    total = max(0, authority + depth + recency + sentiment_score + first_party)

    return total, sentiment_label


def main():
    new_file = DATA_DIR / "new_mentions.csv"
    scored_file = DATA_DIR / "scored_mentions.csv"

    print("=== Signal Scoring ===")

    # Check if there are new mentions
    flag = DATA_DIR / "scan_result.txt"
    if flag.exists() and flag.read_text().strip() == "NO_NEW_MENTIONS":
        print("No new mentions to score.")
        # Write empty scored file
        with open(scored_file, "w") as f:
            f.write("")
        return 0

    # Load new mentions
    if not new_file.exists():
        print("No new_mentions.csv found.")
        return 0

    with open(new_file, "r", encoding="utf-8") as f:
        mentions = list(csv.DictReader(f))

    if not mentions:
        print("No mentions to score.")
        return 0

    print(f"Scoring {len(mentions)} new mentions...")

    # Score each mention
    scored = []
    for m in mentions:
        signal_score, sentiment = score_mention(m)
        m["signal_score"] = signal_score
        m["sentiment"] = sentiment
        scored.append(m)

    # Sort by score descending
    scored.sort(key=lambda x: int(x["signal_score"]), reverse=True)

    # Report thresholds
    above_notify = [m for m in scored if int(m["signal_score"]) >= THRESHOLDS["notify"]]
    above_highlight = [m for m in scored if int(m["signal_score"]) >= THRESHOLDS["highlight"]]

    print(f"Total scored: {len(scored)}")
    print(f"Above notify threshold ({THRESHOLDS['notify']}): {len(above_notify)}")
    print(f"Above highlight threshold ({THRESHOLDS['highlight']}): {len(above_highlight)}")

    # Write scored mentions
    fieldnames = list(scored[0].keys())
    with open(scored_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(scored)

    print(f"Wrote: {scored_file}")

    # Update flag with worthy count
    if above_notify:
        flag.write_text(f"WORTHY_MENTIONS:{len(above_notify)}")
    else:
        flag.write_text("NO_WORTHY_MENTIONS")

    return len(above_notify)


if __name__ == "__main__":
    count = main()
    sys.exit(0)
