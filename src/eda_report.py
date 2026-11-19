"""Produce every number and figure the EDA report needs.

Running this module writes figures to ``figures/`` and a JSON summary to
``notes/eda_stats.json``.  The report quotes the JSON values directly, so the
prose cannot drift away from what the code computed.

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
BEV = "Battery Electric Vehicle (BEV)"
PHEV = "Plug-in Hybrid Electric Vehicle (PHEV)"


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
    report = {
        column: {
            "missing": int(counts[column]),
            "pct": round(100 * counts[column] / len(frame), 2),
        }
        for column in frame.columns
        if counts[column] > 0
    }
    total_cells = frame.shape[0] * frame.shape[1]
    return {
        "dataset": name,
        "rows": int(frame.shape[0]),
        "columns": int(frame.shape[1]),
        "cells_missing": int(frame.isna().sum().sum()),
        "cells_total": int(total_cells),
        "pct_missing": round(100 * frame.isna().sum().sum() / total_cells, 3),
        "by_column": report,
    }


def value_counts(frame, column, limit=12):
    """Return the most common values of a categorical column."""
    counts = frame[column].value_counts(dropna=False).head(limit)
    return {str(index): int(value) for index, value in counts.items()}


def save_figure(path):
    """Save the current figure at a print-friendly resolution."""
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    return path


def main():
    """Compute all EDA statistics and render all figures."""
    os.makedirs(FIG_DIR, exist_ok=True)
    os.makedirs(NOTE_DIR, exist_ok=True)
    stats_out = {}

    # ---- D1: registered EV population -----------------------------------
    pop = data.load_ev_population()
    stats_out["d1"] = {
        "missing": missing_report(pop, "ev_population"),
        "range_summary": seven_number(pop["Electric Range"]),
        "model_year_counts": value_counts(pop, "Model Year", 30),
        "type_counts": value_counts(pop, "Electric Vehicle Type"),
        "make_counts": value_counts(pop, "Make", 10),
        "zip_missing": int(pop["ZIP"].isna().sum()),
    }

    by_year = pop["Model Year"].value_counts().sort_index()
    by_year = by_year[by_year.index >= 1997]
    plt.figure(figsize=(7, 3.6))
    plt.bar(by_year.index.astype(int), by_year.values, color="#2b6cb0")
    plt.xlabel("Model year")
    plt.ylabel("Registered vehicles")
    plt.title("Figure 1. Registered EVs by model year")
    save_figure(os.path.join(FIG_DIR, "fig1_ev_by_model_year.png"))

    plt.figure(figsize=(7, 3.6))
    for label, colour in ((BEV, "#2b6cb0"), (PHEV, "#c05621")):
        subset = pop.loc[
            pop["Electric Vehicle Type"] == label, "Electric Range"
        ]
        subset = pd.to_numeric(subset, errors="coerce").dropna()
        subset = subset[subset.between(0, 400)]
        plt.hist(subset, bins=50, alpha=0.6, label=label, color=colour)
    plt.xlabel("Rated electric range (miles)")
    plt.ylabel("Vehicles")
    plt.legend()
    plt.title("Figure 2. Electric range by powertrain type")
    save_figure(os.path.join(FIG_DIR, "fig2_ev_range_by_type.png"))

    # ---- D2: transaction records ----------------------------------------
    tx = data.load_ev_transactions()
    stats_out["d2"] = {
        "missing": missing_report(tx, "ev_transactions"),
        "year_counts": value_counts(tx, "Year", 40),
        "condition_counts": value_counts(tx, "New or Used Vehicle"),
        "type_counts": value_counts(tx, "Transaction Type", 10),
        "range_summary": seven_number(tx["Electric Range"]),
        "zip_missing": int(tx["ZIP"].isna().sum()),
    }

    used = tx[(tx["New or Used Vehicle"] == "Used") & (tx["Sale Price"] > 0)]
    stats_out["d2"]["used_price_summary"] = seven_number(used["Sale Price"])
    stats_out["d2"]["used_with_price_rows"] = int(len(used))

    tx_year = tx["Year"].value_counts().sort_index()
    plt.figure(figsize=(7, 3.6))
    plt.plot(tx_year.index.astype(int), tx_year.values, marker="o", ms=3)
    plt.xlabel("Transaction year")
    plt.ylabel("Transactions")
    plt.title("Figure 3. EV title and registration transactions by year")
    save_figure(os.path.join(FIG_DIR, "fig3_transactions_by_year.png"))

    plt.figure(figsize=(7, 3.6))
    prices = pd.to_numeric(used["Sale Price"], errors="coerce").dropna()
    prices = prices[prices.between(0, prices.quantile(0.99))]
    plt.hist(prices, bins=60, color="#2f855a")
    plt.xlabel("Sale price (USD)")
    plt.ylabel("Used EVs sold")
    plt.title("Figure 4. Distribution of used EV sale prices")
    save_figure(os.path.join(FIG_DIR, "fig4_used_price_distribution.png"))

    # ---- D3: IRS income profile -----------------------------------------
    irs_raw = data.load_irs_zip_income()
    profile = data.add_income_quartile(data.income_profile(irs_raw))
    stats_out["d3"] = {
        "raw_rows": len(irs_raw),
        "profile_rows": len(profile),
        "missing": missing_report(irs_raw, "irs_zip_income (WA rows)"),
        "returns_summary": seven_number(profile["RETURNS"]),
        "avg_agi_summary": seven_number(profile["AVG_AGI"]),
        "quartile_counts": {
            str(k): int(v)
            for k, v in profile["INCOME_QUARTILE"].value_counts().items()
        },
        "quartile_median_agi": {
            str(k): round(float(v), 1)
            for k, v in profile.groupby("INCOME_QUARTILE")["AVG_AGI"]
            .median()
            .items()
        },
    }

    plt.figure(figsize=(7, 3.6))
    plt.hist(profile["AVG_AGI"], bins=60, color="#6b46c1")
    plt.xlabel("Average AGI per tax return (thousands of USD)")
    plt.ylabel("ZIP codes")
    plt.title("Figure 5. Average income per return across WA ZIP codes")
    save_figure(os.path.join(FIG_DIR, "fig5_income_distribution.png"))

    # ---- Join 1: D1 x D3 -------------------------------------------------
    evzip = data.zip_ev_counts(pop)
    merged = evzip.merge(profile, on="ZIP", how="inner")
    merged["EV_PER_1K_RETURNS"] = merged["EV_COUNT"] / merged["RETURNS"] * 1000
    rho, p_value = stats.spearmanr(
        merged["AVG_AGI"], merged["EV_PER_1K_RETURNS"]
    )
    stats_out["join_d1_d3"] = {
        "ev_zips": int(len(evzip)),
        "income_zips": int(len(profile)),
        "matched_zips": int(len(merged)),
        "coverage_pct": round(100 * len(merged) / len(evzip), 2),
        "ev_rows_matched_pct": round(
            100 * pop["ZIP"].isin(profile["ZIP"]).sum() / len(pop), 2
        ),
        "ev_per_1k_summary": seven_number(merged["EV_PER_1K_RETURNS"]),
        "avg_agi_summary": seven_number(merged["AVG_AGI"]),
        "spearman_rho": round(float(rho), 4),
        "spearman_p": float(p_value),
        "zips_below_100_returns_excluded": int(
            len(data.income_profile(irs_raw)) < len(profile)
        ),
    }

    quartile_medians = (
        merged.groupby("INCOME_QUARTILE")["EV_PER_1K_RETURNS"].median()
    )
    stats_out["join_d1_d3"]["median_ev_per_1k_by_quartile"] = {
        str(k): round(float(v), 2) for k, v in quartile_medians.items()
    }

    # Powertrain mix by income quartile: the RQ2 comparison that survived EDA.
    mix = merged.groupby("INCOME_QUARTILE")[["BEV_COUNT", "EV_COUNT"]].sum()
    mix["PHEV_COUNT"] = mix["EV_COUNT"] - mix["BEV_COUNT"]
    chi2_mix, p_mix, dof_mix, _ = stats.chi2_contingency(
        mix[["BEV_COUNT", "PHEV_COUNT"]].values
    )
    n_mix = float(mix["EV_COUNT"].sum())
    stats_out["join_d1_d3"]["bev_share_by_quartile"] = {
        str(q): round(
            float(mix.loc[q, "BEV_COUNT"] / mix.loc[q, "EV_COUNT"]), 4
        )
        for q in [1, 2, 3, 4]
    }
    stats_out["join_d1_d3"]["mix_chi2"] = round(float(chi2_mix), 2)
    stats_out["join_d1_d3"]["mix_p"] = float(p_mix)
    stats_out["join_d1_d3"]["mix_cramers_v"] = round(
        float(np.sqrt(chi2_mix / (n_mix * 1))), 5
    )

    plt.figure(figsize=(7, 3.8))
    plt.scatter(
        merged["AVG_AGI"],
        merged["EV_PER_1K_RETURNS"],
        s=10,
        alpha=0.45,
        color="#2b6cb0",
        label="ZIP codes",
    )
    plt.xlabel("Average AGI per return (thousands of USD)")
    plt.ylabel("EVs per 1,000 tax returns")
    plt.title("Figure 7. EV density rises with ZIP-level income")
    plt.legend()
    save_figure(os.path.join(FIG_DIR, "fig7_ev_density_vs_income.png"))

    plt.figure(figsize=(7, 3.6))
    medians = [quartile_medians.get(q, np.nan) for q in [1, 2, 3, 4]]
    plt.bar([1, 2, 3, 4], medians, color="#2b6cb0")
    plt.xlabel("Income quartile (1 = lowest)")
    plt.ylabel("Median EVs per 1,000 returns")
    plt.title("Figure 8. Median EV density by income quartile")
    save_figure(os.path.join(FIG_DIR, "fig8_ev_density_by_quartile.png"))

    # ---- Join 2: D2 x D3 -------------------------------------------------
    cond = data.zip_condition_counts(tx)
    merged2 = cond.merge(profile, on="ZIP", how="inner")
    table = (
        merged2.groupby("INCOME_QUARTILE")[["New", "Used"]]
        .sum()
        .reindex([1, 2, 3, 4])
    )
    chi2, chi_p, dof, expected = stats.chi2_contingency(table.values)
    stats_out["join_d2_d3"] = {
        "tx_zips": int(len(cond)),
        "matched_zips": int(len(merged2)),
        "coverage_pct": round(100 * len(merged2) / len(cond), 2),
        "used_share_by_quartile": {
            str(q): round(float(table.loc[q, "Used"] / table.loc[q].sum()), 4)
            for q in [1, 2, 3, 4]
        },
        "chi2": round(float(chi2), 2),
        "chi2_p": float(chi_p),
        "dof": int(dof),
        "min_expected_cell": round(float(expected.min()), 1),
        "cramers_v": round(
            float(np.sqrt(chi2 / (table.values.sum() * 1))), 5
        ),
        "expected_ok": bool(expected.min() >= 5),
    }

    plt.figure(figsize=(7, 3.6))
    shares = [table.loc[q, "Used"] / table.loc[q].sum() for q in [1, 2, 3, 4]]
    plt.bar([1, 2, 3, 4], shares, color="#c05621")
    plt.xlabel("Income quartile (1 = lowest)")
    plt.ylabel("Share of registrations that are used")
    plt.title("Figure 9. Used-vehicle share by income quartile")
    plt.ylim(0, max(shares) * 1.25)
    save_figure(os.path.join(FIG_DIR, "fig9_used_share_by_quartile.png"))

    plt.figure(figsize=(7, 3.6))
    plt.bar([1, 2, 3, 4], table.sum(axis=1).values, color="#4a5568")
    plt.xlabel("Income quartile (1 = lowest)")
    plt.ylabel("Matched registrations")
    plt.title("Figure 10. Matched transaction volume by income quartile")
    save_figure(os.path.join(FIG_DIR, "fig10_volume_by_quartile.png"))

    plt.figure(figsize=(7, 3.6))
    plt.scatter(
        profile["RETURNS"],
        profile["AVG_AGI"],
        s=12,
        alpha=0.5,
        color="#6b46c1",
        label="ZIP codes",
    )
    plt.xscale("log")
    plt.xlabel("Tax returns per ZIP (log scale)")
    plt.ylabel("Average AGI per return (thousands of USD)")
    plt.title("Figure 6. ZIP size versus average income")
    plt.legend()
    save_figure(os.path.join(FIG_DIR, "fig6_returns_vs_income.png"))

    plt.figure(figsize=(7, 3.6))
    per_vehicle = (
        tx.dropna(subset=["DOL Vehicle ID"]).groupby("DOL Vehicle ID").size()
    )
    counts = per_vehicle.clip(upper=10).value_counts().sort_index()
    plt.bar(counts.index.astype(int), counts.values, color="#2f855a")
    plt.xlabel("Transactions per vehicle (capped at 10)")
    plt.ylabel("Vehicles")
    plt.title("Figure 11. How many transactions a vehicle appears in")
    save_figure(os.path.join(FIG_DIR, "fig11_transactions_per_vehicle.png"))

    pop_years = pop["Model Year"].value_counts().sort_index()
    tx_years = tx["Model Year"].value_counts().sort_index()
    years = sorted(set(pop_years.index) & set(tx_years.index))
    years = [y for y in years if 2011 <= y <= 2026]
    plt.figure(figsize=(7, 3.6))
    plt.plot(years, [pop_years.get(y, 0) / len(pop) for y in years],
             marker="o", ms=3, label="Current registrations (D1)")
    plt.plot(years, [tx_years.get(y, 0) / len(tx) for y in years],
             marker="s", ms=3, label="All transactions (D2)")
    plt.xlabel("Model year")
    plt.ylabel("Share of rows")
    plt.legend()
    plt.title(
        "Figure 12. Model-year composition, population versus transactions"
    )
    save_figure(os.path.join(FIG_DIR, "fig12_model_year_composition.png"))

    # ---- Join 3: D2 x D1 -------------------------------------------------
    pop_ids = set(pop["DOL Vehicle ID"].dropna().astype("int64"))
    tx_ids = set(tx["DOL Vehicle ID"].dropna().astype("int64"))
    stats_out["join_d2_d1"] = {
        "pop_vehicle_ids": len(pop_ids),
        "tx_vehicle_ids": len(tx_ids),
        "matched_ids": len(pop_ids & tx_ids),
        "tx_matched_pct": round(100 * len(pop_ids & tx_ids) / len(tx_ids), 2),
    }

    # ---- Assumption checks for the planned tests ------------------------
    p99 = pd.to_numeric(used["Sale Price"], errors="coerce").dropna()
    flag = tx["Meets 2019 HB 2042 Electric Range Requirement"].astype(str)
    below = tx[flag == "False"]
    above = tx[flag == "True"]
    stats_out["assumptions"] = {
        "used_price_skew": round(float(stats.skew(p99)), 3),
        "used_price_kurtosis": round(float(stats.kurtosis(p99)), 3),
        "flag_false_rows": int(len(below)),
        "flag_true_rows": int(len(above)),
        "range_summary_flag_false": seven_number(below["Electric Range"]),
        "range_summary_flag_true": seven_number(above["Electric Range"]),
        "min_expected_cell_chi2": stats_out["join_d2_d3"]["min_expected_cell"],
    }

    with open(os.path.join(NOTE_DIR, "eda_stats.json"), "w") as handle:
        json.dump(stats_out, handle, indent=2, default=str)

    for key, value in stats_out.items():
        print(f"{key}: {json.dumps(value, default=str)[:400]}")
    print(f"\nFigures written to {FIG_DIR}/")
    print(f"Stats written to {NOTE_DIR}/eda_stats.json")


if __name__ == "__main__":
    main()
