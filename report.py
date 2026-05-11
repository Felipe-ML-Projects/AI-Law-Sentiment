"""
report.py
Generates a daily Markdown report + charts from analyzed sentiment data.

Output structure:
  reports/
    YYYY-MM-DD_report.md       ← human-readable daily summary
    plots/
      YYYY-MM-DD_sentiment_dist.png
      YYYY-MM-DD_topic_breakdown.png
      YYYY-MM-DD_source_sentiment.png
      YYYY-MM-DD_timeline.png
      YYYY-MM-DD_wordcloud.png
  README.md                    ← auto-updated project landing page
"""

import json
import logging
import textwrap
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
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


def _fig(w=9, h=5):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#DDDDDD")
    ax.tick_params(colors="#444444")
    ax.title.set_color("#222222")
    return fig, ax


# ── Charts ────────────────────────────────────────────────────────────────────

def plot_sentiment_distribution(df: pd.DataFrame, plots_dir: Path, today: str):
    """Pie / bar: positive vs neutral vs negative."""
    counts = df["vader_label"].value_counts()
    labels_order = ["positive", "neutral", "negative"]
    values = [counts.get(l, 0) for l in labels_order]
    colors = [SENTIMENT_COLORS[l] for l in labels_order]

    fig, ax = _fig(7, 5)
    bars = ax.bar(labels_order, values, color=colors, width=0.5, edgecolor="white", linewidth=1.5)
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
    """Horizontal bar: top topics, stacked by sentiment."""
    topic_sentiment = defaultdict(Counter)
    for _, row in df.iterrows():
        topics = row.get("topics", [])
        if isinstance(topics, str):
            import ast
            try:
                topics = ast.literal_eval(topics)
            except Exception:
                topics = []
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
        bars = ax.barh(y, vals, left=left, color=SENTIMENT_COLORS[sentiment],
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
    """Bar: average VADER compound score by source (top 10 sources)."""
    avg = (
        df.groupby("source")["vader_compound"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "avg_compound", "count": "n"})
        .query("n >= 3")
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


def plot_timeline(history_df: pd.DataFrame, plots_dir: Path, today: str):
    """Line chart: daily average sentiment over time."""
    if history_df.empty or "fetched" not in history_df.columns:
        return None

    df = history_df.copy()
    df["date"] = pd.to_datetime(df["fetched"], errors="coerce").dt.date
    daily = (
        df.groupby("date")["vader_compound"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "avg", "count": "n"})
        .reset_index()
        .sort_values("date")
    )

    if len(daily) < 2:
        return None

    fig, ax = _fig(11, 4)
    ax.plot(daily["date"], daily["avg"], color="#3B7DD8", linewidth=2, marker="o", markersize=4)
    ax.fill_between(daily["date"], daily["avg"], alpha=0.12, color="#3B7DD8")
    ax.axhline(0, color="#AAAAAA", linewidth=0.8, linestyle="--")
    ax.set_ylabel("Avg. VADER compound")
    ax.set_title("Daily sentiment trend — AI in law coverage", fontsize=13, pad=12)
    plt.xticks(rotation=35, ha="right", fontsize=9)
    plt.tight_layout()
    path = plots_dir / f"{today}_timeline.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Saved → {path}")
    return path


def plot_wordcloud(df: pd.DataFrame, plots_dir: Path, today: str):
    """Word cloud from all titles and text."""
    all_text = " ".join(
        str(df.get("title", "")) + " " + str(df.get("text", ""))
        for _, df in df.iterrows()
    )
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


def plot_stance_breakdown(df: pd.DataFrame, plots_dir: Path, today: str):
    """Pie chart: regulatory stance distribution."""
    counts = df["stance"].value_counts()
    labels = ["pro-regulation", "neutral/mixed", "anti-regulation"]
    sizes  = [counts.get(l, 0) for l in labels]
    colors = [STANCE_COLORS[l] for l in labels]

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


# ── Markdown report ───────────────────────────────────────────────────────────

def build_report(df: pd.DataFrame, history_df: pd.DataFrame,
                 plots_dir: Path, today: str) -> str:
    """Build the full Markdown daily report string."""

    total = len(df)
    if total == 0:
        return f"# Daily Report — {today}\n\n_No data collected today._\n"

    sentiment_counts = df["vader_label"].value_counts().to_dict()
    pos = sentiment_counts.get("positive", 0)
    neg = sentiment_counts.get("negative", 0)
    neu = sentiment_counts.get("neutral", 0)
    avg_compound = df["vader_compound"].mean()

    stance_counts = df["stance"].value_counts().to_dict()

    # Top topics
    all_topics: list[str] = []
    for topics in df["topics"]:
        if isinstance(topics, list):
            all_topics.extend(topics)
        elif isinstance(topics, str):
            import ast
            try:
                all_topics.extend(ast.literal_eval(topics))
            except Exception:
                pass
    top_topics = Counter(all_topics).most_common(5)

    # Top items (most positive / most negative)
    df_s = df.copy()
    top_positive = df_s.nlargest(3, "vader_compound")[["title", "source", "vader_compound", "url"]]
    top_negative = df_s.nsmallest(3, "vader_compound")[["title", "source", "vader_compound", "url"]]

    # Overall sentiment direction
    if avg_compound >= 0.05:
        overall_direction = "🟢 Mildly positive"
    elif avg_compound <= -0.05:
        overall_direction = "🔴 Mildly negative"
    else:
        overall_direction = "⚪ Neutral / mixed"

    # History stats
    history_note = ""
    if not history_df.empty and len(history_df) > total:
        hist_avg = history_df["vader_compound"].mean()
        delta = avg_compound - hist_avg
        direction = "↑" if delta > 0 else "↓"
        history_note = f"Compared to the historical average of **{hist_avg:.3f}**, today's sentiment is {direction} **{abs(delta):.3f}** points {'higher' if delta > 0 else 'lower'}.\n"

    lines = [
        f"# AI in Law — Daily Sentiment Report",
        f"**Date:** {today} | **Items analyzed:** {total} | **Overall:** {overall_direction} ({avg_compound:+.3f})",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"Today's collection covers **{total}** items from news outlets, academic preprints, Reddit, and regulatory sources.",
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
        "## Visualizations",
        "",
        f"![Sentiment Distribution](plots/{today}_sentiment_dist.png)",
        f"![Topic Breakdown](plots/{today}_topic_breakdown.png)",
        f"![Source Sentiment](plots/{today}_source_sentiment.png)",
        f"![Regulatory Stance](plots/{today}_stance.png)",
        f"![Word Cloud](plots/{today}_wordcloud.png)",
        f"![Timeline](plots/{today}_timeline.png)",
        "",
        "---",
        "",
        "## Methodology",
        "",
        "- **VADER** (Valence Aware Dictionary and sEntiment Reasoner) — compound score in [-1, 1].",
        "- **Topic tagging** — regex keyword matching across 12 AI-law sub-domains.",
        "- **Stance detection** — keyword-based pro/anti-regulation signal detection.",
        "- Sources: RSS news feeds, arXiv academic API, Reddit (PRAW), Regulations.gov API.",
        "",
        f"_Generated automatically on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}._",
        "",
    ]

    return "\n".join(lines)


# ── README updater ────────────────────────────────────────────────────────────

def update_readme(df: pd.DataFrame, history_df: pd.DataFrame,
                  reports_dir: Path, today: str):
    """Rewrite the repo README with current project stats."""
    total_historic = len(history_df) if not history_df.empty else len(df)
    avg_compound = history_df["vader_compound"].mean() if not history_df.empty else df["vader_compound"].mean()
    days_running = (
        (history_df["fetched"].apply(lambda x: str(x)[:10]).nunique())
        if not history_df.empty and "fetched" in history_df.columns else 1
    )

    readme = textwrap.dedent(f"""
    # AI in Law — Public Sentiment Analysis

    > Automated daily tracking of public and academic sentiment toward AI regulation and law.
    > Data collected from news outlets, arXiv, Reddit, and regulatory sources.
    > Updated every day via GitHub Actions.

    ## Latest snapshot — {today}

    | Metric | Value |
    |--------|-------|
    | Total items analyzed | {total_historic:,} |
    | Days running | {days_running} |
    | Historical avg. VADER score | {avg_compound:+.4f} |
    | Latest daily report | [View report](reports/{today}_report.md) |

    ## Why this project?

    Public opinion and academic discourse on AI regulation is evolving rapidly. This project
    provides an open, reproducible dataset tracking sentiment across:

    - 🗞️ **News**: Reuters, Ars Technica, POLITICO, Wired, MIT Tech Review, LawFare
    - 📚 **Academic**: arXiv & SSRN preprints on AI law and governance
    - 💬 **Social**: Reddit (r/law, r/AIPolicy, r/MachineLearning, and others)
    - 🏛️ **Regulatory**: Regulations.gov, EUR-Lex, NIST

    ## Data

    - **Raw**: [`data/raw/`](data/raw/) — daily JSON snapshots
    - **Processed**: [`data/processed/`](data/processed/) — enriched CSV with sentiment scores
    - **Reports**: [`reports/`](reports/) — daily Markdown summaries + charts

    ## How to run locally

    ```bash
    git clone https://github.com/YOUR_USERNAME/ai-law-sentiment
    cd ai-law-sentiment
    pip install -r requirements.txt
    python main.py
    ```

    Set optional environment variables for richer data:
    ```
    REDDIT_CLIENT_ID=...
    REDDIT_CLIENT_SECRET=...
    REGULATIONS_API_KEY=...
    ```

    ## Techniques

    - **VADER** — rule-based sentiment (fast, no GPU required)
    - **FinBERT** — transformer-based financial/policy sentiment (optional)
    - **Topic tagging** — 12 AI-law sub-domains (bias, liability, privacy, etc.)
    - **Stance detection** — pro/anti-regulation signal analysis
    - **Word clouds** — weekly discourse visualization

    ## Citation

    If you use this dataset in your research, please cite:

    ```
    @misc{{ai-law-sentiment,
      author = {{YOUR NAME}},
      title  = {{AI in Law: Public Sentiment Analysis Dataset}},
      year   = {{2026}},
      url    = {{https://github.com/YOUR_USERNAME/ai-law-sentiment}}
    }}
    ```

    ## License

    Data: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
    Code: [MIT](LICENSE)

    ---
    _Updated automatically on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} by GitHub Actions._
    """).strip()

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

    # Charts
    plot_sentiment_distribution(df, plots_dir, today)
    plot_topic_breakdown(df, plots_dir, today)
    plot_source_sentiment(df, plots_dir, today)
    plot_wordcloud(df, plots_dir, today)
    plot_stance_breakdown(df, plots_dir, today)
    if not history_df.empty:
        combined = pd.concat([history_df, df], ignore_index=True)
        plot_timeline(combined, plots_dir, today)

    # Markdown report
    md = build_report(df, history_df, plots_dir, today)
    report_path = rep_dir / f"{today}_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
    log.info(f"Report saved → {report_path}")

    # README
    update_readme(df, history_df, rep_dir, today)

    return report_path


if __name__ == "__main__":
    import json
    # Quick test with dummy data
    dummy = [
        {"id": "1", "source": "Reuters", "type": "news",
         "title": "EU AI Act passes — strict rules for high-risk AI systems",
         "text": "The landmark regulation imposes accountability requirements.",
         "vader_label": "positive", "vader_compound": 0.42,
         "vader_pos": 0.3, "vader_neg": 0.05, "vader_neu": 0.65,
         "topics": ["eu_ai_act", "transparency"], "stance": "pro-regulation",
         "fetched": datetime.utcnow().isoformat()},
        {"id": "2", "source": "Ars Technica", "type": "news",
         "title": "Critics say AI legislation will crush startup innovation",
         "text": "Industry groups warn of regulatory overreach and compliance costs.",
         "vader_label": "negative", "vader_compound": -0.38,
         "vader_pos": 0.05, "vader_neg": 0.28, "vader_neu": 0.67,
         "topics": ["us_legislation", "labor"], "stance": "anti-regulation",
         "fetched": datetime.utcnow().isoformat()},
    ]
    path = generate_report(dummy, pd.DataFrame())
    print(f"Report: {path}")
