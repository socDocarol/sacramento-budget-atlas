from __future__ import annotations

import pytest

from budget_app.data.normalize import DataValidationError, normalize_features


def feature(**overrides: object) -> dict[str, object]:
    values = {
        "Fiscal_Year": "2027",
        "Department": "  Police\n Department ",
        "Fund": "General   Fund",
        "CATEGORY": "  Personnel ",
        "Amount": "12.5",
        "ExpenseRevenue": " r ",
        "Fund_Category": "Governmental Funds",
        "ObjectId": 7,
    }
    values.update(overrides)
    return {"attributes": values}


def test_normalize_features_enforces_eight_field_contract() -> None:
    rows = normalize_features([feature()])
    assert list(rows.columns) == [
        "fiscal_year",
        "department",
        "fund",
        "category",
        "amount",
        "expense_revenue",
        "fund_category",
        "object_id",
    ]
    assert rows.iloc[0].to_dict() == {
        "fiscal_year": 2027,
        "department": "Police Department",
        "fund": "General Fund",
        "category": "Personnel",
        "amount": 12.5,
        "expense_revenue": "Revenues",
        "fund_category": "Governmental Funds",
        "object_id": 7,
    }


def test_unknown_flow_is_rejected() -> None:
    with pytest.raises(DataValidationError, match="unknown ExpenseRevenue"):
        normalize_features([feature(ExpenseRevenue="transfer")])
