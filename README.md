# AI in Law — Public Sentiment Analysis

> Automated daily tracking of public and academic sentiment toward AI regulation and law.
> Data collected from news outlets, arXiv, Reddit, and regulatory sources.
> Updated every day via GitHub Actions.

## Latest snapshot — 2026-05-13

| Metric | Value |
|--------|-------|
| Total items analyzed | 99 |
| Days running | 2 |
| Historical avg. VADER score | +0.4773 |
| Latest daily report | [View report](reports/2026-05-13_report.md) |

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
@misc{ai-law-sentiment,
  author = {YOUR NAME},
  title  = {AI in Law: Public Sentiment Analysis Dataset},
  year   = {2026},
  url    = {https://github.com/YOUR_USERNAME/ai-law-sentiment}
}
```

## License

Data: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
Code: [MIT](LICENSE)

---
_Updated automatically on 2026-05-13 10:38 UTC by GitHub Actions._