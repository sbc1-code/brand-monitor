"""
Brand Mention Scanner
Searches configured sources for brand mentions across a multi-brand portfolio.
Outputs raw_mentions.csv with all discovered mentions.

Sources (no API keys needed):
  - Google News RSS
  - Reddit JSON API
  - Known source RSS feeds

Future sources (require API keys set as CI/CD variables):
  - Google Custom Search API
  - YouTube Data API v3
  - Google Analytics 4
"""

import csv
import json
import os
import sys
import time
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# Paths
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"

# Load configs
with open(CONFIG_DIR / "brands.json") as f:
    BRANDS_CONFIG = json.load(f)

with open(CONFIG_DIR / "sources.json") as f:
    SOURCES_CONFIG = json.load(f)

HEADERS = {
    "User-Agent": "BrandMonitor/1.0 (internal brand tracking)"
}

CSV_FIELDS = [
    "mention_id", "scan_date", "brand_id", "brand_name", "product",
    "source_name", "source_type", "domain", "url", "title",
    "snippet", "published_date", "platform",
    "is_first_party", "is_partner_or_reseller",
    "discovery_source"
]


def generate_mention_id(url, brand_id):
    """Create a stable ID from URL + brand to deduplicate."""
    raw = f"{url.strip().lower()}|{brand_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def parse_date_safe(date_str):
    """Try to parse a date string, return ISO format or empty string."""
    if not date_str:
        return ""
    try:
        dt = date_parser.parse(date_str, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return ""


def extract_domain(url):
    """Extract domain from URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def is_excluded(url, brand):
    """Check if URL matches brand's exclude patterns."""
    domain = extract_domain(url)
    for pattern in brand.get("exclude_patterns", []):
        if pattern.lower() in domain:
            return True
    return False


def verify_brand_mention(title, snippet, brand):
    """Verify that the brand keyword actually appears in the result text.
    Reddit and other search engines return loose matches -- this filters out
    results where the brand name doesn't actually appear."""
    text = f"{title} {snippet}".lower()

    # Primary check: does the brand's core name appear?
    # These are the distinctive terms that definitively indicate a brand mention.
    core_brand_terms = {
        "brandaplha": ["brandalpha"],
        "brandbeta": ["brandbeta"],
        "brandgamma": ["brandgamma systems", "brandgamma power", "bgsl", "gammacam pro", "brandgamma light"],
        "branddelta": ["branddelta"],
        "brandepsilon": ["brandepsilon"],
        "brandzeta": ["brandzeta live", "brandzeta"],
    }

    terms = core_brand_terms.get(brand["id"], [brand["id"]])
    for term in terms:
        if term in text:
            return True

    return False


def classify_source_type(domain, title="", snippet=""):
    """Classify the content type based on domain and text signals."""
    domain = domain.lower()
    text = f"{title} {snippet}".lower()

    # Known classifications
    if any(d in domain for d in ["reddit.com"]):
        return "forum_discussion"
    if any(d in domain for d in ["youtube.com", "youtu.be"]):
        return "video_review"
    if any(d in domain for d in ["play.google.com", "apps.apple.com"]):
        return "app_store_review"
    if any(d in domain for d in ["homedepot.com", "lowes.com", "amazon.com"]):
        return "retail_review"
    if any(d in domain for d in ["resellerdepot.example.com", "toolsupply.example.com"]):
        return "reseller_listing"
    if any(d in domain for d in ["research-institute.example.org", "marine-science.example.org"]):
        return "institutional"
    if any(d in domain for d in ["industrytrademag.example.com", "facilitiesmag.example.com", "hvacjournal.example.com"]):
        return "trade_publication"

    # Text signals
    if any(w in text for w in ["case study", "case-study"]):
        return "case_study"
    if any(w in text for w in ["review", "tested", "hands-on"]):
        return "independent_review"
    if any(w in text for w in ["news", "announces", "launch", "introduces"]):
        return "news_article"

    return "blog_post"


def classify_product(title, snippet, brand_id):
    """Try to identify the specific product mentioned."""
    text = f"{title} {snippet}".lower()
    products = {
        "brandbeta": [
            ("MiniReel APX", ["minireel apx"]),
            ("MiniReel Essentials", ["minireel essentials"]),
            ("MiniReel", ["minireel"]),
            ("MicroDrain APX", ["microdrain"]),
            ("Mini Pro", ["mini pro"]),
            ("Compact M40 DSL", ["m40 dsl", "compact m40"]),
            ("Compact C40 DSL", ["c40 dsl", "compact c40"]),
            ("BrandBeta (general)", []),
        ],
        "brandgamma": [
            ("GammaCam Pro", ["gammacam pro", "gammacam"]),
            ("BrandGamma (general)", []),
        ],
        "branddelta": [
            ("SR-24", ["sr-24", "sr24"]),
            ("SR-20", ["sr-20", "sr20"]),
            ("BrandDelta (general)", []),
        ],
        "brandepsilon": [
            ("Scout", ["epsilon scout", "scout locator"]),
            ("BrandEpsilon (general)", []),
        ],
        "brandzeta": [
            ("BrandZeta Live", []),
        ],
        "brandaplha": [
            ("BrandAlpha (general)", []),
        ],
    }

    for product_name, patterns in products.get(brand_id, []):
        if not patterns:  # fallback / general
            return product_name
        for pattern in patterns:
            if pattern in text:
                return product_name

    return ""


def extract_cse_published_date(item):
    """Try to extract a published date from Google CSE metadata."""
    pagemap = item.get("pagemap", {}) or {}

    meta_date_fields = [
        "article:published_time",
        "article:modified_time",
        "og:updated_time",
        "date",
        "publishdate",
        "pubdate",
        "dc.date",
        "dc.date.issued",
        "sailthru.date",
        "parsely-pub-date",
    ]

    for metatag in pagemap.get("metatags", []):
        for field in meta_date_fields:
            parsed = parse_date_safe(metatag.get(field, ""))
            if parsed:
                return parsed

    for block_name in ["newsarticle", "article", "webpage"]:
        for block in pagemap.get(block_name, []):
            for field in ["datepublished", "datecreated", "datemodified"]:
                parsed = parse_date_safe(block.get(field, ""))
                if parsed:
                    return parsed

    return ""


# ---------- SCANNERS ----------

def scan_google_news_rss(brand):
    """Search Google News RSS for brand mentions."""
    mentions = []
    source_config = SOURCES_CONFIG["sources"].get("google_news_rss", {})
    if not source_config.get("enabled"):
        return mentions

    rate_limit = source_config.get("rate_limit_seconds", 3)

    for keyword in brand["keywords"]:
        query = quote_plus(keyword)
        url = source_config["base_url"].format(query=query)

        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:BRANDS_CONFIG["scan_settings"]["max_results_per_keyword"]]:
                link = entry.get("link", "")
                if not link or is_excluded(link, brand):
                    continue

                domain = extract_domain(link)
                title = entry.get("title", "")
                snippet = BeautifulSoup(
                    entry.get("summary", ""), "html.parser"
                ).get_text()[:500]
                pub_date = parse_date_safe(entry.get("published", ""))

                # Verify brand actually appears in the text
                if not verify_brand_mention(title, snippet, brand):
                    continue

                mentions.append({
                    "mention_id": generate_mention_id(link, brand["id"]),
                    "scan_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "brand_id": brand["id"],
                    "brand_name": brand["name"],
                    "product": classify_product(title, snippet, brand["id"]),
                    "source_name": domain,
                    "source_type": classify_source_type(domain, title, snippet),
                    "domain": domain,
                    "url": link,
                    "title": title,
                    "snippet": snippet,
                    "published_date": pub_date,
                    "platform": "web",
                    "is_first_party": "False",
                    "is_partner_or_reseller": "False",
                    "discovery_source": "google_news_rss",
                })

            time.sleep(rate_limit)

        except Exception as e:
            print(f"  [WARN] Google News RSS error for '{keyword}': {e}", file=sys.stderr)
            time.sleep(rate_limit)

    return mentions


def scan_reddit(brand):
    """Search Reddit for brand mentions."""
    mentions = []
    source_config = SOURCES_CONFIG["sources"].get("reddit", {})
    if not source_config.get("enabled"):
        return mentions

    rate_limit = source_config.get("rate_limit_seconds", 5)
    session = requests.Session()
    session.headers.update({
        "User-Agent": source_config.get("user_agent", HEADERS["User-Agent"])
    })

    for keyword in brand["keywords"]:
        # Use simpler query for Reddit (strip quotes for better results)
        clean_query = keyword.strip('"')
        url = source_config["base_url"].format(query=quote_plus(clean_query))

        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for post in data.get("data", {}).get("children", []):
                post_data = post.get("data", {})
                link = f"https://www.reddit.com{post_data.get('permalink', '')}"
                title = post_data.get("title", "")
                snippet = post_data.get("selftext", "")[:500]
                subreddit = post_data.get("subreddit", "")

                # Verify brand actually appears in the text
                if not verify_brand_mention(title, snippet, brand):
                    continue

                created_utc = post_data.get("created_utc")
                pub_date = ""
                if created_utc:
                    pub_date = datetime.fromtimestamp(
                        created_utc, tz=timezone.utc
                    ).strftime("%Y-%m-%d")

                mentions.append({
                    "mention_id": generate_mention_id(link, brand["id"]),
                    "scan_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "brand_id": brand["id"],
                    "brand_name": brand["name"],
                    "product": classify_product(title, snippet, brand["id"]),
                    "source_name": f"Reddit r/{subreddit}",
                    "source_type": "forum_discussion",
                    "domain": "reddit.com",
                    "url": link,
                    "title": title,
                    "snippet": snippet,
                    "published_date": pub_date,
                    "platform": "reddit",
                    "is_first_party": "False",
                    "is_partner_or_reseller": "False",
                    "discovery_source": "reddit_json",
                })

            time.sleep(rate_limit)

        except Exception as e:
            print(f"  [WARN] Reddit error for '{keyword}': {e}", file=sys.stderr)
            time.sleep(rate_limit)

    return mentions


def scan_known_rss_feeds(brand):
    """Check known trade publication RSS feeds for brand mentions."""
    mentions = []
    clean_keywords = [k.strip('"').lower() for k in brand["keywords"]]

    for source in SOURCES_CONFIG.get("known_sources", []):
        if not source.get("check_rss") or not source.get("rss"):
            continue

        try:
            feed = feedparser.parse(source["rss"])
            for entry in feed.entries[:50]:
                title = entry.get("title", "")
                summary = BeautifulSoup(
                    entry.get("summary", ""), "html.parser"
                ).get_text()
                text = f"{title} {summary}".lower()

                # Check if any brand keyword appears
                if not any(kw in text for kw in clean_keywords):
                    continue

                link = entry.get("link", "")
                if not link or is_excluded(link, brand):
                    continue

                domain = extract_domain(link)
                pub_date = parse_date_safe(entry.get("published", ""))
                snippet = summary[:500]

                mentions.append({
                    "mention_id": generate_mention_id(link, brand["id"]),
                    "scan_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "brand_id": brand["id"],
                    "brand_name": brand["name"],
                    "product": classify_product(title, snippet, brand["id"]),
                    "source_name": source["name"],
                    "source_type": classify_source_type(domain, title, snippet),
                    "domain": domain,
                    "url": link,
                    "title": title,
                    "snippet": snippet,
                    "published_date": pub_date,
                    "platform": "web",
                    "is_first_party": "False",
                    "is_partner_or_reseller": "False",
                    "discovery_source": "known_rss",
                })

        except Exception as e:
            print(f"  [WARN] RSS error for {source['name']}: {e}", file=sys.stderr)

    return mentions


# ---------- FUTURE API SCANNERS (stubs) ----------

def scan_google_cse(brand):
    """Google Custom Search API scanner (requires GOOGLE_CSE_KEY and GOOGLE_CSE_CX)."""
    mentions = []
    source_config = SOURCES_CONFIG["sources"].get("google_custom_search", {})
    if not source_config.get("enabled"):
        return mentions

    api_key = os.environ.get(source_config.get("api_key_env", "GOOGLE_CSE_KEY"))
    cx = os.environ.get(source_config.get("cx_env", "GOOGLE_CSE_CX"))
    if not api_key or not cx:
        print("  [INFO] Google CSE not configured (set GOOGLE_CSE_KEY and GOOGLE_CSE_CX)", file=sys.stderr)
        return mentions

    base_url = source_config.get("base_url", "https://www.googleapis.com/customsearch/v1")
    rate_limit = source_config.get("rate_limit_seconds", 2)
    max_results = BRANDS_CONFIG["scan_settings"].get("max_results_per_keyword", 20)
    lookback_days = BRANDS_CONFIG["scan_settings"].get("lookback_days", 0)

    session = requests.Session()
    session.headers.update({
        "User-Agent": source_config.get("user_agent", HEADERS["User-Agent"])
    })

    for keyword in brand["keywords"]:
        fetched = 0
        start_index = 1

        while fetched < max_results and start_index <= 91:
            page_size = min(10, max_results - fetched)
            params = {
                "key": api_key,
                "cx": cx,
                "q": keyword,
                "num": page_size,
                "start": start_index,
            }
            if lookback_days:
                params["dateRestrict"] = f"d{lookback_days}"

            try:
                resp = session.get(base_url, params=params, timeout=20)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as e:
                print(f"  [WARN] Google CSE error for '{keyword}': {e}", file=sys.stderr)
                time.sleep(rate_limit)
                break

            items = payload.get("items", [])
            if not items:
                break

            for item in items:
                link = item.get("link", "")
                if not link or is_excluded(link, brand):
                    continue

                title = item.get("title", "")
                snippet = (item.get("snippet", "") or "")[:500]

                # Search APIs can still return loose matches across query terms.
                if not verify_brand_mention(title, snippet, brand):
                    continue

                domain = extract_domain(link)
                pub_date = extract_cse_published_date(item)

                mentions.append({
                    "mention_id": generate_mention_id(link, brand["id"]),
                    "scan_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "brand_id": brand["id"],
                    "brand_name": brand["name"],
                    "product": classify_product(title, snippet, brand["id"]),
                    "source_name": domain,
                    "source_type": classify_source_type(domain, title, snippet),
                    "domain": domain,
                    "url": link,
                    "title": title,
                    "snippet": snippet,
                    "published_date": pub_date,
                    "platform": "web",
                    "is_first_party": "False",
                    "is_partner_or_reseller": "False",
                    "discovery_source": "google_custom_search",
                })

            fetched += len(items)

            next_pages = payload.get("queries", {}).get("nextPage", [])
            if not next_pages:
                break

            start_index = next_pages[0].get("startIndex", start_index + len(items))
            time.sleep(rate_limit)

        time.sleep(rate_limit)

    return mentions


def scan_youtube_api(brand):
    """YouTube Data API v3 scanner (requires YOUTUBE_API_KEY)."""
    if not SOURCES_CONFIG["sources"].get("youtube_rss", {}).get("enabled"):
        return []
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("  [INFO] YouTube API not configured (set YOUTUBE_API_KEY)", file=sys.stderr)
        return []
    # TODO: Implement when API key is configured
    return []


# ---------- MAIN ----------

def main():
    all_mentions = []
    scan_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"=== Brand Monitor Scan: {scan_time} ===")
    print(f"Brands: {len(BRANDS_CONFIG['brands'])}")
    print()

    for brand in BRANDS_CONFIG["brands"]:
        print(f"Scanning: {brand['name']} ({len(brand['keywords'])} keywords)...")

        # Active scanners
        news = scan_google_news_rss(brand)
        print(f"  Google News RSS: {len(news)} results")
        all_mentions.extend(news)

        reddit = scan_reddit(brand)
        print(f"  Reddit: {len(reddit)} results")
        all_mentions.extend(reddit)

        rss = scan_known_rss_feeds(brand)
        print(f"  Known RSS: {len(rss)} results")
        all_mentions.extend(rss)

        # Future scanners (stubs + gated API integrations)
        cse = scan_google_cse(brand)
        print(f"  Google CSE: {len(cse)} results")
        all_mentions.extend(cse)

        youtube = scan_youtube_api(brand)
        print(f"  YouTube API: {len(youtube)} results")
        all_mentions.extend(youtube)

        print()

    # Deduplicate by mention_id (same URL + brand)
    seen = set()
    unique = []
    for m in all_mentions:
        if m["mention_id"] not in seen:
            seen.add(m["mention_id"])
            unique.append(m)

    print(f"Total raw mentions: {len(all_mentions)}")
    print(f"After dedup: {len(unique)}")

    # Write raw mentions
    output_file = DATA_DIR / "raw_mentions.csv"
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(unique)

    print(f"Wrote: {output_file}")
    return len(unique)


if __name__ == "__main__":
    count = main()
    sys.exit(0 if count >= 0 else 1)
