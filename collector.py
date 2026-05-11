"""
collector.py
Pulls articles, posts, and papers from all configured sources.
Saves raw JSON to data/raw/YYYY-MM-DD.json
"""

import json
import logging
import os
import time
import re
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import feedparser
import requests

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _slug(text: str) -> str:
    """Stable short ID for deduplication."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _contains_keyword(text: str) -> bool:
    """Return True if text contains at least one project keyword."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in config.KEYWORDS)


# ── RSS / News ────────────────────────────────────────────────────────────────

def fetch_rss() -> list[dict]:
    """Fetch and filter articles from all RSS feeds."""
    items = []
    for source_name, url in config.RSS_FEEDS.items():
        log.info(f"RSS: {source_name}")
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title   = getattr(entry, "title", "") or ""
                summary = getattr(entry, "summary", "") or ""
                link    = getattr(entry, "link", "")
                pub     = getattr(entry, "published", datetime.utcnow().isoformat())

                combined = f"{title} {summary}"
                if not _contains_keyword(combined):
                    continue

                items.append({
                    "id":      _slug(link or title),
                    "source":  source_name,
                    "type":    "news",
                    "title":   title.strip(),
                    "text":    summary.strip(),
                    "url":     link,
                    "date":    pub,
                    "fetched": datetime.utcnow().isoformat(),
                })
            time.sleep(0.5)
        except Exception as e:
            log.warning(f"RSS fetch failed for {source_name}: {e}")

    log.info(f"RSS: collected {len(items)} relevant articles")
    return items


# ── arXiv ─────────────────────────────────────────────────────────────────────

def fetch_arxiv() -> list[dict]:
    """Query arXiv API for recent papers on AI law topics."""
    items = []
    base_url = "http://export.arxiv.org/api/query"

    for term in config.ARXIV_SEARCH_TERMS:
        query = quote(f'all:"{term}"')
        params = f"?search_query={query}&max_results={config.ARXIV_MAX_RESULTS}&sortBy=submittedDate&sortOrder=descending"
        url = base_url + params

        log.info(f"arXiv: querying '{term}'")
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title   = getattr(entry, "title", "").replace("\n", " ").strip()
                summary = getattr(entry, "summary", "").replace("\n", " ").strip()
                link    = getattr(entry, "link", "")
                pub     = getattr(entry, "published", "")

                items.append({
                    "id":      _slug(link),
                    "source":  "arXiv",
                    "type":    "academic",
                    "title":   title,
                    "text":    summary,
                    "url":     link,
                    "date":    pub,
                    "fetched": datetime.utcnow().isoformat(),
                })
            time.sleep(1)
        except Exception as e:
            log.warning(f"arXiv fetch failed for '{term}': {e}")

    log.info(f"arXiv: collected {len(items)} papers")
    return items


# ── Reddit ────────────────────────────────────────────────────────────────────

def fetch_reddit() -> list[dict]:
    """Fetch relevant posts and top comments from Reddit."""
    if not PRAW_AVAILABLE:
        log.warning("praw not installed — skipping Reddit")
        return []

    if config.REDDIT_CLIENT_ID == "YOUR_CLIENT_ID":
        log.warning("Reddit credentials not set — skipping Reddit. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET env vars.")
        return []

    items = []
    try:
        reddit = praw.Reddit(
            client_id=config.REDDIT_CLIENT_ID,
            client_secret=config.REDDIT_CLIENT_SECRET,
            user_agent=config.REDDIT_USER_AGENT,
        )

        for subreddit_name in config.REDDIT_SUBREDDITS:
            subreddit = reddit.subreddit(subreddit_name)
            for term in config.REDDIT_SEARCH_TERMS:
                try:
                    for post in subreddit.search(term, limit=config.REDDIT_POST_LIMIT, time_filter="week"):
                        combined = f"{post.title} {post.selftext}"
                        if not _contains_keyword(combined):
                            continue

                        items.append({
                            "id":      _slug(post.id),
                            "source":  f"Reddit/r/{subreddit_name}",
                            "type":    "social",
                            "title":   post.title,
                            "text":    post.selftext[:2000] if post.selftext else post.title,
                            "url":     f"https://reddit.com{post.permalink}",
                            "date":    datetime.utcfromtimestamp(post.created_utc).isoformat(),
                            "fetched": datetime.utcnow().isoformat(),
                            "score":   post.score,
                            "comments": post.num_comments,
                        })
                except Exception as e:
                    log.warning(f"Reddit search failed r/{subreddit_name} '{term}': {e}")
                time.sleep(0.5)

    except Exception as e:
        log.warning(f"Reddit init failed: {e}")

    log.info(f"Reddit: collected {len(items)} posts")
    return items


# ── Regulations.gov ───────────────────────────────────────────────────────────

def fetch_regulations_gov() -> list[dict]:
    """
    Query Regulations.gov API for AI-related dockets and comments.
    Free API key available at https://open.fda.gov/apis/
    Set env var: REGULATIONS_API_KEY
    """
    api_key = os.getenv("REGULATIONS_API_KEY", "DEMO_KEY")
    items   = []
    base    = "https://api.regulations.gov/v4/documents"
    headers = {"X-Api-Key": api_key}

    for term in ["artificial intelligence", "AI regulation", "machine learning"]:
        params = {
            "filter[searchTerm]": term,
            "filter[postedDate][ge]": (date.today() - timedelta(days=30)).isoformat(),
            "page[size]": 20,
            "sort": "-postedDate",
        }
        log.info(f"Regulations.gov: querying '{term}'")
        try:
            resp = requests.get(base, headers=headers, params=params, timeout=15)
            if resp.status_code == 200:
                for doc in resp.json().get("data", []):
                    attrs = doc.get("attributes", {})
                    title = attrs.get("title", "")
                    items.append({
                        "id":      _slug(doc.get("id", title)),
                        "source":  "Regulations.gov",
                        "type":    "regulatory",
                        "title":   title,
                        "text":    attrs.get("agencyId", "") + ": " + title,
                        "url":     f"https://www.regulations.gov/document/{doc.get('id','')}",
                        "date":    attrs.get("postedDate", ""),
                        "fetched": datetime.utcnow().isoformat(),
                    })
            elif resp.status_code == 429:
                log.warning("Regulations.gov rate limit hit")
            time.sleep(1)
        except Exception as e:
            log.warning(f"Regulations.gov failed for '{term}': {e}")

    log.info(f"Regulations.gov: collected {len(items)} documents")
    return items


# ── Main collector ────────────────────────────────────────────────────────────

def deduplicate(items: list[dict]) -> list[dict]:
    """Remove items with duplicate IDs, keeping the first occurrence."""
    seen = set()
    unique = []
    for item in items:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)
    return unique


def collect_all(output_dir: Optional[str] = None) -> list[dict]:
    """
    Run all collectors, deduplicate, and save to JSON.
    Returns the full list of collected items.
    """
    out_dir = Path(output_dir or config.DATA_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("=== Starting daily collection ===")
    all_items = []
    all_items.extend(fetch_rss())
    all_items.extend(fetch_arxiv())
    all_items.extend(fetch_reddit())
    all_items.extend(fetch_regulations_gov())

    all_items = deduplicate(all_items)
    log.info(f"Total unique items collected: {len(all_items)}")

    out_path = out_dir / f"{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    log.info(f"Saved raw data → {out_path}")

    return all_items


if __name__ == "__main__":
    data = collect_all()
    print(f"\nCollected {len(data)} items.")
    for item in data[:5]:
        print(f"  [{item['type']}] {item['source']}: {item['title'][:80]}")
