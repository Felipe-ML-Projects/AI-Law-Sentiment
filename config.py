"""
config.py
Central configuration for the AI-in-Law Sentiment Analysis project.
Edit this file to add/remove sources, keywords, or credentials.
"""

import os

# ── Keywords ─────────────────────────────────────────────────────────────────
KEYWORDS = [
    "AI regulation", "artificial intelligence law", "AI legislation",
    "AI governance", "algorithmic regulation", "AI liability",
    "AI Act", "EU AI Act", "AI policy", "machine learning regulation",
    "AI ethics law", "autonomous systems law", "AI compliance",
    "AI legal framework", "AI judiciary", "AI criminal justice",
    "AI bias regulation", "AI accountability", "algorithmic transparency",
    "AI enforcement", "generative AI regulation", "LLM regulation",
]

# ── RSS / News feeds ──────────────────────────────────────────────────────────
RSS_FEEDS = {
    "Reuters Law": "https://feeds.reuters.com/reuters/technologyNews",
    "Ars Technica Policy": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "The Verge AI": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "MIT Tech Review": "https://www.technologyreview.com/feed/",
    "POLITICO Tech": "https://rss.politico.com/technology.xml",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Wired AI": "https://www.wired.com/feed/category/artificial-intelligence/latest/rss",
    "LawFare": "https://www.lawfaremedia.org/feed",
    "Future of Life": "https://futureoflife.org/feed/",
}

# ── arXiv / SSRN ─────────────────────────────────────────────────────────────
ARXIV_SEARCH_TERMS = [
    "AI regulation", "artificial intelligence law",
    "AI governance", "algorithmic accountability",
    "large language model policy",
]
ARXIV_MAX_RESULTS = 30

SSRN_KEYWORDS = [
    "artificial intelligence regulation",
    "AI governance",
    "algorithmic accountability",
]

# ── Reddit ────────────────────────────────────────────────────────────────────
# Create a Reddit app at https://www.reddit.com/prefs/apps (script type)
# Then set env vars: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "YOUR_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
REDDIT_USER_AGENT    = "ai_law_sentiment_bot/1.0"

REDDIT_SUBREDDITS = [
    "law", "AIPolicy", "MachineLearning", "artificial",
    "ChatGPT", "singularity", "legaladvice", "LegalTech",
    "OpenAI", "privacy",
]
REDDIT_SEARCH_TERMS = [
    "AI regulation", "artificial intelligence law",
    "AI Act", "AI governance", "AI legislation",
]
REDDIT_POST_LIMIT = 50

# ── Government / Regulatory sources ──────────────────────────────────────────
GOV_SOURCES = {
    "Regulations.gov RSS": "https://www.regulations.gov/api/rss?docketId=DOCKET-2023-AI",
    "EUR-Lex AI Act": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:52021PC0206",
    "NIST AI RMF": "https://www.nist.gov/artificial-intelligence",
    "FTC AI": "https://www.ftc.gov/news-events/topics/artificial-intelligence",
}

# ── Output paths ──────────────────────────────────────────────────────────────
DATA_DIR    = "data/raw"
OUTPUT_DIR  = "data/processed"
REPORTS_DIR = "reports"
PLOTS_DIR   = "reports/plots"

# ── Sentiment model ───────────────────────────────────────────────────────────
# Options: "vader" (fast, no GPU needed) | "finbert" (slower, more accurate)
# For NIW project running on GitHub Actions, "vader" is recommended.
SENTIMENT_MODEL = "vader"

# ── Scheduling ────────────────────────────────────────────────────────────────
# These settings are used by the GitHub Actions workflow (see .github/workflows/)
CRON_SCHEDULE = "0 8 * * *"  # 8:00 AM UTC daily
