"""
config.py
Central configuration for the AI-in-Law Sentiment Analysis project.
Edit this file to add/remove sources, keywords, or credentials.
"""

import os

# Keywords (legacy — kept for reference) 
# The collector now uses a richer AI×Law term matcher defined in collector.py
# (AI_TERMS × LAW_TERMS). This list remains for documentation of intent.
KEYWORDS = [
    "AI regulation", "artificial intelligence law", "AI legislation",
    "AI governance", "algorithmic regulation", "AI liability",
    "AI Act", "EU AI Act", "AI policy", "machine learning regulation",
    "AI ethics law", "autonomous systems law", "AI compliance",
    "AI legal framework", "AI judiciary", "AI criminal justice",
    "AI bias regulation", "AI accountability", "algorithmic transparency",
    "AI enforcement", "generative AI regulation", "LLM regulation",
]

# RSS / News feeds 
# Note on feed health: Reuters retired its public RSS in 2020,
# and POLITICO's `rss.politico.com` was decommissioned. They've been replaced
# with sources that have working feeds as of 2026.
RSS_FEEDS = {
    "Ars Technica Policy":   "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "The Verge AI":          "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "MIT Tech Review":       "https://www.technologyreview.com/feed/",
    "TechCrunch":            "https://techcrunch.com/feed/",
    "Wired AI":              "https://www.wired.com/feed/category/artificial-intelligence/latest/rss",
    "LawFare":               "https://www.lawfaremedia.org/feed",
    "Future of Life":        "https://futureoflife.org/feed/",
    # Replacements for dead feeds:
    "EFF DeepLinks":         "https://www.eff.org/rss/updates.xml",
    "Brookings TechTank":    "https://www.brookings.edu/blog/techtank/feed/",
    "Stanford HAI":          "https://hai.stanford.edu/news/rss.xml",
    "AlgorithmWatch":        "https://algorithmwatch.org/en/feed/",
    "Ars Technica Tech Policy": "https://feeds.arstechnica.com/arstechnica/tech-policy",
}

# arXiv 
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

# Reddit 
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

# Government / Regulatory sources 
GOV_SOURCES = {
    "Regulations.gov RSS": "https://www.regulations.gov/api/rss?docketId=DOCKET-2023-AI",
    "EUR-Lex AI Act":      "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:52021PC0206",
    "NIST AI RMF":         "https://www.nist.gov/artificial-intelligence",
    "FTC AI":              "https://www.ftc.gov/news-events/topics/artificial-intelligence",
}

# Output paths 
DATA_DIR    = "data/raw"
OUTPUT_DIR  = "data/processed"
REPORTS_DIR = "reports"
PLOTS_DIR   = "reports/plots"

# Sentiment model 
# Options: "vader" (fast, no GPU needed) | "finbert" (slower, more accurate)
# "vader" is recommended for GitHub Actions.
SENTIMENT_MODEL = "vader"

# Scheduling 
# Note: this string is informational only. The actual schedule lives in
# .github/workflows/daily.yml. Keep them in sync if you change either.
CRON_SCHEDULE = "0 11 * * *"  # 11:00 UTC daily
