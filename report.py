"""
report.py
Generates a daily Markdown report + charts from analyzed sentiment data,
and rewrites README.md with a longitudinal "Trends" section.

Output structure:
  reports/
    YYYY-MM-DD_report.md       ← human-readable daily summary
    plots/
      YYYY-MM-DD_sentiment_dist.png
      YYYY-MM-DD_topic_breakdown.png
      YYYY-MM-DD_source_sentiment.png
      YYYY-MM-DD_stance.png
      YYYY-MM-DD_timeline.png
      YYYY-MM-DD_wordcloud.png
      YYYY-MM-DD_topics_over_time.png       ← NEW: longitudinal topic trends
      YYYY-MM-DD_stance_over_time.png       ← NEW: longitudinal stance trends
  README.md                    ← auto-updated project landing page (now includes
                                  a persistent Trends section)
"""

import ast
import json
import logging
import textwrap
from collections import Counter, defaultdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from wordcloud import WordCloud, STOPWORDS

import config

log = logging.getLogger(__name__)

SENTIMENT_COLORS = {
    "positive": "#2E9B6E",
    "neutral":  "#8C8C8C",
    "negative": "#D84F3F",
}
STANCE_COLORS = {
    "pro-regulation":  "#3B7DD8",
    "neutral/mixed":   "#9B9B9B",
    "anti-regulation": "#D88C3B",
}

EXTRA_STOPWORDS = {
    "ai", "artificial", "intelligence", "law", "legal", "use",
    "said", "also", "new", "one", "may", "using", "used",
    "will", "like", "say", "says", "year", "years",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.1f}%" if total else "0%"


def _utcnow() -> datetime:
    """Replacement for the deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc)


def _fig(w=9, h=5):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#DDDDDD")
    ax.tick_params(colors="#444444")
    ax.title.set_color("#222222")
    return fig, ax


def _coerce_topics(value):
    """Always return a list — handles raw-list, stringified-list, or NaN."""
    if isinstance(value, list):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, str):
        try:
            v = ast.literal_eval(value)
            return v if isinstance(v, list) else []
        except (ValueError, SyntaxError):
            return []
    return []


def _ensure_pub_date(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure the dataframe has a `pub_date` column as datetime.date.
    Falls back to `fetched` (run date) only if pub_date is unavailable.
    """
    if df.empty:
        return df
    df = df.copy()
    if "pub_date" in df.columns:
        df["pub_date"] = pd.to_datetime(df["pub_date"], errors="coerce").dt.date
    elif "date" in df.columns:
        df["pub_date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    elif "fetched" in df.columns:
        df["pub_date"] = pd.to_datetime(df["fetched"], errors="coerce").dt.date
    else:
        df["pub_date"] = pd.NaT
    return df


# ── Daily charts ──────────────────────────────────────────────────────────────

def plot_sentiment_distribution(df: pd.DataFrame, plots_dir: Path, today: str):
    counts = df["vader_label"].value_counts()
    labels_order = ["positive", "neutral", "negative"]
    values = [counts.get(l, 0) for l in labels_order]
    colors = [SENTIMENT_COLORS[l] for l in labels_order]

    fig, ax = _fig(7, 5)
    bars = ax.bar(labels_order, values, color=colors, width=0.5,
                  edgecolor="white", linewidth=1.5)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                str(val), ha="center", va="bottom", fontsize=11, color="#222222")
    ax.set_title("Sentiment distribution — today", fontsize=13, pad=12)
    ax.set_ylabel("Number of items")
    ax.set_ylim(0, max(values) * 1.18 if max(values) > 0 else 10)
    plt.tight_layout()
    path = plots_dir / f"{today}_sentiment_dist.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Saved → {path}")
    return path


def plot_topic_breakdown(df: pd.DataFrame, plots_dir: Path, today: str):
    topic_sentiment = defaultdict(Counter)
    for _, row in df.iterrows():
        topics = _coerce_topics(row.get("topics"))
        for topic in topics:
            topic_sentiment[topic][row.get("vader_label", "neutral")] += 1

    if not topic_sentiment:
        return None

    topics_sorted = sorted(
        topic_sentiment.keys(),
        key=lambda t: sum(topic_sentiment[t].values()),
        reverse=True
    )[:12]

    fig, ax = _fig(10, 6)
    y = np.arange(len(topics_sorted))
    width = 0.55

    left = np.zeros(len(topics_sorted))
    for sentiment in ["positive", "neutral", "negative"]:
        vals = [topic_sentiment[t].get(sentiment, 0) for t in topics_sorted]
        ax.barh(y, vals, left=left, color=SENTIMENT_COLORS[sentiment],
                height=width, label=sentiment)
        left += np.array(vals)

    ax.set_yticks(y)
    ax.set_yticklabels([t.replace("_", " ").title() for t in topics_sorted], fontsize=10)
    ax.set_xlabel("Number of items")
    ax.set_title("Top topics — sentiment breakdown", fontsize=13, pad=12)
    ax.legend(loc="lower right", fontsize=9)
    ax.invert_yaxis()
    plt.tight_layout()
    path = plots_dir / f"{today}_topic_breakdown.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Saved → {path}")
    return path


def plot_source_sentiment(df: pd.DataFrame, plots_dir: Path, today: str):
    if "source" not in df.columns or "vader_compound" not in df.columns:
        return None
    avg = (
        df.groupby("source")["vader_compound"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "avg_compound", "count": "n"})
        .query("n >= 2")            # was 3 — relax for small daily samples
        .sort_values("avg_compound")
    )

    if avg.empty:
        return None

    avg = avg.iloc[-10:] if len(avg) > 10 else avg

    fig, ax = _fig(9, 5)
    colors = [SENTIMENT_COLORS["positive"] if v >= 0.05
              else SENTIMENT_COLORS["negative"] if v <= -0.05
              else SENTIMENT_COLORS["neutral"]
              for v in avg["avg_compound"]]

    ax.barh(avg.index, avg["avg_compound"], color=colors, edgecolor="white", linewidth=1)
    ax.axvline(0, color="#AAAAAA", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Average VADER compound score")
    ax.set_title("Average sentiment by source", fontsize=13, pad=12)
    plt.tight_layout()
    path = plots_dir / f"{today}_source_sentiment.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Saved → {path}")
    return path


def plot_stance_breakdown(df: pd.DataFrame, plots_dir: Path, today: str):
    if "stance" not in df.columns:
        return None
    counts = df["stance"].value_counts()
    labels = ["pro-regulation", "neutral/mixed", "anti-regulation"]
    sizes  = [counts.get(l, 0) for l in labels]
    colors = [STANCE_COLORS[l] for l in labels]

    if sum(sizes) == 0:
        return None

    fig, ax = plt.subplots(figsize=(6, 6))
    fig.patch.set_facecolor("white")
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors,
        autopct=lambda p: f"{p:.1f}%" if p > 2 else "",
        startangle=140, pctdistance=0.78,
        wedgeprops={"edgecolor": "white", "linewidth": 2},
    )
    for t in texts:
        t.set_fontsize(10)
    ax.set_title("Regulatory stance distribution", fontsize=13, pad=14)
    plt.tight_layout()
    path = plots_dir / f"{today}_stance.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Saved → {path}")
    return path


def plot_wordcloud(df: pd.DataFrame, plots_dir: Path, today: str):
    rows = df.fillna("")
    text_chunks = []
    for _, row in rows.iterrows():
        text_chunks.append(str(row.get("title", "")))
        text_chunks.append(str(row.get("text", "")))
    all_text = " ".join(text_chunks).strip()

    if not all_text:
        return None

    stopwords = STOPWORDS | EXTRA_STOPWORDS

    wc = WordCloud(
        width=1200, height=500,
        background_color="white",
        stopwords=stopwords,
        colormap="RdYlGn",
        max_words=150,
        prefer_horizontal=0.85,
    ).generate(all_text)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title("Most frequent terms — AI in law discourse", fontsize=13, pad=10)
    plt.tight_layout()
    path = plots_dir / f"{today}_wordcloud.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Saved → {path}")
    return path


# ── Longitudinal / trend charts ───────────────────────────────────────────────

def plot_timeline(history_df: pd.DataFrame, plots_dir: Path, today: str):
    """
    Line chart: daily average sentiment over time, keyed on ARTICLE PUBLICATION
    DATE (not the scraper run time). This matches the report-date convention.
    """
    if history_df.empty:
        return None

    df = _ensure_pub_date(history_df)
    df = df.dropna(subset=["pub_date"])
    if df.empty:
        return None

    daily = (
        df.groupby("pub_date")["vader_compound"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "avg", "count": "n"})
        .reset_index()
        .sort_values("pub_date")
    )

    if len(daily) < 2:
        return None

    # 7-day rolling average to smooth single-day noise
    daily["avg_7d"] = daily["avg"].rolling(window=7, min_periods=2).mean()

    fig, ax = _fig(11, 4.5)
    ax.plot(daily["pub_date"], daily["avg"], color="#9CBBE0", linewidth=1.2,
            marker="o", markersize=3, label="Daily avg.")
    ax.plot(daily["pub_date"], daily["avg_7d"], color="#3B7DD8", linewidth=2.2,
            label="7-day rolling avg.")
    ax.fill_between(daily["pub_date"], daily["avg_7d"], alpha=0.10, color="#3B7DD8")
    ax.axhline(0, color="#AAAAAA", linewidth=0.8, linestyle="--")
    ax.set_ylabel("Avg. VADER compound")
    ax.set_title("Daily sentiment trend — AI-in-law coverage (by publication date)",
                 fontsize=13, pad=12)
    ax.legend(loc="best", fontsize=9)
    plt.xticks(rotation=35, ha="right", fontsize=9)
    plt.tight_layout()
    path = plots_dir / f"{today}_timeline.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Saved → {path}")
    return path


def plot_topics_over_time(history_df: pd.DataFrame, plots_dir: Path, today: str):
    """
    Stacked-area chart of the top regulatory topics over time. This is the
    visualization that shows which regulatory aspects are getting attention
    over successive days/weeks.
    """
    if history_df.empty:
        return None

    df = _ensure_pub_date(history_df)
    df = df.dropna(subset=["pub_date"])
    if df.empty:
        return None

    if "topics" not in df.columns:
        return None
    df = df.copy()
    df["topics"] = df["topics"].apply(_coerce_topics)

    exploded = df.explode("topics")
    exploded = exploded[exploded["topics"].notna() & (exploded["topics"] != "")]
    if exploded.empty:
        return None

    top_topics = exploded["topics"].value_counts().head(6).index.tolist()
    exploded = exploded[exploded["topics"].isin(top_topics)]

    pivot = (
        exploded.groupby(["pub_date", "topics"]).size()
        .unstack(fill_value=0)
        .sort_index()
    )
    if len(pivot) < 2:
        return None

    # Reorder columns to most-frequent first for stable colors
    pivot = pivot[[c for c in top_topics if c in pivot.columns]]

    fig, ax = _fig(11, 5)
    ax.stackplot(
        pivot.index, pivot.T.values,
        labels=[t.replace("_", " ").title() for t in pivot.columns],
        alpha=0.85,
    )
    ax.set_title("Top regulatory topics over time (by publication date)",
                 fontsize=13, pad=12)
    ax.set_ylabel("Items per day")
    ax.legend(loc="upper left", fontsize=9, ncol=2)
    plt.xticks(rotation=35, ha="right", fontsize=9)
    plt.tight_layout()
    path = plots_dir / f"{today}_topics_over_time.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Saved → {path}")
    return path


def plot_stance_over_time(history_df: pd.DataFrame, plots_dir: Path, today: str):
    """
    100% stacked-area of pro/neutral/anti regulation share over time.
    Reveals shifts in regulatory mood across the dataset.
    """
    if history_df.empty or "stance" not in history_df.columns:
        return None

    df = _ensure_pub_date(history_df)
    df = df.dropna(subset=["pub_date"])
    if df.empty:
        return None

    pivot = (
        df.groupby(["pub_date", "stance"]).size()
        .unstack(fill_value=0)
        .sort_index()
    )
    if len(pivot) < 2:
        return None

    # Normalize to share (sums to 1.0 per day)
    row_totals = pivot.sum(axis=1).replace(0, 1)
    share = pivot.div(row_totals, axis=0)

    ordered = [c for c in ["pro-regulation", "neutral/mixed", "anti-regulation"]
               if c in share.columns]
    if not ordered:
        return None
    share = share[ordered]

    fig, ax = _fig(11, 4.5)
    ax.stackplot(
        share.index, share.T.values,
        labels=ordered,
        colors=[STANCE_COLORS[c] for c in ordered],
        alpha=0.9,
    )
    ax.set_ylim(0, 1)
    ax.set_ylabel("Share of items")
    ax.set_title("Regulatory stance share over time (by publication date)",
                 fontsize=13, pad=12)
    ax.legend(loc="upper left", fontsize=9)
    plt.xticks(rotation=35, ha="right", fontsize=9)
    plt.tight_layout()
    path = plots_dir / f"{today}_stance_over_time.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Saved → {path}")
    return path


# ── Markdown report ───────────────────────────────────────────────────────────

def build_report(df: pd.DataFrame, history_df: pd.DataFrame,
                 plots_dir: Path, today: str) -> str:
    total = len(df)
    if total == 0:
        return (
            f"# AI in Law — Daily Sentiment Report\n"
            f"**Date:** {today}\n\n"
            f"_No items matching AI + Law criteria were published in the look-back window._\n"
        )

    sentiment_counts = df["vader_label"].value_counts().to_dict()
    pos = sentiment_counts.get("positive", 0)
    neg = sentiment_counts.get("negative", 0)
    neu = sentiment_counts.get("neutral", 0)
    avg_compound = df["vader_compound"].mean()

    stance_counts = df["stance"].value_counts().to_dict() if "stance" in df.columns else {}

    # Top topics today
    all_topics: list[str] = []
    if "topics" in df.columns:
        for topics in df["topics"]:
            all_topics.extend(_coerce_topics(topics))
    top_topics = Counter(all_topics).most_common(5)

    # Date range of articles covered today
    df_dates = _ensure_pub_date(df).dropna(subset=["pub_date"])
    if not df_dates.empty:
        pub_min = df_dates["pub_date"].min().isoformat()
        pub_max = df_dates["pub_date"].max().isoformat()
        date_range_note = (
            f"_Articles in this report were published between **{pub_min}** "
            f"and **{pub_max}**._\n"
        )
    else:
        date_range_note = ""

    # Top items — guard against missing columns (e.g. when a source didn't
    # return a URL field).
    wanted_cols = ["title", "source", "vader_compound", "url"]
    available = [c for c in wanted_cols if c in df.columns]
    top_positive = df.nlargest(3, "vader_compound")[available]
    top_negative = df.nsmallest(3, "vader_compound")[available]

    if avg_compound >= 0.05:
        overall_direction = "🟢 Mildly positive"
    elif avg_compound <= -0.05:
        overall_direction = "🔴 Mildly negative"
    else:
        overall_direction = "⚪ Neutral / mixed"

    history_note = ""
    if not history_df.empty and len(history_df) > total:
        hist_avg = history_df["vader_compound"].mean()
        delta = avg_compound - hist_avg
        direction = "↑" if delta > 0 else "↓"
        history_note = (
            f"Compared to the historical average of **{hist_avg:+.3f}**, "
            f"today's sentiment is {direction} **{abs(delta):.3f}** points "
            f"{'higher' if delta > 0 else 'lower'}.\n"
        )

    lines = [
        f"# AI in Law — Daily Sentiment Report",
        f"**Run date:** {today} | **Items analyzed:** {total} | "
        f"**Overall:** {overall_direction} ({avg_compound:+.3f})",
        "",
        date_range_note,
        "---",
        "",
        "## Summary",
        "",
        f"Today's collection covers **{total}** items from news outlets, "
        f"academic preprints, Reddit, and regulatory sources.",
        history_note,
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Positive items | {pos} ({_pct(pos, total)}) |",
        f"| Neutral items  | {neu} ({_pct(neu, total)}) |",
        f"| Negative items | {neg} ({_pct(neg, total)}) |",
        f"| Avg. VADER compound | {avg_compound:+.4f} |",
        f"| Pro-regulation items | {stance_counts.get('pro-regulation', 0)} |",
        f"| Anti-regulation items | {stance_counts.get('anti-regulation', 0)} |",
        "",
        "---",
        "",
        "## Top Topics Today",
        "",
    ]

    if top_topics:
        for topic, count in top_topics:
            lines.append(f"- **{topic.replace('_', ' ').title()}** — {count} items")
    else:
        lines.append("_No strong topic signals detected today._")

    lines += [
        "",
        "---",
        "",
        "## Most Positive Coverage",
        "",
    ]
    for _, row in top_positive.iterrows():
        title = str(row.get("title", ""))[:100]
        source = row.get("source", "")
        score = row.get("vader_compound", 0)
        url = row.get("url", "")
        link = f"[{title}]({url})" if url else title
        lines.append(f"- {link}  \n  _{source}_ — VADER: `{score:+.3f}`")

    lines += [
        "",
        "---",
        "",
        "## Most Critical / Negative Coverage",
        "",
    ]
    for _, row in top_negative.iterrows():
        title = str(row.get("title", ""))[:100]
        source = row.get("source", "")
        score = row.get("vader_compound", 0)
        url = row.get("url", "")
        link = f"[{title}]({url})" if url else title
        lines.append(f"- {link}  \n  _{source}_ — VADER: `{score:+.3f}`")

    lines += [
        "",
        "---",
        "",
        "## Visualizations — Today",
        "",
        f"![Sentiment Distribution](plots/{today}_sentiment_dist.png)",
        f"![Topic Breakdown](plots/{today}_topic_breakdown.png)",
        f"![Source Sentiment](plots/{today}_source_sentiment.png)",
        f"![Regulatory Stance](plots/{today}_stance.png)",
        f"![Word Cloud](plots/{today}_wordcloud.png)",
        "",
        "## Visualizations — Trends Over Time",
        "",
        f"![Sentiment Timeline](plots/{today}_timeline.png)",
        f"![Topics Over Time](plots/{today}_topics_over_time.png)",
        f"![Stance Over Time](plots/{today}_stance_over_time.png)",
        "",
        "---",
        "",
        "## Methodology",
        "",
        "- **VADER** (Valence Aware Dictionary and sEntiment Reasoner) — compound score in [-1, 1].",
        "- **Topic tagging** — regex keyword matching across 12 AI-law sub-domains.",
        "- **Stance detection** — keyword-based pro/anti-regulation signal detection.",
        "- **Date filter** — items are kept only if their *publication* date falls within the look-back window (default 2 days).",
        "- Sources: RSS news feeds, arXiv academic API, Reddit (PRAW), Regulations.gov API.",
        "",
        f"_Generated automatically on {_utcnow().strftime('%Y-%m-%d %H:%M UTC')}._",
        "",
    ]

    return "\n".join(lines)


# ── README updater ────────────────────────────────────────────────────────────

def _trends_section_md(history_df: pd.DataFrame, today: str,
                       plots_dir: Path) -> str:
    """
    Build the markdown for a 'Trends Over Time' block embedded in the README.
    Always returns at least a placeholder so the README stays well-formed.
    Only references plot images that were actually generated.
    """
    if history_df.empty:
        return "_Not enough historical data yet. Trends will populate after the first few runs._"

    df = _ensure_pub_date(history_df).dropna(subset=["pub_date"])
    if df.empty:
        return "_No items with parseable publication dates yet._"

    # 7-day vs 30-day average sentiment
    today_d = date.today()
    last_7   = df[df["pub_date"] >= today_d - timedelta(days=7)]
    last_30  = df[df["pub_date"] >= today_d - timedelta(days=30)]
    overall  = df

    def _avg(d):
        return f"{d['vader_compound'].mean():+.3f}" if not d.empty else "—"

    def _n(d):
        return len(d) if not d.empty else 0

    # Top recurring topics in the last 30 days
    topic_counter: Counter = Counter()
    if "topics" in last_30.columns:
        for t in last_30["topics"]:
            topic_counter.update(_coerce_topics(t))
    top5 = topic_counter.most_common(5)
    topics_md = (
        ", ".join(f"**{name.replace('_',' ').title()}** ({count})" for name, count in top5)
        if top5 else "_No recurring topics yet._"
    )

    # Stance share over the last 30 days
    stance_md = "—"
    if "stance" in last_30.columns and not last_30.empty:
        sc = last_30["stance"].value_counts(normalize=True) * 100
        stance_md = (
            f"Pro **{sc.get('pro-regulation', 0):.0f}%** · "
            f"Neutral **{sc.get('neutral/mixed', 0):.0f}%** · "
            f"Anti **{sc.get('anti-regulation', 0):.0f}%**"
        )

    # Only embed plots that actually exist on disk this run.
    plot_lines = []
    for slug, alt in [
        ("timeline",          "Sentiment Timeline"),
        ("topics_over_time",  "Topics Over Time"),
        ("stance_over_time",  "Stance Over Time"),
    ]:
        plot_path = plots_dir / f"{today}_{slug}.png"
        if plot_path.exists():
            plot_lines.append(f"![{alt}](reports/plots/{today}_{slug}.png)")
    plot_block = "\n".join(plot_lines) if plot_lines else (
        "_Trend plots will appear after 2+ days of data are collected._"
    )

    md = (
        "| Window | Items | Avg. sentiment |\n"
        "|--------|-------|----------------|\n"
        f"| Last 7 days  | {_n(last_7)}  | {_avg(last_7)}  |\n"
        f"| Last 30 days | {_n(last_30)} | {_avg(last_30)} |\n"
        f"| All-time     | {_n(overall)} | {_avg(overall)} |\n"
        "\n"
        f"**Most-discussed regulatory topics (last 30 days):** {topics_md}\n"
        "\n"
        f"**Stance distribution (last 30 days):** {stance_md}\n"
        "\n"
        f"{plot_block}\n"
    )
    return md.strip()


def update_readme(df: pd.DataFrame, history_df: pd.DataFrame,
                  reports_dir: Path, today: str):
    """Rewrite README.md with current stats AND a longitudinal Trends section."""
    if history_df.empty:
        combined = df
    else:
        combined = pd.concat([history_df, df], ignore_index=True)

    total_historic = len(combined)
    avg_compound   = combined["vader_compound"].mean() if not combined.empty else 0.0

    combined_pd = _ensure_pub_date(combined)
    days_running = (
        combined_pd["pub_date"].dropna().nunique()
        if not combined_pd.empty and "pub_date" in combined_pd.columns else 1
    )

    plots_dir = reports_dir / "plots"
    trends_md = _trends_section_md(combined, today, plots_dir)

    # Plain string — no textwrap.dedent — so that the embedded trends_md
    # block doesn't get its indentation mangled.
    readme = f"""# AI in Law — Public Sentiment Analysis

> Automated daily tracking of public and academic sentiment toward AI regulation and law.
> Data collected from news outlets, arXiv, Reddit, and regulatory sources.
> Updated every day via GitHub Actions.

## Latest snapshot — {today}

| Metric | Value |
|--------|-------|
| Total items analyzed | {total_historic:,} |
| Days with data       | {days_running} |
| Historical avg. VADER score | {avg_compound:+.4f} |
| Latest daily report  | [View report](reports/{today}_report.md) |

## Trends Over Time

{trends_md}

## Why this project?

Public opinion and academic discourse on AI regulation is evolving rapidly. This project
provides an open, reproducible dataset tracking sentiment across:

- 🗞️ **News**: Ars Technica, The Verge, MIT Tech Review, Wired, TechCrunch, LawFare, EFF, Brookings, Stanford HAI, AlgorithmWatch
- 📚 **Academic**: arXiv preprints on AI law and governance
- 💬 **Social**: Reddit (r/law, r/AIPolicy, r/MachineLearning, and others)
- 🏛️ **Regulatory**: Regulations.gov

## Data

- **Raw**: [`data/raw/`](data/raw/) — daily JSON snapshots
- **Processed**: [`data/processed/`](data/processed/) — enriched CSV with sentiment scores
- **Reports**: [`reports/`](reports/) — daily Markdown summaries + charts

## How to run locally

```bash
git clone https://github.com/Felipe-ML-Projects/AI-Law-Sentiment.git
cd AI-Law-Sentiment
pip install -r requirements.txt
python main.py
```

Optional environment variables for richer data:
```
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REGULATIONS_API_KEY=...
LOOKBACK_DAYS=2          # how many days back to include (default 2)
```

## Techniques

- **VADER** — rule-based sentiment (fast, no GPU required)
- **FinBERT** — transformer-based sentiment (optional)
- **Topic tagging** — 12 AI-law sub-domains (bias, liability, privacy, etc.)
- **Stance detection** — pro/anti-regulation signal analysis
- **Word clouds** — discourse visualization
- **Date-aware filtering** — only items published in the look-back window are kept

## Citation

```
@misc{{ai-law-sentiment,
  author = {{Felipe-ML-Projects}},
  title  = {{AI in Law: Public Sentiment Analysis Dataset}},
  year   = {{2026}},
  url    = {{https://github.com/Felipe-ML-Projects/AI-Law-Sentiment}}
}}
```

## License

Data: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
Code: [MIT](LICENSE)

---
_Updated automatically on {_utcnow().strftime('%Y-%m-%d %H:%M UTC')} by GitHub Actions._
"""

    path = reports_dir.parent / "README.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(readme)
    log.info(f"README updated → {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def generate_report(items: list[dict], history_df: Optional[pd.DataFrame] = None,
                    reports_dir: Optional[str] = None) -> Path:
    """
    Generate all charts, the Markdown report, and update the README.
    Returns the path to the generated report.
    """
    from sentiment import load_history

    today = date.today().isoformat()
    rep_dir = Path(reports_dir or config.REPORTS_DIR)
    plots_dir = rep_dir / "plots"
    rep_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(items)
    if history_df is None:
        history_df = load_history()

    # Today's charts
    plot_sentiment_distribution(df, plots_dir, today)
    plot_topic_breakdown(df, plots_dir, today)
    plot_source_sentiment(df, plots_dir, today)
    plot_stance_breakdown(df, plots_dir, today)
    plot_wordcloud(df, plots_dir, today)

    # Trend charts use the combined (history + today) dataset
    if not history_df.empty or not df.empty:
        combined = pd.concat([history_df, df], ignore_index=True) if not history_df.empty else df
        plot_timeline(combined, plots_dir, today)
        plot_topics_over_time(combined, plots_dir, today)
        plot_stance_over_time(combined, plots_dir, today)

    # Markdown report
    md = build_report(df, history_df, plots_dir, today)
    report_path = rep_dir / f"{today}_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
    log.info(f"Report saved → {report_path}")

    # README with trends
    update_readme(df, history_df, rep_dir, today)

    return report_path


if __name__ == "__main__":
    # Quick smoke test with two dummy items
    dummy = [
        {"id": "1", "source": "Reuters", "type": "news",
         "title": "EU AI Act passes — strict rules for high-risk AI systems",
         "text": "The landmark regulation imposes accountability requirements.",
         "vader_label": "positive", "vader_compound": 0.42,
         "vader_pos": 0.3, "vader_neg": 0.05, "vader_neu": 0.65,
         "topics": ["eu_ai_act", "transparency"], "stance": "pro-regulation",
         "pub_date": date.today().isoformat(),
         "fetched": _utcnow().isoformat()},
        {"id": "2", "source": "Ars Technica", "type": "news",
         "title": "Critics say AI legislation will crush startup innovation",
         "text": "Industry groups warn of regulatory overreach and compliance costs.",
         "vader_label": "negative", "vader_compound": -0.38,
         "vader_pos": 0.05, "vader_neg": 0.28, "vader_neu": 0.67,
         "topics": ["us_legislation", "labor"], "stance": "anti-regulation",
         "pub_date": date.today().isoformat(),
         "fetched": _utcnow().isoformat()},
    ]
    path = generate_report(dummy, pd.DataFrame())
    print(f"Report: {path}")
