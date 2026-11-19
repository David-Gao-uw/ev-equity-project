"""Tests for the summary helpers in src/eda_report.py.

Every number in the report passes through these helpers, so each test pins
the helper to a value worked out by hand.
"""

import numpy as np
import pandas as pd
import pytest

import eda_report


def test_seven_number_matches_hand_computation():
    summary = eda_report.seven_number(pd.Series([1, 2, 3, 4, 5, 6, 7]))
    assert summary["n"] == 7
    assert summary["mean"] == pytest.approx(4.0)
    assert summary["std"] == pytest.approx(np.sqrt(28 / 6))
    assert (summary["min"], summary["max"]) == (1.0, 7.0)
    assert (summary["q1"], summary["median"], summary["q3"]) == (
        2.5, 4.0, 5.5
    )


def test_seven_number_ignores_non_numeric_values():
    summary = eda_report.seven_number(pd.Series(["10", None, "x", 20]))
    assert summary["n"] == 2
    assert summary["mean"] == pytest.approx(15.0)


def test_missing_report_counts_cells_and_columns():
    frame = pd.DataFrame({"a": [1, None, 3, 4], "b": [None, None, 1, 1]})
    report = eda_report.missing_report(frame, "toy")
    assert report["cells_missing"] == 3
    assert report["cells_total"] == 8
    assert report["by_column"]["a"] == {"missing": 1, "pct": 25.0}
    assert report["by_column"]["b"]["missing"] == 2


def test_value_counts_lists_every_value_including_missing():
    frame = pd.DataFrame({"kind": ["x", "y", "x", None, np.nan]})
    counts = eda_report.value_counts(frame, "kind")
    assert counts == {"x": 2, "y": 1, "(missing)": 2}


def test_series_to_dict_writes_plain_numbers():
    series = pd.Series([3, 4], index=[2024, 2025])
    assert eda_report.series_to_dict(series) == {"2024": 3, "2025": 4}
    shares = pd.Series([0.12345], index=["King"])
    assert eda_report.series_to_dict(shares, 2) == {"King": 0.12}


def test_count_table_counts_every_pair():
    frame = pd.DataFrame({"kind": ["a", "a", "b"], "flag": [1, 0, 1]})
    table = eda_report.count_table(frame, "kind", "flag")
    assert table.loc["a", 1] == 1
    assert table.loc["b", 0] == 0
    assert table.loc["b", 1] == 1


def test_chi_square_reports_cramers_v():
    # Expected counts are 20 in every cell, so chi2 = 4 * 100 / 20 = 20 and
    # V = sqrt(20 / (120 * 1)).
    result = eda_report.chi_square([[10, 20, 30], [30, 20, 10]])
    assert result["chi2"] == pytest.approx(20.0)
    assert result["dof"] == 2
    assert result["min_expected"] == pytest.approx(20.0)
    assert result["cramers_v"] == pytest.approx(np.sqrt(20 / 120), abs=1e-4)


def test_chi_square_is_zero_for_independent_table():
    result = eda_report.chi_square([[10, 20, 30], [20, 40, 60]])
    assert result["chi2"] == pytest.approx(0.0)
    assert result["cramers_v"] == pytest.approx(0.0)


def test_is_wa_zip_uses_state_prefix_range():
    zips = pd.Series(["98004", "99403", "97201", "83814"])
    assert eda_report.is_wa_zip(zips).tolist() == [True, True, False, False]


def test_range_group_labels_each_band_and_skips_missing():
    ranges = pd.Series([0, 1, 29, 30, 300, np.nan])
    groups = eda_report.range_group(ranges)
    assert groups.iloc[0] == "0 (unknown)"
    assert groups.iloc[1] == "1-29 miles"
    assert groups.iloc[2] == "1-29 miles"
    assert groups.iloc[3] == "30+ miles"
    assert groups.iloc[4] == "30+ miles"
    assert pd.isna(groups.iloc[5])


def test_yearly_growth_and_trailing_mean():
    counts = pd.Series([100, 200, 100, 150], index=[2020, 2021, 2022, 2023])
    growth, trailing = eda_report.yearly_growth(counts)
    assert growth == {2021: 1.0, 2022: -0.5, 2023: 0.5}
    assert trailing == {2023: pytest.approx(1.0 / 3)}


def test_check_unique_rejects_a_duplicated_key():
    eda_report.check_unique(pd.DataFrame({"ZIP": ["1", "2"]}), "ZIP")
    raised = False
    try:
        eda_report.check_unique(pd.DataFrame({"ZIP": ["1", "1"]}), "ZIP")
    except ValueError:
        raised = True
    assert raised
