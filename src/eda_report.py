"""Produce every number and figure the EDA report needs.

Running this module writes figures to ``figures/`` and a JSON summary to
``notes/eda_stats.json``.  Every number the report quotes is read from that
JSON file, so the prose cannot drift away from what the code computed.

Usage::

    MPLCONFIGDIR=.mplcache python src/eda_report.py
"""

import json
import os

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

import data

matplotlib.use("Agg")

FIG_DIR = "figures"
NOTE_DIR = "notes"

QUARTILES = [1, 2, 3, 4]
QUARTILE_LABELS = ["Q1 (lowest)", "Q2", "Q3", "Q4 (highest)"]

# Categorical colours, always assigned in this order.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
NEUTRAL = "#a3a29c"
INK = "#52514e"
GRID = "#e4e3df"

CAFV = "Clean Alternative Fuel Vehicle (CAFV) Eligibility"
FLAG = "Meets 2019 HB 2042 Electric Range Requirement"
TYPE_ORDER = [
    "Original Title",
    "Transfer Title",
    "Original Registration",
    "Registration at time of Transfer",
    "Registration Renewal",
]

# Every Washington ZIP code starts with 980 to 994.
WA_ZIP3_LOW = 980
WA_ZIP3_HIGH = 994

# Odometer readings outside this band are entry errors, not mileage.
ODOMETER_MIN = 1
ODOMETER_MAX = 500000

# Tick positions for log-scaled income axes and for year axes.
INCOME_TICKS = [50, 100, 200, 500, 1000]
YEAR_TICKS = [2012, 2016, 2020, 2024, 2028]

# Figures are printed two to a row, so each is drawn at that printed size.
FIGSIZE = (4.4, 2.5)


def seven_number(series):
    """Return the seven-number summary of a quantitative variable."""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    summary = clean.describe()
    return {
        "n": int(summary["count"]),
        "mean": float(summary["mean"]),
        "std": float(summary["std"]),
        "min": float(summary["min"]),
        "q1": float(summary["25%"]),
        "median": float(summary["50%"]),
        "q3": float(summary["75%"]),
        "max": float(summary["max"]),
    }


def missing_report(frame, name):
    """Report missingness per column as counts and percentages."""
    counts = frame.isna().sum()
    total_cells = frame.shape[0] * frame.shape[1]
    by_column = {}
    for column in frame.columns:
        if counts[column] > 0:
            by_column[column] = {
                "missing": int(counts[column]),
                "pct": round(100 * float(counts[column]) / len(frame), 3),
            }
    return {
        "dataset": name,
        "rows": int(frame.shape[0]),
        "columns": int(frame.shape[1]),
        "cells_missing": int(counts.sum()),
        "cells_total": int(total_cells),
        "pct_missing": round(100 * float(counts.sum()) / total_cells, 3),
        "by_column": by_column,
    }


def series_to_dict(series, digits=None):
    """Turn a Series into a ``{label: number}`` dict for the JSON file.

    With ``digits`` left as ``None`` the values are whole counts; otherwise
    they are rounded to that many decimal places.
    """
    result = {}
    for label in series.index:
        if digits is None:
            result[str(label)] = int(series[label])
        else:
            result[str(label)] = round(float(series[label]), digits)
    return result


def table_to_dict(table):
    """Turn a table of counts into a nested ``{row: {column: count}}``."""
    result = {}
    for row in table.index:
        result[str(row)] = series_to_dict(table.loc[row])
    return result


def value_counts(frame, column, limit=None):
    """Return the values of a categorical column with their counts.

    Missing values are counted under the label ``"(missing)"`` whether pandas
    holds them as ``None`` or ``NaN``.
    """
    column_values = frame[column].astype("object")
    labelled = column_values.where(column_values.notna(), "(missing)")
    counts = labelled.value_counts()
    if limit is not None:
        counts = counts.head(limit)
    return series_to_dict(counts)


def count_table(frame, row_column, column_column):
    """Count the rows of ``frame`` for every pair of values in two columns."""
    return (
        frame.groupby([row_column, column_column])
        .size()
        .unstack(fill_value=0)
    )


def chi_square(table):
    """Run a chi-square test of independence and add Cramér's V."""
    values = np.array(table, dtype=float)
    chi2, p_value, dof, expected = stats.chi2_contingency(values)
    smaller_side = min(values.shape) - 1
    return {
        "chi2": round(float(chi2), 2),
        "p": float(p_value),
        "dof": int(dof),
        "min_expected": round(float(expected.min()), 1),
        "cramers_v": round(
            float(np.sqrt(chi2 / (values.sum() * smaller_side))), 4
        ),
    }


def is_wa_zip(zips):
    """Return a boolean Series marking Washington ZIP codes."""
    return zips.str[:3].astype(int).between(WA_ZIP3_LOW, WA_ZIP3_HIGH)


def check_unique(frame, column):
    """Raise ``ValueError`` unless every value of ``column`` is distinct.

    Called on the "one" side of each merge, so a duplicated key can never
    silently copy rows.
    """
    if not frame[column].is_unique:
        raise ValueError(f"{column} is not unique; the merge would add rows")


def file_columns(path):
    """Return the number of columns in a CSV file's header."""
    return int(pd.read_csv(path, nrows=0).shape[1])


def share(numerator, denominator, digits=4):
    """Return ``numerator / denominator`` as a rounded float."""
    return round(float(numerator) / float(denominator), digits)


def count_true(values):
    """Return how many items of a list are True."""
    total = 0
    for value in values:
        if value:
            total += 1
    return total


def style_axes(ax, title):
    """Give every chart the same title size and a quiet frame and grid."""
    ax.set_title(title, fontsize=10.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def label_ticks(ax, axis, style):
    """Relabel the visible ticks of one axis.

    ``axis`` is ``"x"`` or ``"y"``; ``style`` is ``"comma"`` (12,345),
    ``"percent"`` (45%) or ``"thousands"`` ($50k).  Call it after the plot
    and its limits are final, because it fixes the tick positions.
    """
    if axis == "x":
        low, high = ax.get_xlim()
        ticks = ax.get_xticks()
    else:
        low, high = ax.get_ylim()
        ticks = ax.get_yticks()
    kept = []
    labels = []
    for tick in ticks:
        if low <= tick <= high:
            kept.append(tick)
            if style == "percent":
                labels.append(f"{tick:.0%}")
            elif style == "thousands":
                labels.append(f"${tick / 1000:,.0f}k")
            else:
                labels.append(f"{tick:,.0f}")
    if axis == "x":
        ax.set_xticks(kept)
        ax.set_xticklabels(labels)
    else:
        ax.set_yticks(kept)
        ax.set_yticklabels(labels)


def save_figure(fig, name):
    """Save a figure at a print-friendly resolution and close it."""
    path = os.path.join(FIG_DIR, name)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def quartile_axis(ax):
    """Label the x-axis with the four income quartiles."""
    ax.set_xticks(QUARTILES)
    ax.set_xticklabels(QUARTILE_LABELS)
    ax.set_xlabel("Return-weighted income quartile")


def quartile_table(merged):
    """Sum new and used counts per income quartile."""
    return (
        merged.groupby("INCOME_QUARTILE")[["New", "Used"]]
        .sum()
        .reindex(QUARTILES)
    )


def used_share_by_quartile(table):
    """Return the used share of each quartile row of a New/Used table."""
    result = {}
    for q in QUARTILES:
        result[str(q)] = share(table.loc[q, "Used"], table.loc[q].sum())
    return result


def profile_population(pop):
    """Summarise D1 and draw Figures 1-2."""
    researched = pop[pop["Electric Range"] > 0]
    is_bev = pop["Electric Vehicle Type"] == data.BEV
    by_year = pop["Model Year"].value_counts().sort_index()
    range_is_zero = pop[CAFV].to_frame()
    range_is_zero["RANGE_ZERO"] = pop["Electric Range"] == 0
    result = {
        "file_columns": file_columns(data.EV_POPULATION_PATH),
        "missing": missing_report(pop, "ev_population"),
        "range_summary": seven_number(pop["Electric Range"]),
        "range_summary_researched": seven_number(researched["Electric Range"]),
        "range_zero_rows": int((pop["Electric Range"] == 0).sum()),
        "range_zero_share_of_bev": share(
            (pop.loc[is_bev, "Electric Range"] == 0).sum(), is_bev.sum()
        ),
        "cafv_by_range_zero": table_to_dict(
            count_table(range_is_zero, CAFV, "RANGE_ZERO")
        ),
        "model_year_summary": seven_number(pop["Model Year"]),
        "model_year_counts": series_to_dict(by_year),
        "model_years_before_2010": int(by_year[by_year.index < 2010].sum()),
        "type_counts": value_counts(pop, "Electric Vehicle Type"),
        "cafv_counts": value_counts(pop, CAFV),
        "state_counts": value_counts(pop, "State", limit=5),
        "out_of_state_rows": int((pop["State"] != "WA").sum()),
        "out_of_state_codes": int(
            pop.loc[pop["State"] != "WA", "State"].nunique()
        ),
        "make_counts_top10": value_counts(pop, "Make", limit=10),
        "zip_missing": int(pop["ZIP"].isna().sum()),
    }

    shown = by_year[by_year.index >= 2010]
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.bar(shown.index, shown.values, color=SERIES[0], width=0.8)
    style_axes(ax, "Registered EVs by model year (2010 onward)")
    ax.set_xticks(YEAR_TICKS)
    label_ticks(ax, "y", "comma")
    ax.set_xlabel("Model year")
    ax.set_ylabel("Registered vehicles")
    save_figure(fig, "fig01_ev_by_model_year.png")

    fig, ax = plt.subplots(figsize=FIGSIZE)
    bins = np.arange(0, 360, 10)
    for label, name, colour in (
        (data.BEV, "BEV", SERIES[0]),
        (data.PHEV, "PHEV", SERIES[1]),
    ):
        values = researched.loc[
            researched["Electric Vehicle Type"] == label, "Electric Range"
        ]
        ax.hist(values, bins=bins, color=colour, alpha=0.8,
                label=f"{name} (n = {len(values):,})")
    ax.axvline(data.HB2042_RANGE_MILES, color=INK, linestyle="--",
               linewidth=1, label="30-mile HB 2042 line")
    style_axes(ax, "Electric range by powertrain (range 0 omitted)")
    label_ticks(ax, "y", "comma")
    ax.set_xlabel("Rated electric range (miles)")
    ax.set_ylabel("Vehicles")
    ax.legend(loc="upper right", fontsize=8, frameon=False)
    save_figure(fig, "fig02_ev_range_by_type.png")
    return result


def profile_transactions(tx, sales):
    """Summarise D2 and draw Figures 3-5.

    Returns the summary and a ``{year: months covered}`` dict for RQ3.
    """
    used = tx["New or Used Vehicle"] == "Used"
    priced = tx["Sale Price"] > 0
    titles = tx["Transaction Type"].isin(data.ACQUISITION_TYPES)
    months = tx.groupby("TX_YEAR")["TX_MONTH"].nunique()
    first = int(tx["TX_ORDER"].min())
    last = int(tx["TX_ORDER"].max())
    per_vehicle = tx.groupby("DOL Vehicle ID").size()
    largest = tx.loc[used, "Sale Price"].sort_values(ascending=False).head(3)
    result = {
        "file_columns": file_columns(data.EV_TRANSACTIONS_PATH),
        "missing": missing_report(
            tx[data.TX_COLUMNS + ["ZIP"]], "ev_transactions"
        ),
        "type_counts": value_counts(tx, "Transaction Type"),
        "condition_counts": value_counts(tx, "New or Used Vehicle"),
        "type_by_condition": table_to_dict(
            count_table(tx, "Transaction Type", "New or Used Vehicle")
        ),
        "renewal_share": share(
            (tx["Transaction Type"] == "Registration Renewal").sum(), len(tx)
        ),
        "year_counts": series_to_dict(tx["Year"].value_counts().sort_index()),
        "months_covered": series_to_dict(months),
        "date_first": first,
        "date_last": last,
        "range_summary": seven_number(tx["Electric Range"]),
        "model_year_summary": seven_number(tx["Model Year"]),
        "out_of_state_share": share((tx["State"] != "WA").sum(), len(tx)),
        "flag_counts": value_counts(tx, FLAG),
        "used_priced_rows": int((used & priced).sum()),
        "used_title_rows": int((used & titles).sum()),
        "used_title_priced_share": share(
            (used & titles & priced).sum(), (used & titles).sum()
        ),
        "used_price_summary_raw": seven_number(
            tx.loc[used & priced, "Sale Price"]
        ),
        "largest_prices": [int(value) for value in largest],
        "price_below_min_rows": int(
            (used & priced & (tx["Sale Price"] < data.MIN_SALE_PRICE)).sum()
        ),
        "price_above_max_rows": int(
            (used & (tx["Sale Price"] > data.MAX_SALE_PRICE)).sum()
        ),
        "per_vehicle": {
            "vehicles": int(len(per_vehicle)),
            "share_one": share((per_vehicle == 1).sum(), len(per_vehicle)),
            "share_two_or_fewer": share(
                (per_vehicle <= 2).sum(), len(per_vehicle)
            ),
            "median": float(per_vehicle.median()),
            "mean": round(float(per_vehicle.mean()), 2),
            "share_ten_plus": share(
                (per_vehicle >= 10).sum(), len(per_vehicle)
            ),
        },
    }

    table = count_table(tx, "Year", "Transaction Type")[TYPE_ORDER]
    fig, ax = plt.subplots(figsize=FIGSIZE)
    bottom = np.zeros(len(table))
    for index in range(len(TYPE_ORDER)):
        column = TYPE_ORDER[index]
        ax.bar(table.index, table[column], bottom=bottom,
               color=SERIES[index], width=0.8, edgecolor="white",
               linewidth=0.5, label=column)
        bottom = bottom + table[column].values
    last_month = data.MONTH_NAMES[(last // 100) % 100 - 1][:3]
    ax.set_ylim(0, bottom.max() * 1.12)
    ax.annotate(f"Jan-{last_month} only", (table.index.max(), bottom.max()),
                xytext=(0, 4), textcoords="offset points", ha="center",
                fontsize=8, color=INK)
    style_axes(ax, "Transactions by year and type")
    ax.set_xticks(YEAR_TICKS[:-1])
    label_ticks(ax, "y", "comma")
    ax.set_xlabel("Transaction year")
    ax.set_ylabel("Transactions")
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    save_figure(fig, "fig03_transactions_by_year_type.png")

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.hist(sales["Sale Price"], bins=np.arange(0, 255000, 5000),
            color=SERIES[2])
    median = sales["Sale Price"].median()
    ax.axvline(median, color=INK, linestyle="--", linewidth=1)
    ax.annotate(f"median ${median:,.0f}", (median, 0.92),
                xycoords=("data", "axes fraction"), xytext=(6, 0),
                textcoords="offset points", color=INK, fontsize=9)
    style_axes(ax, "Used EV sale prices in the RQ4 sample")
    label_ticks(ax, "x", "thousands")
    label_ticks(ax, "y", "comma")
    ax.set_xlabel("Sale price (USD)")
    ax.set_ylabel("Used EV sales")
    save_figure(fig, "fig04_used_price_distribution.png")

    capped = per_vehicle.copy()
    capped[capped > 10] = 10
    capped_counts = capped.value_counts().sort_index()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.bar(capped_counts.index, capped_counts.values, color=SERIES[0],
           width=0.8)
    style_axes(ax, "How many transactions each vehicle appears in")
    ax.set_xticks(list(range(1, 11)))
    ax.set_xticklabels(["1", "2", "3", "4", "5", "6", "7", "8", "9", "10+"])
    label_ticks(ax, "y", "comma")
    ax.set_xlabel("Transactions recorded for the vehicle")
    ax.set_ylabel("Vehicles")
    save_figure(fig, "fig05_transactions_per_vehicle.png")
    return result, months


def yearly_growth(counts):
    """Return year-over-year growth and its three-year trailing mean.

    ``counts`` is a Series indexed by consecutive years.  Both results are
    ``{year: rate}`` dicts; the first year has no growth and the first two
    growth years have no trailing mean.
    """
    years = list(counts.index)
    growth = {}
    for i in range(1, len(years)):
        growth[years[i]] = counts[years[i]] / counts[years[i - 1]] - 1
    growth_years = list(growth.keys())
    trailing = {}
    for i in range(2, len(growth_years)):
        window = 0
        for j in range(i - 2, i + 1):
            window += growth[growth_years[j]]
        trailing[growth_years[i]] = window / 3
    return growth, trailing


def profile_new_registrations(tx, months):
    """Summarise the RQ3 inputs (new EV titles by county) and draw Figure 6."""
    table = data.new_titles_by_county(tx)
    full_years = []
    partial_years = []
    for year in table.index:
        if months[year] == 12:
            full_years.append(int(year))
        else:
            partial_years.append(int(year))
    statewide = table.sum(axis=1)
    king_share = table["King"] / statewide
    growth, trailing = yearly_growth(statewide)
    totals = table.loc[full_years].sum().sort_values(ascending=False)
    result = {
        "counties": int(table.shape[1]),
        "full_years": full_years,
        "partial_years": partial_years,
        "new_titles_by_year": series_to_dict(statewide),
        "king_share_by_year": series_to_dict(king_share, 4),
        "statewide_growth": series_to_dict(pd.Series(growth), 4),
        "statewide_growth_3yr_mean": series_to_dict(pd.Series(trailing), 4),
        "county_totals_full_years": series_to_dict(totals),
    }

    full = [year for year in full_years if year >= 2011]
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(full, king_share.loc[full], color=SERIES[0], linewidth=2,
            marker="o", markersize=5)
    for year in partial_years:
        ax.plot(year, king_share.loc[year], marker="o", markersize=6,
                markerfacecolor="white", markeredgecolor=SERIES[0])
        ax.annotate("partial year", (year, king_share.loc[year]),
                    xytext=(0, -14), textcoords="offset points",
                    ha="center", fontsize=8, color=INK)
    ax.set_ylim(0.3, 0.8)
    style_axes(ax, "King County share of new-EV titles")
    ax.set_xticks([2011, 2014, 2017, 2020, 2023, 2026])
    label_ticks(ax, "y", "percent")
    ax.set_xlabel("Transaction year")
    ax.set_ylabel("King County share")
    save_figure(fig, "fig06_king_share_new_titles.png")
    return result


def profile_income(irs_raw):
    """Summarise D3, draw Figures 7-8, and return the quartiled profile."""
    profile = data.add_income_quartile(data.income_profile(irs_raw))
    unfiltered = data.income_profile(irs_raw, min_returns=0)
    raw = pd.read_csv(data.IRS_INCOME_PATH,
                      usecols=["STATE", "zipcode", "N1"],
                      dtype={"zipcode": "string"})
    raw = raw[raw["STATE"] == "WA"]
    codes = raw["zipcode"].str.zfill(5)
    by_quartile = profile.groupby("INCOME_QUARTILE")
    starts = by_quartile["AVG_AGI"].min()
    boundaries = [float(starts[2]), float(starts[3]), float(starts[4])]
    small = profile["RETURNS"] < 1000
    large = profile["RETURNS"] >= 10000
    rich = profile[profile["AVG_AGI"] > 600]
    zips_over_600k = []
    for i in rich.index:
        zips_over_600k.append({
            "zip": rich.loc[i, "ZIP"],
            "returns": int(rich.loc[i, "RETURNS"]),
            "avg_agi": round(float(rich.loc[i, "AVG_AGI"]), 1),
        })
    result = {
        "file_columns": file_columns(data.IRS_INCOME_PATH),
        "wa_rows_in_file": int(len(codes)),
        "pseudo_zip_rows_dropped": int(codes.isin(data.PSEUDO_ZIPS).sum()),
        "returns_in_99999_bucket": int(raw.loc[codes == "99999", "N1"].sum()),
        "spearman_returns_vs_agi": round(float(stats.spearmanr(
            profile["RETURNS"], profile["AVG_AGI"]
        )[0]), 3),
        "median_agi_small_zips": {
            "zips": int(small.sum()),
            "median": round(float(profile.loc[small, "AVG_AGI"].median()), 1),
        },
        "median_agi_large_zips": {
            "zips": int(large.sum()),
            "median": round(float(profile.loc[large, "AVG_AGI"].median()), 1),
        },
        "missing": missing_report(irs_raw, "irs_zip_income (WA rows)"),
        "agi_stub_counts": value_counts(irs_raw, "agi_stub"),
        "profile_rows": int(len(profile)),
        "zips_below_min_returns": int(len(unfiltered) - len(profile)),
        "min_returns_observed": float(unfiltered["RETURNS"].min()),
        "returns_summary": seven_number(profile["RETURNS"]),
        "avg_agi_summary": seven_number(profile["AVG_AGI"]),
        "quartile_start_agi": [round(value, 2) for value in boundaries],
        "quartile_zip_counts": series_to_dict(by_quartile.size()),
        "quartile_returns": series_to_dict(by_quartile["RETURNS"].sum()),
        "quartile_median_agi": series_to_dict(
            by_quartile["AVG_AGI"].median(), 1
        ),
        "zips_over_600k": zips_over_600k,
    }

    log_bins = []
    for i in range(50):
        log_bins.append(30 * (1300 / 30) ** (i / 49))
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.hist(profile["AVG_AGI"], bins=log_bins, color=SERIES[0])
    ax.set_xscale("log")
    ax.minorticks_off()
    for boundary in boundaries:
        ax.axvline(boundary, color=INK, linestyle="--", linewidth=1)
    ax.annotate("dashed: quartile boundaries", (0.98, 0.9),
                xycoords="axes fraction", ha="right", fontsize=8, color=INK)
    style_axes(ax, "Average AGI per return across WA ZIPs")
    ax.set_xticks(INCOME_TICKS)
    label_ticks(ax, "x", "comma")
    ax.set_xlabel("Average AGI per return (thousands USD, log)")
    ax.set_ylabel("ZIP codes")
    save_figure(fig, "fig07_income_distribution.png")

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.scatter(profile["RETURNS"], profile["AVG_AGI"], s=12, alpha=0.6,
               color=SERIES[0], edgecolors="none")
    for boundary in boundaries:
        ax.axhline(boundary, color=INK, linestyle="--", linewidth=1)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.minorticks_off()
    style_axes(ax, "ZIP size vs. average income")
    ax.set_yticks(INCOME_TICKS)
    label_ticks(ax, "x", "comma")
    label_ticks(ax, "y", "comma")
    ax.set_xlabel("Tax returns in the ZIP (log)")
    ax.set_ylabel("Avg AGI (thousands USD)")
    save_figure(fig, "fig08_returns_vs_income.png")
    return result, profile


def regional_check(merged, min_zips=10):
    """Check whether EV density clusters by three-digit ZIP region.

    A plain permutation test treats every ZIP as exchangeable.  If some
    regions hold far more high-density ZIPs than others, that assumption
    fails across regions and the RQ1 permutation must shuffle within
    regions instead.  The check is a chi-square test of region against
    "density above the statewide median", over regions with at least
    ``min_zips`` ZIPs; the Spearman correlation inside each such region is
    reported alongside.
    """
    frame = merged.copy()
    frame["REGION"] = frame["ZIP"].str[:3]
    frame["ABOVE_MEDIAN"] = (
        frame["EV_PER_1K_RETURNS"] > frame["EV_PER_1K_RETURNS"].median()
    )
    sizes = frame.groupby("REGION").size()
    tested = list(sizes[sizes >= min_zips].index)
    in_tested = frame[frame["REGION"].isin(tested)]
    above = in_tested.groupby("REGION")["ABOVE_MEDIAN"].sum()
    total = in_tested.groupby("REGION").size()
    table = pd.DataFrame({"ABOVE": above, "BELOW": total - above})
    within = {}
    for region in tested:
        group = in_tested[in_tested["REGION"] == region]
        rho = stats.spearmanr(group["AVG_AGI"], group["EV_PER_1K_RETURNS"])[0]
        within[region] = round(float(rho), 3)
    return {
        "regions": int(frame["REGION"].nunique()),
        "regions_tested": len(tested),
        "zips_in_tested_regions": int(len(in_tested)),
        "share_above_median_by_region": series_to_dict(above / total, 3),
        "test": chi_square(table),
        "within_region_rho": within,
        "within_region_rho_positive": count_true(
            [rho > 0 for rho in within.values()]
        ),
    }


def join_population_income(pop, profile):
    """Profile the D1 x D3 join (RQ1) and draw Figures 9-10."""
    evzip = data.zip_ev_counts(pop)
    check_unique(evzip, "ZIP")
    check_unique(profile, "ZIP")
    merged = evzip.merge(profile, on="ZIP", how="inner")
    merged["EV_PER_1K_RETURNS"] = merged["EV_COUNT"] / merged["RETURNS"] * 1000
    unmatched = evzip[~evzip["ZIP"].isin(profile["ZIP"])]
    unmatched_wa = is_wa_zip(unmatched["ZIP"])
    fleet = merged["EV_COUNT"] > merged["RETURNS"]
    households = merged[~fleet]
    fleet_zips = merged[fleet]
    rho = stats.spearmanr(merged["AVG_AGI"], merged["EV_PER_1K_RETURNS"])[0]
    rho_households = stats.spearmanr(
        households["AVG_AGI"], households["EV_PER_1K_RETURNS"]
    )[0]
    medians = merged.groupby("INCOME_QUARTILE")["EV_PER_1K_RETURNS"].median()
    mix = merged.groupby("INCOME_QUARTILE")[["BEV_COUNT", "EV_COUNT"]].sum()
    mix["PHEV_COUNT"] = mix["EV_COUNT"] - mix["BEV_COUNT"]
    bev_share = {}
    for q in QUARTILES:
        bev_share[str(q)] = share(mix.loc[q, "BEV_COUNT"],
                                  mix.loc[q, "EV_COUNT"])
    fleet_list = []
    for i in fleet_zips.index:
        fleet_list.append({
            "zip": fleet_zips.loc[i, "ZIP"],
            "ev_count": int(fleet_zips.loc[i, "EV_COUNT"]),
            "returns": int(fleet_zips.loc[i, "RETURNS"]),
            "avg_agi": round(float(fleet_zips.loc[i, "AVG_AGI"]), 1),
            "ev_per_1k": round(
                float(fleet_zips.loc[i, "EV_PER_1K_RETURNS"]), 1
            ),
        })
    result = {
        "ev_zips": int(len(evzip)),
        "income_zips": int(len(profile)),
        "matched_zips": int(len(merged)),
        "zip_coverage_pct": round(100 * len(merged) / len(evzip), 2),
        "unmatched_zips_wa": int(unmatched_wa.sum()),
        "unmatched_zips_other_state": int((~unmatched_wa).sum()),
        "unmatched_vehicles_wa": int(unmatched.loc[unmatched_wa,
                                                   "EV_COUNT"].sum()),
        "unmatched_vehicles_other_state": int(
            unmatched.loc[~unmatched_wa, "EV_COUNT"].sum()
        ),
        "ev_rows_matched_pct": round(
            100 * float(pop["ZIP"].isin(profile["ZIP"]).mean()), 2
        ),
        "merged_shape": [int(merged.shape[0]), int(merged.shape[1])],
        "merged_missing_cells": int(merged.isna().sum().sum()),
        "ev_count_summary": seven_number(merged["EV_COUNT"]),
        "ev_per_1k_summary": seven_number(merged["EV_PER_1K_RETURNS"]),
        "avg_agi_summary": seven_number(merged["AVG_AGI"]),
        "bev_share_summary": seven_number(merged["BEV_SHARE"]),
        "spearman_rho": round(float(rho), 4),
        "spearman_rho_excluding_fleet_zips": round(float(rho_households), 4),
        "fleet_zips": fleet_list,
        "median_ev_per_1k_by_quartile": series_to_dict(medians, 2),
        "regional": regional_check(merged),
        "bev_share_by_quartile": bev_share,
        "bev_mix_test": chi_square(mix[["BEV_COUNT", "PHEV_COUNT"]]),
    }

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.scatter(households["AVG_AGI"], households["EV_PER_1K_RETURNS"], s=12,
               alpha=0.6, color=SERIES[0], edgecolors="none",
               label="ZIP codes")
    ax.scatter(fleet_zips["AVG_AGI"], fleet_zips["EV_PER_1K_RETURNS"], s=36,
               color=SERIES[1], edgecolors="white",
               label="More EVs than tax returns (fleet)")
    for i in fleet_zips.index:
        ax.annotate(fleet_zips.loc[i, "ZIP"],
                    (fleet_zips.loc[i, "AVG_AGI"],
                     fleet_zips.loc[i, "EV_PER_1K_RETURNS"]),
                    xytext=(6, -3), textcoords="offset points", fontsize=8,
                    color=INK)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.minorticks_off()
    style_axes(ax, "EV density against ZIP-level income")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_xticks(INCOME_TICKS)
    label_ticks(ax, "x", "comma")
    label_ticks(ax, "y", "comma")
    ax.set_xlabel("Average AGI per return (thousands USD, log)")
    ax.set_ylabel("EVs per 1,000 returns (log)")
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    save_figure(fig, "fig09_ev_density_vs_income.png")

    fig, ax = plt.subplots(figsize=FIGSIZE)
    values = []
    for q in QUARTILES:
        values.append(float(medians[q]))
    ax.bar(QUARTILES, values, color=SERIES[0], width=0.6)
    for index in range(len(QUARTILES)):
        ax.annotate(f"{values[index]:.1f}", (QUARTILES[index], values[index]),
                    xytext=(0, 3), textcoords="offset points", ha="center",
                    fontsize=9, color=INK)
    ax.set_ylim(0, max(values) * 1.15)
    style_axes(ax, "Median EV density by income quartile")
    quartile_axis(ax)
    ax.set_ylabel("Median EVs per 1,000 returns")
    save_figure(fig, "fig10_ev_density_by_quartile.png")
    return result


def merge_with_income(counts, profile):
    """Merge per-ZIP new/used counts with the income profile, one-to-one."""
    check_unique(counts, "ZIP")
    check_unique(profile, "ZIP")
    return counts.merge(profile, on="ZIP", how="inner")


def join_transactions_income(tx, profile):
    """Profile the D2 x D3 join (RQ2) and draw Figures 11-12."""
    acquired = data.acquisitions(tx)
    repeat_used = (
        acquired[acquired["New or Used Vehicle"] == "Used"]
        .groupby("DOL Vehicle ID").size()
    )
    first_only = acquired.drop_duplicates(
        subset=["DOL Vehicle ID", "New or Used Vehicle"]
    )
    counts = data.zip_condition_counts(tx)
    merged = merge_with_income(counts, profile)
    all_events = data.zip_condition_counts(tx, acquisitions_only=False)
    one_per_vehicle = data.zip_condition_counts(first_only)
    tables = {
        "acquisitions": quartile_table(merged),
        "all_events": quartile_table(merge_with_income(all_events, profile)),
        "one_per_vehicle": quartile_table(
            merge_with_income(one_per_vehicle, profile)
        ),
    }
    table = tables["acquisitions"]
    rho = stats.spearmanr(merged["AVG_AGI"], merged["USED_SHARE"])[0]
    counts_by_quartile = {}
    for q in QUARTILES:
        counts_by_quartile[str(q)] = {
            "New": int(table.loc[q, "New"]),
            "Used": int(table.loc[q, "Used"]),
        }
    result = {
        "acquisition_rows": int(len(acquired)),
        "acquisition_vehicles": int(acquired["DOL Vehicle ID"].nunique()),
        "vehicles_with_repeat_used_acquisition": int((repeat_used > 1).sum()),
        "acquisition_zips": int(len(counts)),
        "matched_zips": int(len(merged)),
        "zip_coverage_pct": round(100 * len(merged) / len(counts), 2),
        "acquisition_rows_matched_pct": round(
            100 * float(acquired["ZIP"].isin(profile["ZIP"]).mean()), 2
        ),
        "merged_shape": [int(merged.shape[0]), int(merged.shape[1])],
        "merged_missing_cells": int(merged.isna().sum().sum()),
        "acquisitions_per_zip_summary": seven_number(
            merged["New"] + merged["Used"]
        ),
        "used_share_zip_summary": seven_number(merged["USED_SHARE"]),
        "zip_spearman_used_share_vs_income": round(float(rho), 4),
        "counts_by_quartile": counts_by_quartile,
        "used_share_by_quartile": used_share_by_quartile(table),
        "test": chi_square(table),
    }
    for name in ["all_events", "one_per_vehicle"]:
        result[name] = {
            "used_share_by_quartile": used_share_by_quartile(tables[name]),
            "test": chi_square(tables[name]),
        }

    fig, ax = plt.subplots(figsize=FIGSIZE)
    width = 0.36
    for offset, name, colour, label in (
        (-width / 2, "acquisitions", SERIES[1], "Acquisitions only"),
        (width / 2, "all_events", NEUTRAL, "All events incl. renewals"),
    ):
        positions = []
        shares = []
        for q in QUARTILES:
            positions.append(q + offset)
            shares.append(
                tables[name].loc[q, "Used"] / tables[name].loc[q].sum()
            )
        ax.bar(positions, shares, width=width, color=colour, label=label)
        for index in range(len(positions)):
            ax.annotate(f"{shares[index]:.0%}",
                        (positions[index], shares[index]), xytext=(0, 3),
                        textcoords="offset points", ha="center", fontsize=8,
                        color=INK)
    ax.set_ylim(0, 1.18)
    style_axes(ax, "Used-vehicle share by income quartile")
    quartile_axis(ax)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    label_ticks(ax, "y", "percent")
    ax.set_ylabel("Share that are used vehicles")
    ax.legend(loc="upper left", fontsize=8, ncol=2, frameon=False)
    save_figure(fig, "fig11_used_share_by_quartile.png")

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.bar(QUARTILES, table["New"], color=SERIES[0], width=0.6,
           edgecolor="white", linewidth=0.5, label="New")
    ax.bar(QUARTILES, table["Used"], bottom=table["New"], color=SERIES[1],
           width=0.6, edgecolor="white", linewidth=0.5, label="Used")
    style_axes(ax, "New and used EV acquisitions by income quartile")
    quartile_axis(ax)
    label_ticks(ax, "y", "comma")
    ax.set_ylabel("Title events (acquisitions)")
    ax.legend(loc="upper left", frameon=False)
    save_figure(fig, "fig12_acquisitions_by_quartile.png")
    return result


def range_group(ranges):
    """Label each electric range as unknown (0), 1-29 miles, or 30+ miles.

    A missing range gets no label, so it is left out of the counts.
    """
    groups = pd.Series("30+ miles", index=ranges.index)
    groups[ranges < data.HB2042_RANGE_MILES] = "1-29 miles"
    groups[ranges == 0] = "0 (unknown)"
    return groups.where(ranges.notna())


def join_transactions_population(tx, pop, sales):
    """Profile the D2 x D1 join (RQ4) and draw Figures 13-14."""
    d1 = pop[["DOL Vehicle ID", CAFV, "Electric Range"]].rename(
        columns={"Electric Range": "D1_RANGE"}
    )
    d1["IN_D1"] = True
    check_unique(d1, "DOL Vehicle ID")
    pop_ids = set(pop["DOL Vehicle ID"])
    tx_ids = set(tx["DOL Vehicle ID"].dropna())
    used_in_band = tx[
        (tx["New or Used Vehicle"] == "Used")
        & tx["Sale Price"].between(data.MIN_SALE_PRICE, data.MAX_SALE_PRICE)
    ]
    labelled = used_in_band.merge(d1, on="DOL Vehicle ID", how="left")
    labelled["RANGE_GROUP"] = range_group(labelled["Electric Range"])
    labelled[CAFV] = labelled[CAFV].fillna("Not in current fleet")
    label_counts = count_table(labelled, "RANGE_GROUP", CAFV)
    joined = sales.merge(d1, on="DOL Vehicle ID", how="left")
    joined["IN_D1"] = joined["IN_D1"].fillna(False).astype(bool)
    matched = joined[joined["IN_D1"]]
    by_side = joined.groupby("ABOVE_THRESHOLD")["IN_D1"].mean()
    result = {
        "pop_vehicle_ids": len(pop_ids),
        "tx_vehicle_ids": len(tx_ids),
        "matched_ids": len(pop_ids & tx_ids),
        "pop_ids_in_tx_pct": round(100 * len(pop_ids & tx_ids)
                                   / len(pop_ids), 2),
        "tx_ids_in_pop_pct": round(100 * len(pop_ids & tx_ids)
                                   / len(tx_ids), 2),
        "range_group_by_d1_label": table_to_dict(label_counts),
        "rq4_joined_shape": [int(joined.shape[0]), int(joined.shape[1])],
        "rq4_joined_missing_cells": int(joined.isna().sum().sum()),
        "rq4_matched_rows": int(len(matched)),
        "rq4_matched_pct": round(100 * len(matched) / len(joined), 2),
        "rq4_range_agreement": share(
            (matched["Electric Range"] == matched["D1_RANGE"]).sum(),
            len(matched),
        ),
        "still_registered_share_by_side": {
            "below_30": round(float(by_side[False]), 4),
            "above_30": round(float(by_side[True]), 4),
        },
    }

    order = [
        ("Clean Alternative Fuel Vehicle Eligible", "D1: eligible",
         SERIES[0]),
        ("Not eligible due to low battery range", "D1: range too low",
         SERIES[1]),
        ("Eligibility unknown as battery range has not been researched",
         "D1: range not researched", SERIES[2]),
        ("Not in current fleet", "Not in D1 (left the fleet)", NEUTRAL),
    ]
    row_totals = label_counts.sum(axis=1)
    fig, ax = plt.subplots(figsize=(FIGSIZE[0], FIGSIZE[1] + 0.4))
    left = np.zeros(len(label_counts))
    rows = list(range(len(label_counts)))
    for column, label, colour in order:
        if column in label_counts.columns:
            values = (label_counts[column] / row_totals).values
        else:
            values = np.zeros(len(label_counts))
        ax.barh(rows, values, left=left, color=colour, height=0.6,
                edgecolor="white", linewidth=0.5, label=label)
        left = left + values
    style_axes(ax, "D2 range groups against D1's eligibility label")
    ax.grid(False)
    ax.set_yticks(rows)
    ax.set_yticklabels(list(label_counts.index))
    ax.invert_yaxis()
    label_ticks(ax, "x", "percent")
    ax.set_xlabel("Share of used sales in the D2 range group")
    ax.set_ylabel("Range recorded in D2")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=2,
              fontsize=8, frameon=False)
    save_figure(fig, "fig13_range_vs_d1_label.png")

    joined["RANGE_BIN"] = (joined["Electric Range"] // 10) * 10
    prices = joined.groupby("RANGE_BIN")["Sale Price"]
    binned = pd.DataFrame({
        "median": prices.median(),
        "count": prices.size(),
        "q1": prices.quantile(0.25),
        "q3": prices.quantile(0.75),
    })
    binned = binned[binned["count"] >= 50]
    by_bin = {}
    for start in binned.index:
        by_bin[str(int(start))] = {
            "median": float(binned.loc[start, "median"]),
            "n": int(binned.loc[start, "count"]),
        }
    result["median_price_by_range_bin"] = by_bin
    fig, ax = plt.subplots(figsize=FIGSIZE)
    for below, label, colour in ((True, "Below 30 miles", SERIES[1]),
                                 (False, "30 miles or more", SERIES[0])):
        part = binned[(binned.index < data.HB2042_RANGE_MILES) == below]
        ax.errorbar(part.index + 5, part["median"],
                    yerr=[part["median"] - part["q1"],
                          part["q3"] - part["median"]],
                    fmt="o", color=colour, markersize=5, elinewidth=1,
                    capsize=0, label=label)
    ax.axvline(data.HB2042_RANGE_MILES, color=INK, linestyle="--",
               linewidth=1)
    style_axes(ax, "Used EV sale price by electric range")
    label_ticks(ax, "y", "thousands")
    ax.set_xlabel("Electric range, 10-mile bins (50+ sales each)")
    ax.set_ylabel("Sale price (median, IQR)")
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    save_figure(fig, "fig14_price_by_range.png")
    return result


def describe_rq4_sample(tx, sales):
    """Summarise the used-sale sample that RQ4 will analyse."""
    used = tx["New or Used Vehicle"] == "Used"
    in_band = tx["Sale Price"].between(data.MIN_SALE_PRICE,
                                       data.MAX_SALE_PRICE)
    below = sales[~sales["ABOVE_THRESHOLD"]]
    above = sales[sales["ABOVE_THRESHOLD"]]
    return {
        "rows": int(len(sales)),
        "vehicles": int(sales["DOL Vehicle ID"].nunique()),
        "below_rows": int(len(below)),
        "above_rows": int(len(above)),
        "excluded_range_zero_rows": int(
            (used & in_band & (tx["Electric Range"] == 0)).sum()
        ),
        "type_counts": value_counts(sales, "Transaction Type"),
        "price_summary": seven_number(sales["Sale Price"]),
        "price_summary_below": seven_number(below["Sale Price"]),
        "price_summary_above": seven_number(above["Sale Price"]),
        "range_summary": seven_number(sales["Electric Range"]),
        "model_year_summary": seven_number(sales["Model Year"]),
        "odometer_summary": seven_number(sales["Odometer Reading"]),
        "odometer_usable_rows": int(
            sales["Odometer Reading"].between(ODOMETER_MIN,
                                              ODOMETER_MAX).sum()
        ),
    }


def assumption_checks(tx, sales):
    """Check the assumptions behind the planned RQ4 tests and the flag."""
    flag = tx[FLAG].astype(str) == "True"
    researched = tx["Electric Range"] > 0
    rule = tx["Electric Range"] >= data.HB2042_RANGE_MILES
    mismatch = researched & (flag != rule)
    zero = tx["Electric Range"] == 0
    raw_prices = tx.loc[
        (tx["New or Used Vehicle"] == "Used") & (tx["Sale Price"] > 0),
        "Sale Price",
    ]
    latest = sales.sort_values("TX_ORDER").drop_duplicates(
        subset="DOL Vehicle ID", keep="last"
    )
    log_price = np.log(latest["Sale Price"])
    above = latest["ABOVE_THRESHOLD"]
    mismatch_ranges = []
    for value in tx.loc[mismatch, "Electric Range"].unique():
        mismatch_ranges.append(int(value))
    return {
        "flag_mismatch_researched_rows": int(mismatch.sum()),
        "flag_mismatch_ranges": sorted(mismatch_ranges),
        "range_zero_rows": int(zero.sum()),
        "range_zero_flag_true_share": share((zero & flag).sum(), zero.sum()),
        "price_skew_raw": round(float(stats.skew(raw_prices)), 2),
        "price_kurtosis_raw": round(float(stats.kurtosis(raw_prices)), 1),
        "price_skew_in_band": round(float(stats.skew(sales["Sale Price"])), 3),
        "log_price_skew_in_band": round(
            float(stats.skew(np.log(sales["Sale Price"]))), 3
        ),
        "latest_sale_rows": int(len(latest)),
        "latest_sale_below_rows": int((~above).sum()),
        "latest_sale_above_rows": int(above.sum()),
        "log_price_std_below": round(float(log_price[~above].std()), 3),
        "log_price_std_above": round(float(log_price[above].std()), 3),
    }


def main():
    """Compute all EDA statistics and render all figures."""
    os.makedirs(FIG_DIR, exist_ok=True)
    os.makedirs(NOTE_DIR, exist_ok=True)

    pop = data.load_ev_population()
    tx = data.add_date_columns(data.load_ev_transactions())
    sales = data.used_sales(tx)
    irs_raw = data.load_irs_zip_income()

    stats_out = {"d1": profile_population(pop)}
    stats_out["d2"], months = profile_transactions(tx, sales)
    stats_out["rq3"] = profile_new_registrations(tx, months)
    stats_out["d3"], profile = profile_income(irs_raw)
    stats_out["join_d1_d3"] = join_population_income(pop, profile)
    stats_out["join_d2_d3"] = join_transactions_income(tx, profile)
    stats_out["join_d2_d1"] = join_transactions_population(tx, pop, sales)
    stats_out["rq4_sample"] = describe_rq4_sample(tx, sales)
    stats_out["assumptions"] = assumption_checks(tx, sales)

    path = os.path.join(NOTE_DIR, "eda_stats.json")
    with open(path, "w") as handle:
        json.dump(stats_out, handle, indent=2)
    for key in stats_out:
        print(f"{key}: {json.dumps(stats_out[key])[:300]}")
    print(f"\nFigures written to {FIG_DIR}/")
    print(f"Stats written to {path}")


if __name__ == "__main__":
    main()
