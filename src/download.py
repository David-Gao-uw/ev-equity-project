"""Fetch the three project datasets and verify they arrived intact.

Running this module downloads every source CSV into ``data/`` and checks
each file's byte size and row count against the snapshot the EDA report was
computed from (downloaded on ``SNAPSHOT_DATE``).  The two DOL files are live
and are refreshed upstream every month, so a mismatch is expected later on;
it means the numbers in the report will not reproduce exactly.

Usage::

    python src/download.py
"""

import os
import sys
import urllib.request

DATA_DIR = "data"
SNAPSHOT_DATE = "2026-11-18"

# name, url, expected bytes, expected data rows (as of SNAPSHOT_DATE)
SOURCES = [
    (
        "ev_population.csv",
        ("https://data.wa.gov/api/views/"
         "f6w7-q2d2/rows.csv?accessType=DOWNLOAD"),
        73578930,
        304258,
    ),
    (
        "ev_transactions.csv",
        ("https://data.wa.gov/api/views/"
         "rpr4-cgyd/rows.csv?accessType=DOWNLOAD"),
        952392509,
        1964093,
    ),
    (
        "irs_zip_income.csv",
        "https://www.irs.gov/pub/irs-soi/22zpallagi.csv",
        216173999,
        166131,
    ),
]


def count_rows(path):
    """Return the number of data rows (header excluded) in a CSV file."""
    lines = 0
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for _ in handle:
            lines += 1
    return max(lines - 1, 0)


def download(url, dest):
    """Download ``url`` to ``dest`` unless the file already exists.

    The file is written under a ``.part`` name and renamed only once the
    transfer completes, so an interrupted download is never mistaken for a
    finished one on the next run.
    """
    if os.path.exists(dest):
        print(f"  exists, skipping: {dest}")
        return
    print(f"  downloading: {dest}")
    partial = dest + ".part"
    request = urllib.request.Request(url,
                                     headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        with open(partial, "wb") as out:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
    os.replace(partial, dest)


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
        print(f"WARNING: at least one source changed since {SNAPSHOT_DATE};"
              " report numbers will not reproduce exactly.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
