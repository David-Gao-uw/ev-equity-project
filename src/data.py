"""Load and clean the three datasets used by the EV equity project.

The raw files keep their original column names (the Washington DOL exports
use human-readable headers), so every loader returns a DataFrame that still
carries those names plus a normalised five-digit ``ZIP`` column.  The
aggregation helpers below add the derived columns the analysis needs:
``EV_COUNT``/``BEV_COUNT``/``BEV_SHARE`` per ZIP, ``RETURNS``/``AVG_AGI`` per
ZIP, ``INCOME_QUARTILE``, and ``ABOVE_THRESHOLD`` for used sales.

Usage::

    python src/data.py
"""

import os

import pandas as pd

DATA_DIR = "data"
EV_POPULATION_PATH = os.path.join(DATA_DIR, "ev_population.csv")
EV_TRANSACTIONS_PATH = os.path.join(DATA_DIR, "ev_transactions.csv")
IRS_INCOME_PATH = os.path.join(DATA_DIR, "irs_zip_income.csv")

# The IRS already folds ZIPs with fewer than 100 returns into ``99999``, so
# this threshold removes nothing from the TY2022 file.  It is kept as a guard
# in case a later file stops doing that suppression.
MIN_RETURNS = 100

# HB 2042 (2019) required a minimum electric range for the tax exemption.
HB2042_RANGE_MILES = 30

# Used sales outside this band are not market prices: below $1,000 they are
# nominal (gift or family) transfers, and above $250,000 they are either
# exotic supercars or dates typed into the price field (e.g. 12312016).
MIN_SALE_PRICE = 1000
MAX_SALE_PRICE = 250000

BEV = "Battery Electric Vehicle (BEV)"
PHEV = "Plug-in Hybrid Electric Vehicle (PHEV)"

# Title events are changes of ownership.  Renewals and the registration rows
# that accompany a title are not acquisitions, so they are excluded whenever
# the question is about how a vehicle reached its owner.
ACQUISITION_TYPES = ("Original Title", "Transfer Title")
NEW_TITLE_TYPE = "Original Title"

POP_COLUMNS = [
    "County",
    "State",
    "Postal Code",
    "Model Year",
    "Make",
    "Model",
    "Electric Vehicle Type",
    "Clean Alternative Fuel Vehicle (CAFV) Eligibility",
    "Electric Range",
    "DOL Vehicle ID",
    "2020 GEOID",
]

TX_COLUMNS = [
    "DOL Vehicle ID",
    "Model Year",
    "Electric Range",
    "Odometer Reading",
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

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]

# ``00000`` is the IRS state-total row and ``99999`` its bucket of small or
# non-residential ZIPs; neither is a place, so neither may enter a join.
PSEUDO_ZIPS = ("00000", "99999")


def normalize_zip(values):
    """Return a Series of five-digit ZIP codes, with unusable values as NA.

    Raw files mix formats: numeric ZIPs lose their leading zero when read as
    numbers, and some rows carry a trailing ``.0``.  Everything that is not
    a real five-digit ZIP, including the IRS pseudo-ZIPs in ``PSEUDO_ZIPS``,
    becomes ``pd.NA`` so that joins cannot silently match on a fake code.
    """
    text = values.astype("string").str.strip()
    text = text.str.replace(r"\.0$", "", regex=True)
    text = text.str.replace(r"\D", "", regex=True)
    text = text.str.zfill(5)
    valid = text.str.len().eq(5) & ~text.isin(PSEUDO_ZIPS) & text.notna()
    return text.where(valid)


def load_ev_population(path=EV_POPULATION_PATH, nrows=None):
    """Load the registered-EV population file, one row per vehicle.

    ``Postal Code`` is read as text so that leading zeros survive, and a
    normalised ``ZIP`` column is added.  Raises ``ValueError`` if a vehicle
    appears twice, because every count in the project assumes it cannot.
    """
    frame = pd.read_csv(
        path,
        usecols=POP_COLUMNS,
        dtype={"Postal Code": "string"},
        nrows=nrows,
        low_memory=False,
    )
    if not frame["DOL Vehicle ID"].is_unique:
        raise ValueError("DOL Vehicle ID is not unique in the population file")
    frame["ZIP"] = normalize_zip(frame["Postal Code"])
    return frame


def load_ev_transactions(path=EV_TRANSACTIONS_PATH, nrows=None):
    """Load the title/registration transaction file, one row per event.

    Only the columns needed for the research questions are read; the file is
    about 950 MB and carries thirty-three columns.
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

    The file stacks one row per ZIP and AGI bracket.  Rows for the state
    total (``00000``) and the small-ZIP bucket (``99999``) are dropped.
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

    Returns a frame with ``ZIP``, ``RETURNS``, ``TOTAL_AGI`` and ``AVG_AGI``,
    keeping only ZIPs with at least ``min_returns`` returns.  ``A00100`` is
    reported in thousands of dollars by the IRS.
    """
    grouped = irs_frame.groupby("ZIP", as_index=False).agg(
        RETURNS=("N1", "sum"),
        TOTAL_AGI=("A00100", "sum"),
    )
    grouped = grouped[grouped["RETURNS"] >= min_returns].copy()
    grouped["AVG_AGI"] = grouped["TOTAL_AGI"] / grouped["RETURNS"]
    return grouped.reset_index(drop=True)


def add_income_quartile(profile):
    """Assign return-weighted income quartiles, 1 = lowest average income.

    ZIPs are sorted by ``AVG_AGI`` and each is placed by the share of all
    returns that lie below the middle of its own returns.  A ZIP whose
    midpoint falls in the first quarter of returns is in quartile 1, and so
    on, so each quartile holds a comparable number of tax filers rather than
    a comparable number of ZIP codes.  That matters because ZIP sizes differ
    by two orders of magnitude.
    """
    result = profile.sort_values("AVG_AGI").copy()
    midpoint = result["RETURNS"].cumsum() - result["RETURNS"] / 2
    position = midpoint / result["RETURNS"].sum()
    quartile = (position * 4).astype("int64") + 1
    result["INCOME_QUARTILE"] = quartile.where(quartile <= 4, 4)
    return result.sort_index()


def zip_ev_counts(pop_frame):
    """Aggregate the population file to one row per ZIP.

    Vehicles are deduplicated on ``DOL Vehicle ID`` before counting:
    ``VIN (1-10)`` is a ten-character prefix shared by different vehicles, so
    it cannot serve as a key, and counting rows would let a duplicated record
    push ``BEV_COUNT`` above ``EV_COUNT``.
    """
    valid = pop_frame.dropna(subset=["ZIP"])
    deduped = valid.drop_duplicates(subset=["ZIP", "DOL Vehicle ID"]).copy()
    deduped["IS_BEV"] = deduped["Electric Vehicle Type"] == BEV
    grouped = deduped.groupby("ZIP", as_index=False).agg(
        EV_COUNT=("DOL Vehicle ID", "nunique"),
        BEV_COUNT=("IS_BEV", "sum"),
    )
    grouped["BEV_SHARE"] = grouped["BEV_COUNT"] / grouped["EV_COUNT"]
    return grouped


def add_date_columns(tx_frame):
    """Return a copy of ``tx_frame`` with its date split into numbers.

    ``Transaction Date`` is text such as ``"October 26 2026"``.  The copy
    gains ``TX_YEAR`` and ``TX_MONTH`` plus ``TX_ORDER``, the date written as
    the integer YYYYMMDD, so sorting by ``TX_ORDER`` sorts by date.
    """
    result = tx_frame.copy()
    month_numbers = {}
    for index in range(len(MONTH_NAMES)):
        month_numbers[MONTH_NAMES[index]] = index + 1
    parts = result["Transaction Date"].str.split(" ", expand=True)
    result["TX_MONTH"] = parts[0].map(month_numbers)
    result["TX_YEAR"] = parts[2].astype(int)
    day = parts[1].astype(int)
    result["TX_ORDER"] = (
        result["TX_YEAR"] * 10000 + result["TX_MONTH"] * 100 + day
    )
    return result


def acquisitions(tx_frame):
    """Return only the title events, i.e. changes of ownership."""
    return tx_frame[tx_frame["Transaction Type"].isin(ACQUISITION_TYPES)]


def zip_condition_counts(tx_frame, acquisitions_only=True):
    """Count new versus used vehicles per ZIP.

    By default only title events are counted, because nearly half of all
    rows are registration renewals of vehicles already on the road, which
    say nothing about whether a vehicle reached its owner new or used.
    """
    if acquisitions_only:
        tx_frame = acquisitions(tx_frame)
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


def new_titles_by_county(tx_frame):
    """Count new-vehicle original titles per year and WA county (RQ3).

    Returns a Year-by-County table of counts, zero-filled.  Only Washington
    addresses are kept so out-of-state counties cannot enter the table.
    """
    mask = (
        (tx_frame["Transaction Type"] == NEW_TITLE_TYPE)
        & (tx_frame["New or Used Vehicle"] == "New")
        & (tx_frame["State"] == "WA")
    )
    return (
        tx_frame[mask]
        .groupby(["Year", "County"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )


def used_sales(tx_frame, min_price=MIN_SALE_PRICE, max_price=MAX_SALE_PRICE):
    """Return the used sales usable for RQ4, with ``ABOVE_THRESHOLD`` added.

    A row is kept when it is a used vehicle with a market price inside
    ``[min_price, max_price]`` and a researched range.  DOL records ``0`` for
    a range it has not researched, so zero means unknown, not short range.
    """
    mask = (
        (tx_frame["New or Used Vehicle"] == "Used")
        & tx_frame["Sale Price"].between(min_price, max_price)
        & (tx_frame["Electric Range"] > 0)
    )
    result = tx_frame[mask].copy()
    result["ABOVE_THRESHOLD"] = result["Electric Range"] >= HB2042_RANGE_MILES
    return result


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
