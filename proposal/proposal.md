---
title: "Electrification and Equity: Income, Secondary Markets, and Policy Thresholds in Washington State EV Adoption"
subtitle: "CSE 163 Final Project — Part 1: Proposal"
---

**Author:** David Gao  **Course:** CSE 163, Autumn 2026

## 1. Research Questions

1. Across Washington ZIP codes, is EV ownership per 1,000 tax returns monotonically associated with average adjusted gross income (AGI) per return, and how large is the gradient across income quartiles?
2. Do used EVs reach lower-income ZIP codes than new ones — that is, is the new-versus-used registration mix dependent on income quartile?
3. How is annual growth in new EV registrations distributed across Washington's 39 counties from 2010 to 2025, and does King County's share of statewide registrations decline over time?
4. Among used EV sales with a positive recorded price, how does sale price vary with rated electric range, and does that slope differ significantly above versus below the 30-mile range threshold set by 2019 HB 2042?

## 2. Motivation

Washington forgoes revenue each year through EV tax exemptions, and a tax expenditure is a distributive choice: it matters who receives it. Those exemptions are capped by vehicle price, which mechanically steers the benefit toward buyers of higher-priced cars, and charging access and home ownership — the practical prerequisites for owning an EV — are themselves unevenly distributed. Whether the subsidy is therefore regressive is an empirical question, not a rhetorical one, and it can be answered from registration and income records alone. The answer also has a forward-looking half: if the used market steadily moves EVs from high-income to lower-income ZIP codes, the equity picture of the subsidy today differs from the equity picture of electrification over time. Measuring where adoption lands, and through which market channel, is what makes incentive design possible.

## 3. Datasets

All three are public, download as direct CSV links, and require no login or key. None has been used in a CSE 163 assignment or lecture reading.

**[D1] WA Dept. of Licensing — Electric Vehicle Population Data** (300,142 rows, 72 MB)
<https://data.wa.gov/api/views/f6w7-q2d2/rows.csv?accessType=DOWNLOAD>
One row per registered EV: `County`, `Postal Code`, `Electric Vehicle Type` (BEV/PHEV), `Electric Range`, `DOL Vehicle ID`.

**[D2] WA Dept. of Licensing — EV Title and Registration Activity** (1,926,507 rows, 258 MB)
<https://data.wa.gov/api/views/rpr4-cgyd/rows.csv?accessType=DOWNLOAD>
One row per transaction: `transaction_year`, `transaction_type`, `county`, `zip`, `state_of_residence`, `new_or_used_vehicle`, `sale_price`, `electric_range`, `DOL Vehicle ID`, plus three pre-computed HB 2042 eligibility flags.

**[D3] IRS Statistics of Income — ZIP Code Data, TY2022** (216 MB)
<https://www.irs.gov/pub/irs-soi/22zpallagi.csv>
Income by ZIP and AGI bracket: `zipcode`, `STATE`, `agi_stub`, `N1` (returns), `A00100` (total AGI).

All cleaning — ZIP normalization, deduplication by `DOL Vehicle ID`, threshold and outlier rules — is performed by Python code we write; no CSV is edited by hand.

## 4. Challenge Goals

**Multiple Datasets.** We use **three** datasets and combine them rather than merely presenting them side by side. Three research questions each require at least two datasets: RQ1 merges D1's per-ZIP EV counts with D3's per-ZIP income profile, RQ2 merges D2's per-ZIP new-versus-used counts with the same income profile, and RQ4 joins D2 to D1 on `DOL Vehicle ID`. This satisfies the requirement of at least three datasets, at least two research questions spanning two datasets, and at least one join/merge operation.

**Result Validity.** Every substantive conclusion is backed by a test whose assumptions we state and justify. RQ1 tests the Spearman correlation with a **permutation test (10,000 label shuffles)** rather than a naive p-value, because adjacent ZIP codes are spatially autocorrelated and their observations are therefore not independent; a bootstrap confidence interval is reported alongside, and the correlation is computed separately within income quartiles to show it is not driven by one region of the distribution. RQ2 applies a **chi-square test of independence** to the quartile-by-condition table with Cramér's V as effect size, so a large sample cannot convert a trivial difference into a finding. RQ4 uses a **t-test plus Mann-Whitney U** on prices either side of the range threshold — U being primary because sale prices are right-skewed — and tests the significance of an interaction term in an OLS model. Results are phrased as associations, never causal claims.

## 5. Method

**RQ1.** Aggregate D1 by `Postal Code`, counting distinct `DOL Vehicle ID` and taking the BEV share. From D3, drop `zipcode == "00000"`, restrict to `STATE == "WA"`, sum `A00100` and `N1` across `agi_stub` for average AGI per return, and discard ZIPs with fewer than 100 returns, since a few high-income filers would otherwise dominate a small ZIP's average. Merge on `Postal Code == zipcode` and compute EVs per 1,000 returns — returns as the denominator, so no separate population dataset is needed. Spearman's rho with its permutation p-value and bootstrap interval decides whether a gradient exists; medians per income quartile give its size. A rho near zero means the exemptions are not regressive at this geographic scale, which is also a definite answer.

**RQ2.** From D2, count registrations per `zip` split by `new_or_used_vehicle`, merge to the D3 quartiles, and build the 4×2 quartile-by-condition table. A chi-square test with Cramér's V asks whether the new/used mix depends on income; the used-share by quartile then shows its direction and size. If used share rises as income falls, the secondary market is redistributing electrification downward and the subsidy's regressive profile is a snapshot rather than a trajectory. Output: stacked bar of new versus used by quartile.

**RQ3.** Restrict D2 to new-adoption `transaction_type` values with `state_of_residence == "WA"`, group by `transaction_year` and `county`, and compute year-over-year growth plus a 3-year trailing mean to damp small-base noise. Years with incomplete monthly coverage at the file edges are excluded and documented. King County's declining share of statewide registrations would answer the diffusion question directly.

**RQ4.** Filter D2 to `new_or_used_vehicle == "Used"` with `sale_price > 0` and `electric_range > 0`, reporting how many rows survive. Verify that `meets_2019_hb_2042_electric_range_requirement` behaves as a clean step function in `electric_range`, then compare prices across that line. OLS `sale_price ~ electric_range * above_threshold + model_year + odometer_reading`: a significant interaction means the policy cutoff is visible as a structural break in the resale market, which would show a price cap doing more than changing averages.

*Challenge-goal links:* the joins in RQ1, RQ2, and RQ4 implement **Multiple Datasets**; the permutation, chi-square, and interaction tests implement **Result Validity**.

## 6. Work Plan

| # | Task | Hours |
|---|------|-------|
| 1 | Downloaders and loaders with schema assertions (`src/data.py`) | 5 |
| 2 | Cleaning: ZIP normalization, dedup, missing and outlier rules | 5 |
| 3 | EDA and diagnostics, decisions recorded in `notes/eda.md` | 4 |
| 4 | RQ1 and RQ2 analyses with their validity tests | 6 |
| 5 | RQ3 and RQ4 analyses including the OLS model | 5 |
| 6 | Figures, report, `pytest` suite, README | 5 |
| **Total** | | **30** |

**Workflow.** Development is in a GitHub repository whose `main` branch always runs end-to-end; each task is a branch and a pull request, complete only when the script runs from a clean checkout, `pytest` passes, and the PR states which research question it advances with its output pasted in. Tests cover what fails silently: schema checks, ZIP normalization (leading-zero loss is the likeliest bug here), deduplication, and quartile assignment; an analysis script also runs against a 1,000-row sample so the suite finishes in seconds. If a task overruns by three hours we pair in one session, and if it stays blocked we descope explicitly (e.g. drop the stacked bar, keep the quartile medians) and record it in the README. The plan is ordered so a failure in RQ4 does not take RQ1–RQ3 with it.

**Environment.** Python 3.11 scripts in VS Code, with a pinned `requirements.txt` (`pandas`, `numpy`, `matplotlib`, `seaborn`, `scipy`, `statsmodels`, `pytest`) verified by importing each and printing versions. Large source files are gitignored and fetched by the download script, keeping the repository small but reproducible. We chose local over Colab because the combined download is roughly 550 MB and a 1.9-million-row DataFrame will not reliably coexist with that in a Colab session.
