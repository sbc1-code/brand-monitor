"""
Seed the mention_log.csv with synthetic example brand mentions.
Run once to initialize the cumulative log with historical data.
"""

import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# Import scoring
sys.path.insert(0, str(ROOT / "scripts"))
from score import score_mention

# Synthetic example data demonstrating the data schema across brand types
SEED_DATA = [
    {
        "brand": "BrandGamma Systems", "brand_id": "brandgamma",
        "product": "GammaCam Pro",
        "source_name": "Ocean Science Today", "source_type": "institutional",
        "domain": "oceansciencetoday.example.com",
        "url": "https://oceansciencetoday.example.com/blog/2025/10/gammacam-pro-field-test-subsea-imaging",
        "published_date": "2025-10-02",
        "title": "GammaCam Pro: Field Test Results from Deep-Sea Expedition",
        "snippet": "High-authority third-party field test during scientific research expedition demonstrating 4K imaging capability.",
        "platform": "web"
    },
    {
        "brand": "BrandBeta Pro", "brand_id": "brandbeta",
        "product": "MiniReel APX",
        "source_name": "Pro Tools Review", "source_type": "independent_review",
        "domain": "protoolsreview.example.com",
        "url": "https://protoolsreview.example.com/brandbeta-minireel-apx-smartsense/",
        "published_date": "2025-03-01",
        "title": "BrandBeta MiniReel APX with SmartSense",
        "snippet": "Independent specs and performance overview; authoritative third-party evaluation with field results.",
        "platform": "web"
    },
    {
        "brand": "BrandBeta Pro", "brand_id": "brandbeta",
        "product": "Compact M40 DSL",
        "source_name": "Industry Trade Monthly", "source_type": "trade_publication",
        "domain": "industrytrademag.example.com",
        "url": "https://industrytrademag.example.com/brandbeta-compact-m40-c40-dsl-digital-self-leveling/",
        "published_date": "2025-08-19",
        "title": "BrandBeta Compact M40 and C40 DSL Digital Self-Leveling",
        "snippet": "Trade publication covering new DSL product line; emphasis on reduced maintenance and improved uptime.",
        "platform": "web"
    },
    {
        "brand": "BrandGamma Systems", "brand_id": "brandgamma",
        "product": "GammaCam Pro",
        "source_name": "Marine Technology Review", "source_type": "news_article",
        "domain": "marinetechreview.example.com",
        "url": "https://marinetechreview.example.com/articles/2025/10/research-vessel-deploys-4k-imaging-system",
        "published_date": "2025-10-17",
        "title": "Research Vessel Deploys Advanced 4K Imaging System for Deep-Sea Survey",
        "snippet": "Regional marine technology coverage of GammaCam Pro deployment with research institution partnership.",
        "platform": "web"
    },
    {
        "brand": "BrandDelta Locators", "brand_id": "branddelta",
        "product": "SR-24",
        "source_name": "Field Equipment Review", "source_type": "independent_review",
        "domain": "fieldequipmentreview.example.com",
        "url": "https://fieldequipmentreview.example.com/branddelta-sr-24-review",
        "published_date": "2025-05-01",
        "title": "BrandDelta SR-24 Advanced Locator Review",
        "snippet": "Third-party review positioning SR-24 as a professional-grade utility locator with multi-frequency capability.",
        "platform": "web"
    },
]


def generate_id(url, brand_id):
    raw = f"{url.strip().lower()}|{brand_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def main():
    print("=== Seeding mention_log.csv with example data ===")

    fieldnames = [
        "mention_id", "scan_date", "brand_id", "brand_name", "product",
        "source_name", "source_type", "domain", "url", "title",
        "snippet", "published_date", "platform",
        "is_first_party", "is_partner_or_reseller",
        "discovery_source", "signal_score", "sentiment"
    ]

    rows = []
    for entry in SEED_DATA:
        mention = {
            "mention_id": generate_id(entry["url"], entry["brand_id"]),
            "scan_date": "2025-12-01T00:00:00Z",
            "brand_id": entry["brand_id"],
            "brand_name": entry["brand"],
            "product": entry["product"],
            "source_name": entry["source_name"],
            "source_type": entry["source_type"],
            "domain": entry["domain"],
            "url": entry["url"],
            "title": entry["title"],
            "snippet": entry["snippet"],
            "published_date": entry["published_date"],
            "platform": entry["platform"],
            "is_first_party": "False",
            "is_partner_or_reseller": "True" if entry["source_type"] == "reseller_listing" else "False",
            "discovery_source": "manual_seed",
        }

        # Score it
        signal_score, sentiment = score_mention(mention)
        mention["signal_score"] = signal_score
        mention["sentiment"] = sentiment
        rows.append(mention)

    # Sort by score descending
    rows.sort(key=lambda x: int(x["signal_score"]), reverse=True)

    output = DATA_DIR / "mention_log.csv"
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Seeded {len(rows)} mentions to {output}")
    for r in rows[:5]:
        print(f"  [{r['signal_score']}] {r['brand_name']} - {r['title'][:60]}")
    print(f"  ... and {len(rows) - 5} more")


if __name__ == "__main__":
    main()
