"""Load and clean the three datasets used by the EV equity project.

The raw files keep their original column names (the Washington DOL exports
use human-readable headers), so every function here returns a DataFrame that
still carries those names plus three derived columns added for analysis:
``ZIP`` (normalised five-digit postal code), ``INCOME_QUARTILE`` (added by
:func:`add_income_quartile`) and the aggregate columns described below.

Usage::

    python src/data.py
"""

import os

import numpy as np
import pandas as pd

DATA_DIR = "data"
EV_POPULATION_PATH = os.path.join(DATA_DIR, "ev_population.csv")
EV_TRANSACTIONS_PATH = os.path.join(DATA_DIR, "ev_transactions.csv")
IRS_INCOME_PATH = os.path.join(DATA_DIR, "irs_zip_income.csv")

# A ZIP with fewer returns than this has an average income dominated by a
# handful of high earners, so it is excluded from every income comparison.
MIN_RETURNS = 100

# HB 2042 (2019) required a minimum electric range for the tax exemption.
HB2042_RANGE_MILES = 30

POP_COLUMNS = [
    "County",
    "Postal Code",
    "Model Year",
    "Make",
    "Model",
    "Electric Vehicle Type",
    "Electric Range",
    "DOL Vehicle ID",
    "2020 GEOID",
]

TX_COLUMNS = [
    "DOL Vehicle ID",
    "Model Year",
    "Electric Range",
    "New or Used Vehicle",
    "Sale Price",
    "Transaction Type",
    "Transaction Date",
    "Year",
    "County",
    "State",
    "Postal Code",
    "Meets 2019 HB 2042 Electric Range Requirement",
]

IRS_COLUMNS = ["STATEFIPS", "STATE", "zipcode", "agi_stub", "N1", "A00100"]


def normalize_zip(values):
    """Return a Series of five-digit ZIP codes, with unusable values as NA.

    Raw files mix formats: numeric ZIPs lose their leading zero when read as
    numbers, some rows carry a trailing ``.0``, and state-total rows in the
    IRS file use ``00000``.  Everything that is not a real five-digit ZIP
    becomes ``pd.NA`` so that joins cannot silently match on a fake code.
    """
    text = values.astype("string").str.strip()
    text = text.str.replace(r"\.0$", "", regex=True)
    text = text.str.replace(r"\D", "", regex=True)
    text = text.str.zfill(5)
    valid = text.str.len().eq(5) & text.ne("00000") & text.notna()
    return text.where(valid)


def load_ev_population(path=EV_POPULATION_PATH, nrows=None):
    """Load the registered-EV population file, one row per vehicle.

    ``Postal Code`` is read as text so that leading zeros survive, and a
    normalised ``ZIP`` column is added.
    """
    frame = pd.read_csv(
        path,
        usecols=POP_COLUMNS,
        dtype={"Postal Code": "string"},
        nrows=nrows,
        low_memory=False,
    )
    frame["ZIP"] = normalize_zip(frame["Postal Code"])
    return frame


def load_ev_transactions(path=EV_TRANSACTIONS_PATH, nrows=None):
    """Load the title/registration transaction file, one row per event.

    Only the columns needed for the research questions are read; the file is
    260 MB and carries thirty-three columns.
    """
    frame = pd.read_csv(
        path,
        usecols=TX_COLUMNS,
        dtype={"Postal Code": "string"},
        nrows=nrows,
        low_memory=False,
    )
    frame["ZIP"] = normalize_zip(frame["Postal Code"])
    return frame


def load_irs_zip_income(path=IRS_INCOME_PATH, nrows=None):
    """Load IRS ZIP-level income aggregates for Washington State.

    The file stacks one row per ZIP and AGI bracket, so it is collapsed to one
    row per ZIP here.  State-total rows (``zipcode == "00000"``) are dropped.
    """
    frame = pd.read_csv(
        path,
        usecols=IRS_COLUMNS,
        dtype={"zipcode": "string"},
        nrows=nrows,
        low_memory=False,
    )
    frame = frame[frame["STATE"] == "WA"].copy()
    frame["ZIP"] = normalize_zip(frame["zipcode"])
    frame = frame.dropna(subset=["ZIP"])
    return frame


def income_profile(irs_frame, min_returns=MIN_RETURNS):
    """Collapse IRS brackets to one row per ZIP with average AGI per return.

    Returns a frame indexed by ``ZIP`` with ``RETURNS``, ``TOTAL_AGI`` and
    ``AVG_AGI``, keeping only ZIPs with at least ``min_returns`` returns.
    ``A00100`` is reported in thousands of dollars by the IRS.
    """
    grouped = irs_frame.groupby("ZIP", as_index=False).agg(
        RETURNS=("N1", "sum"),
        TOTAL_AGI=("A00100", "sum"),
    )
    grouped = grouped[grouped["RETURNS"] >= min_returns].copy()
    grouped["AVG_AGI"] = grouped["TOTAL_AGI"] / grouped["RETURNS"]
    return grouped.reset_index(drop=True)


def weighted_quantile(values, weights, probs):
    """Return weighted quantiles of ``values`` using ``weights``."""
    order = np.argsort(values)
    values = np.asarray(values, dtype=float)[order]
    weights = np.asarray(weights, dtype=float)[order]
    cumulative = (np.cumsum(weights) - 0.5 * weights) / weights.sum()
    return np.interp(probs, cumulative, values)


def add_income_quartile(profile):
    """Assign return-weighted income quartiles, 1 = lowest average income.

    Quartile boundaries are weighted quantiles of ``AVG_AGI`` with ``RETURNS``
    as weights, so each quartile holds a comparable number of tax filers
    rather than a comparable number of ZIP codes.  That matters because ZIP
    sizes differ by an order of magnitude.
    """
    result = profile.copy()
    edges = weighted_quantile(
        result["AVG_AGI"], result["RETURNS"], (0.25, 0.5, 0.75)
    )
    quartile = np.searchsorted(edges, result["AVG_AGI"], side="right") + 1
    result["INCOME_QUARTILE"] = quartile.astype("int64")
    return result


def zip_ev_counts(pop_frame):
    """Aggregate the population file to one row per ZIP.

    Vehicles are deduplicated on ``DOL Vehicle ID`` before counting:
    ``VIN (1-10)`` is a ten-character prefix shared by different vehicles, so
    it cannot serve as a key, and counting rows would let a duplicated record
    push ``BEV_COUNT`` above ``EV_COUNT``.
    """
    valid = pop_frame.dropna(subset=["ZIP"])
    deduped = valid.drop_duplicates(subset=["ZIP", "DOL Vehicle ID"])
    grouped = deduped.groupby("ZIP", as_index=False).agg(
        EV_COUNT=("DOL Vehicle ID", "nunique"),
        BEV_COUNT=(
            "Electric Vehicle Type",
            lambda series: (series == "Battery Electric Vehicle (BEV)").sum(),
        ),
    )
    grouped["BEV_SHARE"] = grouped["BEV_COUNT"] / grouped["EV_COUNT"]
    return grouped


def zip_condition_counts(tx_frame):
    """Count new versus used registrations per ZIP."""
    valid = tx_frame.dropna(subset=["ZIP"])
    counts = (
        valid.groupby(["ZIP", "New or Used Vehicle"], as_index=True)
        .size()
        .unstack(fill_value=0)
    )
    counts = counts.reindex(columns=["New", "Used"], fill_value=0)
    totals = counts.sum(axis=1)
    counts["USED_SHARE"] = counts["Used"] / totals.where(totals > 0)
    return counts.reset_index()


def main():
    """Run every loader and report basic shape information."""
    population = load_ev_population()
    print(f"EV population : {population.shape}")
    transactions = load_ev_transactions()
    print(f"EV transactions: {transactions.shape}")
    income = income_profile(load_irs_zip_income())
    print(f"IRS ZIP profile: {income.shape}")
    print(income.head())


if __name__ == "__main__":
    main()
