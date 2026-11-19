# Electrification and Equity — CSE 163 Final Project

Income, secondary markets, and policy thresholds in Washington State electric vehicle adoption.

## What is here

| Path | Purpose |
| --- | --- |
| `src/download.py` | Downloads the three source CSVs and verifies their size and row count |
| `src/data.py` | Loaders, ZIP normalisation, aggregation, income quartiles |
| `src/eda_report.py` | Computes every EDA statistic and writes all twelve figures |
| `tests/test_data.py` | Unit tests for the cleaning and aggregation functions |
| `figures/` | Generated plots referenced by the report |
| `notes/eda_stats.json` | Every number quoted in the report, as computed |
| `eda.pdf` | The submitted report |

## Reproducing the analysis

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python src/download.py          # ~1.2 GB of CSVs into data/
MPLCONFIGDIR=.mplcache python src/eda_report.py
```

`src/eda_report.py` regenerates `figures/` and `notes/eda_stats.json`; the
report quotes the latter directly, so prose and computation cannot diverge.

## Tests and style

```bash
python -m pytest tests/ -q
python -m flake8 src/ tests/
```

## Data sources

- WA Dept. of Licensing, [Electric Vehicle Population Data](https://data.wa.gov/api/views/f6w7-q2d2/rows.csv?accessType=DOWNLOAD)
- WA Dept. of Licensing, [EV Title and Registration Activity](https://data.wa.gov/api/views/rpr4-cgyd/rows.csv?accessType=DOWNLOAD)
- IRS Statistics of Income, [ZIP Code Data TY2022](https://www.irs.gov/pub/irs-soi/22zpallagi.csv)

All three are public and need no account or API key. Raw data is gitignored
because of its size; `src/download.py` reproduces it exactly.
