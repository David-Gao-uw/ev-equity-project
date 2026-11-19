# Electrification and Equity — CSE 163 Final Project

Income, secondary markets, and policy thresholds in Washington State electric vehicle adoption.

## What is here

| Path | Purpose |
| --- | --- |
| `src/download.py` | Downloads the three source CSVs and checks their size and row count against the report's snapshot |
| `src/data.py` | Loaders, ZIP normalisation, aggregation, income quartiles, RQ3/RQ4 samples |
| `src/eda_report.py` | Computes every EDA statistic and writes all fourteen figures |
| `tests/test_data.py`, `tests/test_eda_report.py` | Unit tests on hand-built frames |
| `tests/test_cross_check.py` | Recomputes key aggregates from the raw CSVs with the `csv` module (skipped without `data/`) |
| `figures/` | Generated plots referenced by the report |
| `notes/eda_stats.json` | Every number quoted in the report, as computed |
| `eda_report.md`, `style_eda.css`, `build_eda_pdf.sh` | Report source and the script that builds `eda.pdf` |
| `eda.pdf` | The submitted report |

## Reproducing the analysis

Run every command from the project root.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python src/download.py          # ~1.2 GB of CSVs into data/
MPLCONFIGDIR=.mplcache python src/eda_report.py
```

`src/eda_report.py` regenerates `figures/` and `notes/eda_stats.json`; the
report quotes the latter directly, so prose and computation cannot diverge.

The report was computed from data downloaded on **2026-11-18**. The two DOL
datasets are live and refreshed monthly, so a later download will differ
slightly; `src/download.py` prints `CHANGED` when it does.

## Tests and style

```bash
python -m pytest tests/ -q      # about 20 s with data/ present
python -m flake8 src/ tests/
```

## Rebuilding the PDF

`./build_eda_pdf.sh` converts `eda_report.md` to HTML with pandoc, prints it
with headless Microsoft Edge, and stamps page numbers with `pypdf` and
`reportlab` (both in `requirements.txt`).

## Data sources

- WA Dept. of Licensing, [Electric Vehicle Population Data](https://data.wa.gov/api/views/f6w7-q2d2/rows.csv?accessType=DOWNLOAD)
- WA Dept. of Licensing, [EV Title and Registration Activity](https://data.wa.gov/api/views/rpr4-cgyd/rows.csv?accessType=DOWNLOAD)
- IRS Statistics of Income, [ZIP Code Data TY2022](https://www.irs.gov/pub/irs-soi/22zpallagi.csv)

All three are public and need no account or API key. Raw data is gitignored
because of its size; `src/download.py` fetches it.
