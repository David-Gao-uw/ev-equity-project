"""Fetch the three project datasets and verify they arrived intact.

Running this module downloads every source CSV into ``data/`` and checks
each file's byte size and row count against the values observed when the
project was started.  A mismatch means the upstream dataset changed, which
should be investigated before trusting any downstream result.

Usage::

    python src/download.py
"""

import os
import sys
import urllib.request

DATA_DIR = "data"

# name, url, expected bytes (approx), expected data rows
SOURCES = [
    (
        "ev_population.csv",
        ("https://data.wa.gov/api/views/"
         "f6w7-q2d2/rows.csv?accessType=DOWNLOAD"),
        72559172,
        300142,
    ),
    (
        "ev_transactions.csv",
        ("https://data.wa.gov/api/views/"
         "rpr4-cgyd/rows.csv?accessType=DOWNLOAD"),
        257959126,
        1926507,
    ),
    (
        "irs_zip_income.csv",
        "https://www.irs.gov/pub/irs-soi/22zpallagi.csv",
        216173999,
        None,
    ),
]


def count_rows(path):
    """Return the number of data rows (header excluded) in a CSV file."""
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def download(url, dest):
    """Download ``url`` to ``dest`` unless the file already exists."""
    if os.path.exists(dest):
        print(f"  exists, skipping: {dest}")
        return
    print(f"  downloading: {dest}")
    request = urllib.request.Request(url,
                                     headers={"User-Agent": "Mozilla/5.0"})
    with (
        urllib.request.urlopen(request, timeout=180) as response,
        open(dest, "wb") as out,
    ):
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)


def verify(path, expected_bytes, expected_rows):
    """Print and sanity-check the size and row count of a downloaded file."""
    size = os.path.getsize(path)
    rows = count_rows(path)
    ratio = size / expected_bytes
    status = "ok" if 0.95 <= ratio <= 1.05 else "CHANGED"
    detail = f"{size:,} bytes ({ratio:.0%} of expected)"
    if expected_rows is not None:
        row_ratio = rows / expected_rows
        detail += f", {rows:,} rows ({row_ratio:.1%} of expected)"
        if not 0.95 <= row_ratio <= 1.05:
            status = "CHANGED"
    print(f"  {status:8} {path}: {detail}")
    return status == "ok"


def main():
    """Download and verify every source file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    results = []
    for name, url, expected_bytes, expected_rows in SOURCES:
        path = os.path.join(DATA_DIR, name)
        download(url, path)
        results.append(verify(path, expected_bytes, expected_rows))
    if all(results):
        print("All sources match expectations.")
    else:
        print("WARNING: at least one source changed; re-check the report.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
