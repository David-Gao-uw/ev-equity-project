"""Tests for src/data.py.

The failure modes that matter here are silent ones: a ZIP normalisation that
drops rows, a deduplication that counts events instead of vehicles, or a
quartile assignment that loses ZIP codes.  Each test therefore asserts an
exact expected value on a hand-built frame rather than checking that the
function merely runs.  ``src`` is put on the path by ``conftest.py``.
"""

import os

import pandas as pd
import pytest

import data

TEMP_CSV = os.path.join(os.path.dirname(__file__), "temp_test_data.csv")

TX_DEFAULTS = {
    "DOL Vehicle ID": 1,
    "Model Year": 2020,
    "Electric Range": 200,
    "Odometer Reading": 10000,
    "New or Used Vehicle": "Used",
    "Sale Price": 20000,
    "Transaction Type": "Transfer Title",
    "Transaction Date": "January 1 2024",
    "Year": 2024,
    "County": "King",
    "State": "WA",
    "Postal Code": "98004",
    "Meets 2019 HB 2042 Electric Range Requirement": True,
}


def load_through_csv(frame, loader):
    """Write ``frame`` to a temporary CSV, read it back with ``loader``."""
    frame.to_csv(TEMP_CSV, index=False)
    result = loader(path=TEMP_CSV)
    os.remove(TEMP_CSV)
    return result


def make_transactions(rows):
    """Build and load a transaction file from a list of partial rows.

    Each dict in ``rows`` overrides the defaults in ``TX_DEFAULTS``, so a
    test states only the fields it is actually about.
    """
    records = []
    for row in rows:
        record = dict(TX_DEFAULTS)
        record.update(row)
        records.append(record)
    return load_through_csv(pd.DataFrame(records), data.load_ev_transactions)


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


def test_normalize_zip_rejects_irs_small_zip_bucket():
    # 99999 is the IRS bucket for ZIPs with under 100 returns; treating it
    # as a place would create the largest "ZIP" in the state.
    result = data.normalize_zip(pd.Series(["99999", "99999.0", "99362"]))
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == "99362"


def test_load_irs_zip_income_keeps_real_wa_zips_only():
    frame = pd.DataFrame(
        {
            "STATEFIPS": [53, 53, 53, 41],
            "STATE": ["WA", "WA", "WA", "OR"],
            "zipcode": ["0", "99999", "98004", "97201"],
            "agi_stub": [1, 1, 1, 1],
            "N1": [1000.0, 500.0, 200.0, 300.0],
            "A00100": [9000.0, 4000.0, 2000.0, 3000.0],
        }
    )
    irs = load_through_csv(frame, data.load_irs_zip_income)
    assert irs["ZIP"].tolist() == ["98004"]


def test_load_ev_population_rejects_duplicate_vehicles():
    row = {}
    for column in data.POP_COLUMNS:
        row[column] = "x"
    row["Postal Code"] = "98004"
    row["DOL Vehicle ID"] = 7
    pd.DataFrame([row, row]).to_csv(TEMP_CSV, index=False)
    raised = False
    try:
        data.load_ev_population(path=TEMP_CSV)
    except ValueError:
        raised = True
    os.remove(TEMP_CSV)
    assert raised


def test_zip_ev_counts_deduplicates_by_vehicle():
    frame = pd.DataFrame(
        {
            "ZIP": ["98004", "98004", "98004", "98005"],
            "DOL Vehicle ID": [1, 1, 2, 3],
            "Electric Vehicle Type": [data.BEV, data.BEV, data.PHEV, data.BEV],
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
    # its returns span the first three quarters of filers, so the $30k ZIP
    # lands in the top quartile while equal weights would have put it lower.
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


def test_add_income_quartile_keeps_original_row_order():
    frame = pd.DataFrame(
        {
            "ZIP": ["rich", "poor"],
            "RETURNS": [100.0, 100.0],
            "AVG_AGI": [90.0, 10.0],
        }
    )
    result = data.add_income_quartile(frame)
    assert result["ZIP"].tolist() == ["rich", "poor"]
    assert result["INCOME_QUARTILE"].tolist() == [4, 2]


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


def test_add_date_columns_splits_and_orders_dates():
    tx = make_transactions(
        [
            {"Transaction Date": "October 26 2026"},
            {"Transaction Date": "January 6 2010"},
        ]
    )
    result = data.add_date_columns(tx)
    assert result["TX_YEAR"].tolist() == [2026, 2010]
    assert result["TX_MONTH"].tolist() == [10, 1]
    assert result["TX_ORDER"].tolist() == [20261026, 20100106]
    assert "TX_YEAR" not in tx.columns    # the input is left unchanged


def test_zip_condition_counts_builds_shares():
    tx = make_transactions(
        [
            {"DOL Vehicle ID": 1, "New or Used Vehicle": "Used"},
            {"DOL Vehicle ID": 2, "New or Used Vehicle": "Used"},
            {"DOL Vehicle ID": 3, "New or Used Vehicle": "New",
             "Transaction Type": "Original Title"},
            {"DOL Vehicle ID": 4, "New or Used Vehicle": "Used",
             "Postal Code": "98005"},
        ]
    )
    counts = data.zip_condition_counts(tx).set_index("ZIP")
    assert counts.loc["98004", "Used"] == 2
    assert counts.loc["98004", "New"] == 1
    assert counts.loc["98004", "USED_SHARE"] == pytest.approx(2 / 3)
    assert counts.loc["98005", "USED_SHARE"] == pytest.approx(1.0)


def test_zip_condition_counts_ignores_renewals_by_default():
    # One new purchase followed by three renewals of the same car: the car
    # reached its owner new, so the used share must be 0, not 3/4.
    renewal = {"DOL Vehicle ID": 1, "Transaction Type": "Registration Renewal"}
    purchase = {"DOL Vehicle ID": 1, "New or Used Vehicle": "New",
                "Transaction Type": "Original Title"}
    tx = make_transactions([purchase, renewal, renewal, renewal])
    acquisitions = data.zip_condition_counts(tx).set_index("ZIP")
    assert acquisitions.loc["98004", "USED_SHARE"] == pytest.approx(0.0)
    every_event = data.zip_condition_counts(tx, acquisitions_only=False)
    assert every_event.set_index("ZIP").loc["98004", "Used"] == 3


def test_used_sales_applies_every_rq4_rule():
    tx = make_transactions(
        [
            {"DOL Vehicle ID": 1, "New or Used Vehicle": "New"},
            {"DOL Vehicle ID": 2, "Sale Price": 500},          # nominal
            {"DOL Vehicle ID": 3, "Sale Price": 12312016},     # typed date
            {"DOL Vehicle ID": 4, "Electric Range": 0},        # unknown
            {"DOL Vehicle ID": 5, "Electric Range": 29},
            {"DOL Vehicle ID": 6, "Electric Range": 30},
        ]
    )
    sales = data.used_sales(tx).set_index("DOL Vehicle ID")
    assert sorted(sales.index) == [5, 6]
    assert not sales.loc[5, "ABOVE_THRESHOLD"]
    assert sales.loc[6, "ABOVE_THRESHOLD"]


def test_new_titles_by_county_counts_only_new_wa_titles():
    tx = make_transactions(
        [
            {"New or Used Vehicle": "New", "Transaction Type":
             "Original Title", "County": "King"},
            {"New or Used Vehicle": "New", "Transaction Type":
             "Original Title", "County": "King"},
            {"New or Used Vehicle": "New", "Transaction Type":
             "Original Title", "County": "Pierce", "Year": 2025},
            {"New or Used Vehicle": "New", "Transaction Type":
             "Original Title", "County": "Multnomah", "State": "OR"},
            {"Transaction Type": "Original Title", "County": "Pierce"},
            {"Transaction Type": "Registration Renewal", "County": "King"},
        ]
    )
    table = data.new_titles_by_county(tx)
    assert table.loc[2024, "King"] == 2
    assert table.loc[2024, "Pierce"] == 0
    assert table.loc[2025, "Pierce"] == 1
    assert "Multnomah" not in table.columns
