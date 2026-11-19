"""Tests for src/data.py.

The failure modes that matter here are silent ones: a ZIP normalisation that
drops rows, a deduplication that counts events instead of vehicles, or a
quartile assignment that loses ZIP codes.  Each test therefore asserts an
exact expected value on a hand-built frame rather than checking that the
function merely runs.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import data  # noqa: E402


def test_normalize_zip_pads_and_rejects_junk():
    raw = pd.Series(["98004", "802", "00000", "", None, "98177.0"])
    result = data.normalize_zip(raw)
    assert result.iloc[0] == "98004"
    assert result.iloc[1] == "00802"
    assert pd.isna(result.iloc[2])     # state-total row
    assert pd.isna(result.iloc[3])     # empty string
    assert pd.isna(result.iloc[4])     # null input
    assert result.iloc[5] == "98177"   # float-formatted ZIP


def test_normalize_zip_keeps_leading_zero():
    result = data.normalize_zip(pd.Series([802]))
    assert result.iloc[0] == "00802"
    assert len(result.iloc[0]) == 5


def test_zip_ev_counts_deduplicates_by_vehicle():
    frame = pd.DataFrame(
        {
            "ZIP": ["98004", "98004", "98004", "98005"],
            "DOL Vehicle ID": [1, 1, 2, 3],
            "Electric Vehicle Type": [
                data.BEV if hasattr(data, "BEV")
                else "Battery Electric Vehicle (BEV)",
                "Battery Electric Vehicle (BEV)",
                "Plug-in Hybrid Electric Vehicle (PHEV)",
                "Battery Electric Vehicle (BEV)",
            ],
        }
    )
    counts = data.zip_ev_counts(frame).set_index("ZIP")
    # three rows in 98004 but only two distinct vehicles
    assert counts.loc["98004", "EV_COUNT"] == 2
    assert counts.loc["98004", "BEV_COUNT"] == 1
    assert counts.loc["98004", "BEV_SHARE"] == pytest.approx(0.5)
    assert counts.loc["98005", "EV_COUNT"] == 1


def test_income_profile_applies_return_threshold():
    frame = pd.DataFrame(
        {
            "ZIP": ["98004", "98004", "98005"],
            "N1": [60.0, 60.0, 99.0],
            "A00100": [6000.0, 6000.0, 99.0],
        }
    )
    profile = data.income_profile(frame, min_returns=100).set_index("ZIP")
    assert "98005" not in profile.index       # 99 returns < threshold
    assert profile.loc["98004", "RETURNS"] == 120
    assert profile.loc["98004", "AVG_AGI"] == pytest.approx(100.0)


def test_add_income_quartile_is_return_weighted():
    frame = pd.DataFrame(
        {
            "ZIP": ["a", "b", "c", "d"],
            "RETURNS": [1000.0, 1000.0, 1000.0, 1000.0],
            "AVG_AGI": [10.0, 20.0, 30.0, 40.0],
        }
    )
    result = data.add_income_quartile(frame).set_index("ZIP")
    assert result.loc["a", "INCOME_QUARTILE"] == 1
    assert result.loc["d", "INCOME_QUARTILE"] == 4
    # every ZIP survives the assignment
    assert len(result) == 4


def test_add_income_quartile_respects_weights():
    # One huge ZIP holding 75% of the returns must dominate the boundaries:
    # with weights 750/150/100 the weighted quartile edges fall below $20k,
    # so the $30k ZIP lands in the top quartile while equal weights would
    # have split the four ZIPs evenly.
    frame = pd.DataFrame(
        {
            "ZIP": ["big", "mid", "top"],
            "RETURNS": [750.0, 150.0, 100.0],
            "AVG_AGI": [10.0, 20.0, 30.0],
        }
    )
    result = data.add_income_quartile(frame).set_index("ZIP")
    assert result.loc["top", "INCOME_QUARTILE"] == 4
    assert result.loc["big", "INCOME_QUARTILE"] < 4


def test_quartiles_are_monotone_in_income():
    frame = pd.DataFrame(
        {
            "ZIP": [str(i) for i in range(20)],
            "RETURNS": [100.0] * 20,
            "AVG_AGI": [float(i * 10) for i in range(20)],
        }
    )
    result = data.add_income_quartile(frame).sort_values("AVG_AGI")
    quartiles = result["INCOME_QUARTILE"].tolist()
    assert quartiles == sorted(quartiles)          # non-decreasing
    assert min(quartiles) == 1 and max(quartiles) == 4
    assert len(result) == 20                        # no ZIP lost


def test_zip_condition_counts_builds_shares(tmp_path):
    csv_path = tmp_path / "tx.csv"
    pd.DataFrame(
        {
            "DOL Vehicle ID": [1, 2, 3, 4],
            "Model Year": [2020] * 4,
            "Electric Range": [200] * 4,
            "New or Used Vehicle": ["Used", "Used", "New", "Used"],
            "Sale Price": [1000] * 4,
            "Transaction Type": ["Transfer Title"] * 4,
            "Transaction Date": ["2024-01-01"] * 4,
            "Year": [2024] * 4,
            "County": ["King"] * 4,
            "State": ["WA"] * 4,
            "Postal Code": ["98004", "98004", "98004", "98005"],
            "Meets 2019 HB 2042 Electric Range Requirement": [True] * 4,
        }
    ).to_csv(csv_path, index=False)
    tx = data.load_ev_transactions(path=str(csv_path))
    counts = data.zip_condition_counts(tx).set_index("ZIP")
    assert counts.loc["98004", "Used"] == 2
    assert counts.loc["98004", "New"] == 1
    assert counts.loc["98004", "USED_SHARE"] == pytest.approx(2 / 3)
    assert counts.loc["98005", "USED_SHARE"] == pytest.approx(1.0)
