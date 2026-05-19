"""
main.py
Orchestrates the full daily pipeline:
  1. Collect data from all sources
  2. Run sentiment analysis (skipped if nothing collected)
  3. Save processed data
  4. Generate report + charts (always, so trend plots stay fresh)
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


def run() -> int:
    """Return shell-style exit code: 0 = ok, 1 = hard failure."""
    log.info("=" * 60)
    log.info("AI in Law Sentiment Pipeline — starting")
    log.info("=" * 60)

    # ── Step 1: Collect ───────────────────────────────────────────
    try:
        from collector import collect_all
        items = collect_all()
    except Exception as e:
        log.exception(f"Collection step failed: {e}")
        return 1

    # ── Step 2 & 3: Analyze + save (only if we have items) ────────
    enriched: list[dict] = []
    if items:
        try:
            from sentiment import analyze, save_analyzed
            enriched = analyze(items)
            save_analyzed(enriched)
        except Exception as e:
            log.exception(f"Analysis step failed: {e}")
            return 1
    else:
        log.warning(
            "No items collected today. Continuing to generate an empty-state "
            "report so README + trend plots stay current."
        )

    # ── Step 4: Load history + Report ─────────────────────────────
    try:
        from sentiment import load_history
        from report import generate_report
        history_df = load_history()
        report_path = generate_report(enriched, history_df)
    except Exception as e:
        log.exception(f"Reporting step failed: {e}")
        return 1

    # ── Step 5: Summary ───────────────────────────────────────────
    if enriched:
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
    else:
        log.info("=" * 60)
        log.info("Pipeline complete (no new items today).")
        log.info(f"  Report saved   : {report_path}")
        log.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(run())
