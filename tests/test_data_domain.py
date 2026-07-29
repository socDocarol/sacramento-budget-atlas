from __future__ import annotations

import pandas as pd

from budget_app.data.domain import (
    aggregate_by_dimension,
    build_drilldown_model,
    classify_fund_scope,
    filter_rows,
    overview_totals,
    robust_change_signals,
)


def rows() -> pd.DataFrame:
    records = []
    object_id = 1
    for year in range(2020, 2028):
        records.extend(
            [
                {
                    "fiscal_year": year,
                    "department": "Police",
                    "fund": "General Fund",
                    "category": "Personnel",
                    "amount": float(100 + (year - 2020) * 3),
                    "expense_revenue": "Expenses",
                    "fund_category": "Governmental Funds",
                    "object_id": object_id,
                },
                {
                    "fiscal_year": year,
                    "department": "Parks",
                    "fund": "Measure U Fund",
                    "category": "Programs",
                    "amount": 20.0,
                    "expense_revenue": "Expenses",
                    "fund_category": "Governmental Funds",
                    "object_id": object_id + 1,
                },
            ]
        )
        object_id += 2
    return pd.DataFrame(records)


def test_filter_aggregation_and_drilldown() -> None:
    frame = rows()
    assert classify_fund_scope("Measure U Fund", "Governmental Funds") == "measure_u"
    filtered = filter_rows(frame, year=2027, flow="Expenses", scope="general_fund")
    assert filtered["department"].tolist() == ["Police"]
    totals = overview_totals(frame)
    assert totals.iloc[-1]["expenses"] == 141.0
    grouped = aggregate_by_dimension(frame, "department", year=2027, flow="Expenses")
    assert grouped.iloc[0]["name"] == "Police"
    model = build_drilldown_model(frame, 2027, 2026, "Expenses")
    assert model.root.current == 141.0
    assert any(node.level == "category" for node in model.nodes)


def test_signal_history_is_suppressed_until_minimum_history() -> None:
    frame = rows().loc[lambda value: value["department"].eq("Police")]
    result = robust_change_signals(frame, latest_year=2027)
    assert result.iloc[0]["historical_changes"] >= 6
    assert result.iloc[0]["annual_series"][-1][0] == 2027
    assert result.iloc[0]["suppression_reason"] == "zero_mad"
    assert "suppressed" in result.iloc[0]["formula"]
    assert result.iloc[0]["concentrated"]
    short = frame.loc[frame["fiscal_year"] >= 2025]
    short_result = robust_change_signals(short, latest_year=2027)
    assert short_result["modified_z"].isna().all()
    assert set(short_result["suppression_reason"]) == {"insufficient_history"}
