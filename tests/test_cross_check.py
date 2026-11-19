"""Cross-check the pipeline against the raw files by an independent route.

These tests re-count the per-ZIP aggregates with the standard-library
``csv`` module and plain dictionaries instead of pandas, so a bug in a
pandas call (a wrong ``groupby`` key, a dtype that drops leading zeros)
cannot hide by being repeated inside the check.  They then recompute two
headline results of the report from those raw counts and compare them with
``notes/eda_stats.json``.

The tests read the real downloads, so they do nothing when ``data/`` is
absent and take roughly half a minute on the full files.  Run them from the
project root, as the README describes.
"""

import csv
import json
import os

import pandas as pd
import pytest

import data

STATS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "notes", "eda_stats.json"
)
RAW_PATHS = [
    data.EV_POPULATION_PATH,
    data.EV_TRANSACTIONS_PATH,
    data.IRS_INCOME_PATH,
]


def have_raw_data():
    """Return True when all three raw CSV files have been downloaded."""
    for path in RAW_PATHS:
        if not os.path.exists(path):
            return False
    return True


def plain_zip(text):
    """Normalise a ZIP without pandas, following the documented rules."""
    text = text.strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = ""
    for character in text:
        if character.isdigit():
            digits += character
    if digits == "":
        return None
    digits = digits.zfill(5)
    if len(digits) != 5 or digits in data.PSEUDO_ZIPS:
        return None
    return digits


def median(values):
    """Return the median of a list of numbers."""
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def reported(section):
    """Return one section of the statistics the report quotes."""
    with open(STATS_PATH) as handle:
        return json.load(handle)[section]


def raw_ev_counts():
    """Map ZIP -> (distinct vehicles, BEVs), read straight from D1."""
    counts = {}
    seen = set()
    with open(data.EV_POPULATION_PATH, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        zip_at = header.index("Postal Code")
        id_at = header.index("DOL Vehicle ID")
        type_at = header.index("Electric Vehicle Type")
        for row in reader:
            zip_code = plain_zip(row[zip_at])
            key = (zip_code, row[id_at])
            if zip_code is None or key in seen:
                continue
            seen.add(key)
            if zip_code not in counts:
                counts[zip_code] = [0, 0]
            counts[zip_code][0] += 1
            if row[type_at] == data.BEV:
                counts[zip_code][1] += 1
    result = {}
    for zip_code in counts:
        result[zip_code] = (counts[zip_code][0], counts[zip_code][1])
    return result


def raw_income():
    """Map WA ZIP -> (returns, total AGI), read straight from D3."""
    totals = {}
    with open(data.IRS_INCOME_PATH, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        state_at = header.index("STATE")
        zip_at = header.index("zipcode")
        returns_at = header.index("N1")
        agi_at = header.index("A00100")
        for row in reader:
            zip_code = plain_zip(row[zip_at])
            if row[state_at] != "WA" or zip_code is None:
                continue
            if zip_code not in totals:
                totals[zip_code] = [0.0, 0.0]
            totals[zip_code][0] += float(row[returns_at])
            totals[zip_code][1] += float(row[agi_at])
    result = {}
    for zip_code in totals:
        if totals[zip_code][0] >= data.MIN_RETURNS:
            result[zip_code] = (totals[zip_code][0], totals[zip_code][1])
    return result


def raw_acquisitions():
    """Map ZIP -> (new, used) title events, read straight from D2."""
    counts = {}
    with open(data.EV_TRANSACTIONS_PATH, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        type_at = header.index("Transaction Type")
        condition_at = header.index("New or Used Vehicle")
        zip_at = header.index("Postal Code")
        for row in reader:
            zip_code = plain_zip(row[zip_at])
            if row[type_at] not in data.ACQUISITION_TYPES:
                continue
            if zip_code is None:
                continue
            if zip_code not in counts:
                counts[zip_code] = [0, 0]
            if row[condition_at] == "New":
                counts[zip_code][0] += 1
            else:
                counts[zip_code][1] += 1
    result = {}
    for zip_code in counts:
        result[zip_code] = (counts[zip_code][0], counts[zip_code][1])
    return result


def raw_quartiles(income):
    """Map ZIP -> (income quartile, returns) for the raw IRS profile."""
    rows = []
    for zip_code in income:
        returns, agi = income[zip_code]
        rows.append({"ZIP": zip_code, "RETURNS": returns,
                     "AVG_AGI": agi / returns})
    quartiled = data.add_income_quartile(pd.DataFrame(rows))
    result = {}
    for i in quartiled.index:
        result[quartiled.loc[i, "ZIP"]] = (
            quartiled.loc[i, "INCOME_QUARTILE"],
            quartiled.loc[i, "RETURNS"],
        )
    return result


def test_loaders_read_a_small_sample():
    if not have_raw_data():
        return
    population = data.load_ev_population(nrows=1000)
    transactions = data.load_ev_transactions(nrows=1000)
    assert len(population) == 1000 and len(transactions) == 1000
    for column in data.POP_COLUMNS:
        assert column in population.columns
    for column in data.TX_COLUMNS:
        assert column in transactions.columns
    zips = pd.concat([population["ZIP"], transactions["ZIP"]]).dropna()
    assert (zips.str.len() == 5).all()
    assert zips.str.isdigit().all()


def test_rq1_counts_and_medians_match_raw_files():
    if not have_raw_data():
        return
    ev_counts = raw_ev_counts()
    income = raw_income()

    pipeline = data.zip_ev_counts(data.load_ev_population())
    got = {}
    for i in pipeline.index:
        got[pipeline.loc[i, "ZIP"]] = (pipeline.loc[i, "EV_COUNT"],
                                       pipeline.loc[i, "BEV_COUNT"])
    assert got == ev_counts

    profile = data.income_profile(data.load_irs_zip_income())
    assert len(profile) == len(income)
    for i in profile.index:
        zip_code = profile.loc[i, "ZIP"]
        assert profile.loc[i, "RETURNS"] == pytest.approx(income[zip_code][0])
        assert profile.loc[i, "TOTAL_AGI"] == pytest.approx(
            income[zip_code][1]
        )

    densities = {1: [], 2: [], 3: [], 4: []}
    quartiles = raw_quartiles(income)
    for zip_code in quartiles:
        quartile, returns = quartiles[zip_code]
        if zip_code in ev_counts:
            densities[quartile].append(ev_counts[zip_code][0] / returns * 1000)
    medians = reported("join_d1_d3")["median_ev_per_1k_by_quartile"]
    for quartile in [1, 2, 3, 4]:
        assert median(densities[quartile]) == pytest.approx(
            medians[str(quartile)], abs=0.01
        )


def test_rq2_counts_and_shares_match_raw_files():
    if not have_raw_data():
        return
    acquisitions = raw_acquisitions()

    pipeline = data.zip_condition_counts(data.load_ev_transactions())
    got = {}
    for i in pipeline.index:
        got[pipeline.loc[i, "ZIP"]] = (pipeline.loc[i, "New"],
                                       pipeline.loc[i, "Used"])
    assert got == acquisitions

    totals = {1: [0, 0], 2: [0, 0], 3: [0, 0], 4: [0, 0]}
    quartiles = raw_quartiles(raw_income())
    for zip_code in acquisitions:
        if zip_code in quartiles:
            quartile = quartiles[zip_code][0]
            totals[quartile][0] += acquisitions[zip_code][0]
            totals[quartile][1] += acquisitions[zip_code][1]
    shares = reported("join_d2_d3")["used_share_by_quartile"]
    for quartile in [1, 2, 3, 4]:
        new, used = totals[quartile]
        assert used / (new + used) == pytest.approx(
            shares[str(quartile)], abs=1e-4
        )
