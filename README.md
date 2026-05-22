# AI in Law — Public Sentiment Analysis

> Automated daily tracking of public and academic sentiment toward AI regulation and law.
> Data collected from news outlets, arXiv, Reddit, and regulatory sources.
> Updated every day via GitHub Actions.

## Latest snapshot — 2026-05-22

| Metric | Value |
|--------|-------|
| Total items analyzed | 417 |
| Days with data       | 4 |
| Historical avg. VADER score | +0.4507 |
| Latest daily report  | [View report](reports/2026-05-22_report.md) |

## Trends Over Time

| Window | Items | Avg. sentiment |
|--------|-------|----------------|
| Last 7 days  | 23  | -0.010  |
| Last 30 days | 23 | -0.010 |
| All-time     | 23 | -0.010 |

**Most-discussed regulatory topics (last 30 days):** **Us Legislation** (4), **Healthcare** (3), **Privacy** (2), **Labor** (2), **Transparency** (2)

**Stance distribution (last 30 days):** Pro **26%** · Neutral **74%** · Anti **0%**

![Sentiment Timeline](reports/plots/2026-05-22_timeline.png)
![Topics Over Time](reports/plots/2026-05-22_topics_over_time.png)
![Stance Over Time](reports/plots/2026-05-22_stance_over_time.png)

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
@misc{ai-law-sentiment,
  author = {Felipe-ML-Projects},
  title  = {AI in Law: Public Sentiment Analysis Dataset},
  year   = {2026},
  url    = {https://github.com/Felipe-ML-Projects/AI-Law-Sentiment}
}
```

## License

Data: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
Code: [MIT](LICENSE)

---
_Updated automatically on 2026-05-22 13:34 UTC by GitHub Actions._
