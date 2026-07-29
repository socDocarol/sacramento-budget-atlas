from __future__ import annotations

import pandas as pd

from budget_app.data.domain import safe_csv_export, validate_scenario


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "fiscal_year": 2027,
                "department": "Police",
                "fund": "General Fund",
                "category": "Personnel",
                "amount": 100.0,
                "expense_revenue": "Expenses",
                "fund_category": "Governmental Funds",
                "object_id": 1,
            },
            {
                "fiscal_year": 2027,
                "department": "Parks",
                "fund": "General Fund",
                "category": "Programs",
                "amount": 40.0,
                "expense_revenue": "Expenses",
                "fund_category": "Governmental Funds",
                "object_id": 2,
            },
        ]
    )


def test_scenario_requires_balance_and_nonnegative_allocations() -> None:
    unbalanced = validate_scenario(
        frame(), year=2027, scope="general_fund", adjustments={"Police": 10}, balanced=True
    )
    assert not unbalanced.valid
    balanced = validate_scenario(
        frame(), year=2027, scope="general_fund", adjustments={"Police": 10, "Parks": -10}
    )
    assert balanced.valid
    negative = validate_scenario(
        frame(), year=2027, scope="general_fund", adjustments={"Parks": -100}, balanced=False
    )
    assert not negative.valid


def test_csv_export_neutralizes_formula_cells() -> None:
    csv = safe_csv_export(pd.DataFrame({"label": ["=SUM(A1:A2)", "@cmd"], "amount": [1, -2]}))
    assert "'=SUM(A1:A2)" in csv
    assert "'@cmd" in csv
