"""
main.py
Orchestrates the full daily pipeline:
  1. Collect data from all sources
  2. Run sentiment analysis
  3. Save processed data
  4. Generate report + charts
  5. Print summary

Run manually:    python main.py
Run on schedule: configured via .github/workflows/daily.yml
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", encoding="utf-8"),
    ]
)
log = logging.getLogger(__name__)


def run():
    log.info("=" * 60)
    log.info("AI in Law Sentiment Pipeline — starting")
    log.info("=" * 60)

    # ── Step 1: Collect ───────────────────────────────────────────
    from collector import collect_all
    items = collect_all()

    if not items:
        log.warning("No items collected. Check your source configurations.")
        return

    # ── Step 2: Analyze ───────────────────────────────────────────
    from sentiment import analyze, save_analyzed, load_history
    enriched = analyze(items)
    save_analyzed(enriched)

    # ── Step 3: Load history for trending ─────────────────────────
    history_df = load_history()

    # ── Step 4: Report ────────────────────────────────────────────
    from report import generate_report
    report_path = generate_report(enriched, history_df)

    # ── Step 5: Print summary ─────────────────────────────────────
    import pandas as pd
    df = pd.DataFrame(enriched)

    counts = df["vader_label"].value_counts()
    avg    = df["vader_compound"].mean()

    log.info("=" * 60)
    log.info("Pipeline complete.")
    log.info(f"  Items analyzed : {len(enriched)}")
    log.info(f"  Positive       : {counts.get('positive', 0)}")
    log.info(f"  Neutral        : {counts.get('neutral', 0)}")
    log.info(f"  Negative       : {counts.get('negative', 0)}")
    log.info(f"  Avg compound   : {avg:+.4f}")
    log.info(f"  Report saved   : {report_path}")
    log.info("=" * 60)


if __name__ == "__main__":
    run()
