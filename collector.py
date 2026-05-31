"""
collector.py
Pulls articles, posts, and papers from all configured sources.
Saves raw JSON to data/raw/YYYY-MM-DD.json

Only includes items whose PUBLICATION date falls within the configured
look-back window. This ensures the daily report reflects content actually
published in that window, not whatever happens to be in the RSS buffer.
"""

import json
import logging
import os
import time
import re
import hashlib
from datetime import datetime, date, timedelta, timezone
from email.utils import parsedate_to_datetime
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

# Date filter configuration 
# RSS feeds often have publishing delays of several hours, and timezones shift
# what "today" means. A 2-day window catches yesterday-late and today reliably
# without polluting the dataset with old content.
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "2"))


def _slug(text: str) -> str:
    """Stable short ID for deduplication."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


#  Keyword matching 
#
# Previous logic required a full keyword phrase (e.g. "ai regulation") to appear
# verbatim. Real-world headlines almost never phrase things that way — they say
# "EU rules tighten on chatbots" or "Senate panel weighs AI safety bill".
#
# New logic: an item matches if its combined title+summary contains BOTH:
#   - at least one AI/tech term  (ai, algorithm, machine learning, ...)
#   - at least one law/policy term (law, regulat, govern, ...)
# This is a much better proxy for "AI-and-law" content.

AI_TERMS = [
    r"\bai\b",
    r"\bartificial intelligence\b",
    r"\balgorithm",          # algorithm, algorithmic, algorithms
    r"\bmachine learning\b",
    r"\bllm\b",
    r"\bllms\b",
    r"\blarge language model",
    r"\bgenerative ai\b",
    r"\bgenai\b",
    r"\bchatgpt\b",
    r"\bopenai\b",
    r"\banthropic\b",
    r"\bdeepfake",
    r"\bautonomous",
    r"\bneural network",
    r"\bfoundation model",
]

LAW_TERMS = [
    r"\blaw\b", r"\blaws\b", r"\blegal\b", r"\blegisla",   # legislation, legislator, legislative
    r"\bregulat",          # regulate, regulation, regulator, regulatory
    r"\bgovern",           # governance, government, governing
    r"\bpolic",            # policy, polices, policymaker
    r"\bbill\b", r"\bact\b",
    r"\bcourt\b", r"\bcourts\b", r"\bjudic", r"\bjudge\b",
    r"\bcompliance\b", r"\benforce",
    r"\boversight\b",
    r"\bliab",             # liable, liability
    r"\blawsuit\b", r"\blitigation\b",
    r"\bsenat", r"\bcongress", r"\bparliament",
    r"\bftc\b", r"\bnist\b", r"\bdoj\b", r"\bsec\b", r"\beu\b",
    r"\bcopyright\b", r"\bpatent\b", r"\bintellectual property\b",
    r"\bgdpr\b", r"\bccpa\b",
    r"\bethic",           # ethics, ethical
    r"\bsafety\b", r"\baccountabil",
    r"\bantitrust\b", r"\bmonopol",
    r"\bdata protection\b",
]

AI_RE  = re.compile("|".join(AI_TERMS), re.IGNORECASE)
LAW_RE = re.compile("|".join(LAW_TERMS), re.IGNORECASE)


def _is_relevant(text: str) -> bool:
    """An item is relevant if it mentions AI/algorithms AND law/regulation."""
    if not text:
        return False
    return bool(AI_RE.search(text) and LAW_RE.search(text))


def _parse_pub_date(raw) -> Optional[datetime]:
    if not raw:
        return None
    if isinstance(raw, datetime):
        dt = raw
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    s = str(raw).strip()

    try:
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass

    try:
        s_iso = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s_iso)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    try:
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    return None


def _is_within_window(pub_dt: Optional[datetime], today_utc: date) -> bool:
    if pub_dt is None:
        return False
    pub_date = pub_dt.astimezone(timezone.utc).date()
    earliest = today_utc - timedelta(days=LOOKBACK_DAYS)
    return earliest <= pub_date <= today_utc


def _published_struct_to_dt(entry) -> Optional[datetime]:
    for attr in ("published_parsed", "updated_parsed"):
        st = getattr(entry, attr, None)
        if st:
            try:
                return datetime(*st[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            dt = _parse_pub_date(raw)
            if dt:
                return dt
    return None


# RSS / News 
def fetch_rss(today_utc: date) -> list[dict]:
    items = []
    skipped_old = 0
    skipped_undated = 0
    skipped_irrelevant = 0

    for source_name, url in config.RSS_FEEDS.items():
        log.info(f"RSS: {source_name}")
        try:
            feed = feedparser.parse(url)
            if getattr(feed, "bozo", 0) and getattr(feed, "bozo_exception", None):
                log.warning(f"  feed parse issue: {feed.bozo_exception}")

            for entry in feed.entries:
                title = getattr(entry, "title", "") or ""
                summary = getattr(entry, "summary", "") or ""
                link = getattr(entry, "link", "")

                pub_dt = _published_struct_to_dt(entry)
                if pub_dt is None:
                    skipped_undated += 1
                    continue
                if not _is_within_window(pub_dt, today_utc):
                    skipped_old += 1
                    continue

                combined = f"{title} {summary}"
                if not _is_relevant(combined):
                    skipped_irrelevant += 1
                    continue

                items.append({
                    "id": _slug(link or title),
                    "source": source_name,
                    "type": "news",
                    "title": title.strip(),
                    "text": summary.strip(),
                    "url": link,
                    "date": pub_dt.isoformat(),
                    "pub_date": pub_dt.date().isoformat(),
                    "fetched": datetime.now(timezone.utc).isoformat(),
                })
            time.sleep(0.5)
        except Exception as e:
            log.warning(f"RSS fetch failed for {source_name}: {e}")

    log.info(
        f"RSS: kept {len(items)} | skipped {skipped_old} (too old) | "
        f"{skipped_undated} (no date) | {skipped_irrelevant} (off-topic)"
    )
    return items


# arXiv 
def fetch_arxiv(today_utc: date) -> list[dict]:
    items = []
    skipped_old = 0
    skipped_irrelevant = 0
    base_url = "http://export.arxiv.org/api/query"

    for term in config.ARXIV_SEARCH_TERMS:
        query = quote(f'all:"{term}"')
        params = (
            f"?search_query={query}"
            f"&max_results={config.ARXIV_MAX_RESULTS}"
            f"&sortBy=submittedDate&sortOrder=descending"
        )
        url = base_url + params
        log.info(f"arXiv: querying '{term}'")
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = getattr(entry, "title", "").replace("\n", " ").strip()
                summary = getattr(entry, "summary", "").replace("\n", " ").strip()
                link = getattr(entry, "link", "")

                pub_dt = _published_struct_to_dt(entry)
                if pub_dt is None or not _is_within_window(pub_dt, today_utc):
                    skipped_old += 1
                    continue

                # arXiv search already filtered by term, but double-check relevance.
                if not _is_relevant(f"{title} {summary}"):
                    skipped_irrelevant += 1
                    continue

                items.append({
                    "id": _slug(link),
                    "source": "arXiv",
                    "type": "academic",
                    "title": title,
                    "text": summary,
                    "url": link,
                    "date": pub_dt.isoformat(),
                    "pub_date": pub_dt.date().isoformat(),
                    "fetched": datetime.now(timezone.utc).isoformat(),
                })
            time.sleep(1)
        except Exception as e:
            log.warning(f"arXiv fetch failed for '{term}': {e}")

    log.info(f"arXiv: kept {len(items)} | {skipped_old} (too old) | "
             f"{skipped_irrelevant} (off-topic)")
    return items


# Reddit 
def fetch_reddit(today_utc: date) -> list[dict]:
    if not PRAW_AVAILABLE:
        log.warning("praw not installed — skipping Reddit")
        return []
    if not config.REDDIT_CLIENT_ID or config.REDDIT_CLIENT_ID == "YOUR_CLIENT_ID":
        log.info("Reddit credentials not set — skipping Reddit cleanly.")
        return []

    items = []
    skipped_old = 0
    try:
        reddit = praw.Reddit(
            client_id=config.REDDIT_CLIENT_ID,
            client_secret=config.REDDIT_CLIENT_SECRET,
            user_agent=config.REDDIT_USER_AGENT,
        )
        # Quick auth probe — if this fails, skip the whole section instead of
        # spamming 401s across every subreddit/term combination.
        try:
            reddit.user.me()
        except Exception:
            # Script auth (no user) is still valid for read-only search;
            # but if even an anonymous request will fail we'd rather know now.
            pass

        for subreddit_name in config.REDDIT_SUBREDDITS:
            subreddit = reddit.subreddit(subreddit_name)
            for term in config.REDDIT_SEARCH_TERMS:
                try:
                    rt_filter = "day" if LOOKBACK_DAYS == 0 else "week"
                    for post in subreddit.search(
                        term, limit=config.REDDIT_POST_LIMIT, time_filter=rt_filter,
                    ):
                        pub_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                        if not _is_within_window(pub_dt, today_utc):
                            skipped_old += 1
                            continue

                        combined = f"{post.title} {post.selftext}"
                        if not _is_relevant(combined):
                            continue

                        items.append({
                            "id": _slug(post.id),
                            "source": f"Reddit/r/{subreddit_name}",
                            "type": "social",
                            "title": post.title,
                            "text": post.selftext[:2000] if post.selftext else post.title,
                            "url": f"https://reddit.com{post.permalink}",
                            "date": pub_dt.isoformat(),
                            "pub_date": pub_dt.date().isoformat(),
                            "fetched": datetime.now(timezone.utc).isoformat(),
                            "score": post.score,
                            "comments": post.num_comments,
                        })
                except Exception as e:
                    # 401s here mean credentials are wrong — bail fast on the
                    # first failure rather than try every other subreddit too.
                    if "401" in str(e):
                        log.warning(
                            f"Reddit auth failed (401). Check REDDIT_CLIENT_ID/SECRET. "
                            f"Skipping rest of Reddit."
                        )
                        return items
                    log.warning(f"Reddit search failed r/{subreddit_name} '{term}': {e}")
                time.sleep(0.5)
    except Exception as e:
        log.warning(f"Reddit init failed: {e}")

    log.info(f"Reddit: kept {len(items)} | skipped {skipped_old} outside window")
    return items


# Regulations.gov 
def fetch_regulations_gov(today_utc: date) -> list[dict]:
    api_key = os.getenv("REGULATIONS_API_KEY", "DEMO_KEY")
    items = []
    skipped_old = 0
    base = "https://api.regulations.gov/v4/documents"
    headers = {"X-Api-Key": api_key}

    earliest = (today_utc - timedelta(days=LOOKBACK_DAYS)).isoformat()

    for term in ["artificial intelligence", "AI regulation", "machine learning"]:
        params = {
            "filter[searchTerm]": term,
            "filter[postedDate][ge]": earliest,
            "filter[postedDate][le]": today_utc.isoformat(),
            "page[size]": 20,
            "sort": "-postedDate",
        }
        log.info(f"Regulations.gov: querying '{term}' (from {earliest})")
        try:
            resp = requests.get(base, headers=headers, params=params, timeout=15)
            if resp.status_code == 200:
                for doc in resp.json().get("data", []):
                    attrs = doc.get("attributes", {})
                    posted = attrs.get("postedDate", "")
                    pub_dt = _parse_pub_date(posted)
                    if not _is_within_window(pub_dt, today_utc):
                        skipped_old += 1
                        continue

                    title = attrs.get("title", "")
                    items.append({
                        "id": _slug(doc.get("id", title)),
                        "source": "Regulations.gov",
                        "type": "regulatory",
                        "title": title,
                        "text": attrs.get("agencyId", "") + ": " + title,
                        "url": f"https://www.regulations.gov/document/{doc.get('id','')}",
                        "date": pub_dt.isoformat() if pub_dt else "",
                        "pub_date": pub_dt.date().isoformat() if pub_dt else "",
                        "fetched": datetime.now(timezone.utc).isoformat(),
                    })
            elif resp.status_code == 429:
                log.warning("Regulations.gov rate limit hit")
                time.sleep(2)
            elif resp.status_code in (401, 403):
                log.warning(
                    f"Regulations.gov auth failed ({resp.status_code}). "
                    f"Set REGULATIONS_API_KEY env var. Skipping."
                )
                return items
        except Exception as e:
            log.warning(f"Regulations.gov failed for '{term}': {e}")

    log.info(f"Regulations.gov: kept {len(items)} | skipped {skipped_old} outside window")
    return items


# Main collector
def deduplicate(items: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for item in items:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)
    return unique


def collect_all(output_dir: Optional[str] = None) -> list[dict]:
    out_dir = Path(output_dir or config.DATA_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    today_utc = datetime.now(timezone.utc).date()
    log.info(f"=== Starting daily collection for {today_utc.isoformat()} "
             f"(LOOKBACK_DAYS={LOOKBACK_DAYS}) ===")

    all_items = []
    all_items.extend(fetch_rss(today_utc))
    all_items.extend(fetch_arxiv(today_utc))
    all_items.extend(fetch_reddit(today_utc))
    all_items.extend(fetch_regulations_gov(today_utc))
    all_items = deduplicate(all_items)

    log.info(f"Total unique items collected: {len(all_items)}")

    out_path = out_dir / f"{today_utc.isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    log.info(f"Saved raw data → {out_path}")

    return all_items


if __name__ == "__main__":
    data = collect_all()
    print(f"\nCollected {len(data)} items.")
    for item in data[:5]:
        print(f"  [{item['type']}] {item['source']} ({item.get('pub_date','?')}): "
              f"{item['title'][:80]}")
