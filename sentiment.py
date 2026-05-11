"""
sentiment.py
Performs multi-technique sentiment analysis on collected items.

Techniques used:
  1. VADER         — rule-based, fast, great for social media
  2. Topic tagging — lightweight keyword-based topic labeling
  3. FinBERT       — transformer model (optional, GPU helps)

Outputs a list of enriched records with sentiment scores.
"""

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

import nltk
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

import config

log = logging.getLogger(__name__)

# Download required NLTK data quietly
for resource in ["punkt", "stopwords", "wordnet"]:
    try:
        nltk.download(resource, quiet=True)
    except Exception:
        pass

# ── VADER ─────────────────────────────────────────────────────────────────────

vader = SentimentIntensityAnalyzer()


def vader_score(text: str) -> dict:
    """Return VADER compound + label for a piece of text."""
    if not text or len(text.strip()) < 5:
        return {"compound": 0.0, "label": "neutral", "pos": 0.0, "neg": 0.0, "neu": 1.0}

    scores = vader.polarity_scores(text[:3000])  # VADER works best on shorter text
    compound = scores["compound"]

    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"

    return {
        "compound": round(compound, 4),
        "label":    label,
        "pos":      round(scores["pos"], 4),
        "neg":      round(scores["neg"], 4),
        "neu":      round(scores["neu"], 4),
    }


# ── FinBERT (optional) ────────────────────────────────────────────────────────

_finbert_pipe = None


def _load_finbert():
    global _finbert_pipe
    if _finbert_pipe is None:
        try:
            from transformers import pipeline
            log.info("Loading FinBERT model (first run may take ~2 min)...")
            _finbert_pipe = pipeline(
                "text-classification",
                model="ProsusAI/finbert",
                top_k=None,
                truncation=True,
                max_length=512,
            )
            log.info("FinBERT loaded.")
        except Exception as e:
            log.warning(f"FinBERT unavailable: {e}. Falling back to VADER.")
            _finbert_pipe = None
    return _finbert_pipe


def finbert_score(text: str) -> Optional[dict]:
    """Run FinBERT classification. Returns None if model unavailable."""
    pipe = _load_finbert()
    if not pipe or not text:
        return None
    try:
        result = pipe(text[:512])[0]
        scores = {r["label"].lower(): round(r["score"], 4) for r in result}
        top = max(result, key=lambda x: x["score"])
        return {
            "label":   top["label"].lower(),
            "pos":     scores.get("positive", 0.0),
            "neg":     scores.get("negative", 0.0),
            "neu":     scores.get("neutral",  0.0),
        }
    except Exception as e:
        log.warning(f"FinBERT inference failed: {e}")
        return None


# ── Topic tagging ─────────────────────────────────────────────────────────────

TOPIC_PATTERNS = {
    "eu_ai_act":        r"\b(eu ai act|european ai act|eur.?lex|article 6|high.?risk ai)\b",
    "us_legislation":   r"\b(congress|senate|house bill|executive order|ftc|nist|nsf|dol|doj)\b",
    "criminal_justice": r"\b(criminal justice|recidivism|predictive policing|sentencing|pretrial)\b",
    "liability":        r"\b(liabilit|tort|negligence|product liabilit|strict liabilit|damage)\b",
    "bias_fairness":    r"\b(bias|fairness|discrimination|disparate impact|equity|algorithmic fairness)\b",
    "privacy":          r"\b(privacy|gdpr|ccpa|data protection|facial recognition|surveillance)\b",
    "healthcare":       r"\b(health|medical|clinical|fda|drug approval|diagnosis|patient)\b",
    "copyright_ip":     r"\b(copyright|intellectual property|patent|generative ai|training data)\b",
    "autonomous_vehicles": r"\b(autonomous vehicle|self.?driving|driverless|lidar)\b",
    "labor":            r"\b(labor|employment|automation|job displacement|worker|gig economy)\b",
    "transparency":     r"\b(transparency|explainab|interpretab|black.?box|audit|accountability)\b",
    "national_security":r"\b(national security|military|defense|dod|pentagon|cyber|weapon)\b",
}


def tag_topics(text: str) -> list[str]:
    """Return list of matched topic tags for a piece of text."""
    text_lower = text.lower()
    return [
        topic for topic, pattern in TOPIC_PATTERNS.items()
        if re.search(pattern, text_lower)
    ]


# ── Stance detection (coarse) ─────────────────────────────────────────────────

SUPPORTIVE_TERMS = [
    "should regulate", "need regulation", "must regulate",
    "stronger oversight", "accountability", "ban", "prohibit",
    "safeguards needed", "stricter", "enforce",
]
SKEPTICAL_TERMS = [
    "overregulate", "innovation stifling", "too restrictive",
    "government overreach", "free market", "deregulate",
    "unnecessary regulation", "burden on business", "kill innovation",
]


def detect_stance(text: str) -> str:
    """
    Coarse regulatory stance:
      'pro-regulation' | 'anti-regulation' | 'neutral/mixed'
    """
    text_lower = text.lower()
    pro   = sum(1 for t in SUPPORTIVE_TERMS if t in text_lower)
    anti  = sum(1 for t in SKEPTICAL_TERMS  if t in text_lower)

    if pro > anti:
        return "pro-regulation"
    elif anti > pro:
        return "anti-regulation"
    return "neutral/mixed"


# ── Main analysis pipeline ────────────────────────────────────────────────────

def analyze(items: list[dict], use_finbert: bool = False) -> list[dict]:
    """
    Enrich each collected item with sentiment scores, topics, and stance.
    Returns the enriched list.
    """
    log.info(f"Analyzing {len(items)} items...")

    enriched = []
    for i, item in enumerate(items):
        full_text = f"{item.get('title', '')} {item.get('text', '')}"

        # VADER (always)
        v = vader_score(full_text)
        item["vader_compound"]  = v["compound"]
        item["vader_label"]     = v["label"]
        item["vader_pos"]       = v["pos"]
        item["vader_neg"]       = v["neg"]
        item["vader_neu"]       = v["neu"]

        # FinBERT (optional)
        if use_finbert or config.SENTIMENT_MODEL == "finbert":
            fb = finbert_score(full_text)
            if fb:
                item["finbert_label"] = fb["label"]
                item["finbert_pos"]   = fb["pos"]
                item["finbert_neg"]   = fb["neg"]
                item["finbert_neu"]   = fb["neu"]

        # Topics
        item["topics"]  = tag_topics(full_text)
        item["stance"]  = detect_stance(full_text)

        enriched.append(item)

        if (i + 1) % 50 == 0:
            log.info(f"  Analyzed {i+1}/{len(items)}")

    log.info("Analysis complete.")
    return enriched


def save_analyzed(items: list[dict], output_dir: Optional[str] = None) -> Path:
    """Save enriched records to processed JSON and CSV."""
    out_dir = Path(output_dir or config.OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()

    json_path = out_dir / f"{today}_analyzed.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    csv_path = out_dir / f"{today}_analyzed.csv"
    df = pd.DataFrame(items)
    df.to_csv(csv_path, index=False)

    log.info(f"Saved analyzed data → {json_path}")
    log.info(f"Saved analyzed data → {csv_path}")
    return json_path


def load_history(processed_dir: Optional[str] = None) -> pd.DataFrame:
    """Load all historical analyzed CSVs into one DataFrame."""
    p = Path(processed_dir or config.OUTPUT_DIR)
    csvs = sorted(p.glob("*_analyzed.csv"))
    if not csvs:
        return pd.DataFrame()
    dfs = [pd.read_csv(c) for c in csvs]
    return pd.concat(dfs, ignore_index=True)


if __name__ == "__main__":
    # Quick smoke test
    samples = [
        {"id": "1", "source": "Test", "type": "news",
         "title": "EU AI Act could stifle innovation, critics warn",
         "text": "Industry groups say the sweeping regulation imposes too many burdens."},
        {"id": "2", "source": "Test", "type": "academic",
         "title": "Algorithmic accountability in criminal sentencing must be strengthened",
         "text": "Researchers call for stricter oversight of AI tools used by courts."},
    ]
    results = analyze(samples)
    for r in results:
        print(f"\n{r['title'][:60]}")
        print(f"  VADER: {r['vader_label']} ({r['vader_compound']:.3f})")
        print(f"  Topics: {r['topics']}")
        print(f"  Stance: {r['stance']}")
