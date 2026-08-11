from __future__ import annotations

import pandas as pd
import pytest

from budget_app.ui.overview_metrics import (
    build_overview_measure_summary,
    fixed_fy2027_expense_benchmark,
    format_signed_currency,
    format_signed_percent,
)


def mixed_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (2027, "Police", "General Fund", "Personnel", 1000.0, "Expenses", 1),
            (2027, "Fire", "General Fund", "Personnel", 700.0, "Expenses", 2),
            (2027, "Parks", "Measure U Fund", "Programs", 500.0, "Expenses", 3),
            (2027, "Finance", "General Fund", "Taxes", 200.0, "Revenues", 4),
            (2027, "Utilities", "Measure U Fund", "Fees", 300.0, "Revenues", 5),
            (2026, "Police", "General Fund", "Personnel", 800.0, "Expenses", 6),
            (2026, "Fire", "General Fund", "Personnel", 400.0, "Expenses", 7),
            (2026, "Parks", "Measure U Fund", "Programs", 100.0, "Expenses", 8),
            (2026, "Finance", "General Fund", "Taxes", 0.0, "Revenues", 9),
        ],
        columns=[
            "fiscal_year",
            "department",
            "fund",
            "category",
            "amount",
            "expense_revenue",
            "object_id",
        ],
    ).assign(fund_category="Governmental Funds")


def test_measure_summaries_keep_revenue_and_expense_separate() -> None:
    rows = mixed_rows()

    expense = build_overview_measure_summary(rows, year=2027, flow="expense", fund_scope="all_funds")
    revenue = build_overview_measure_summary(rows, year=2027, flow="revenue", fund_scope="all_funds")

    assert expense.measure == "Expenses"
    assert expense.current_amount == 2200.0
    assert expense.prior_amount == 1300.0
    assert expense.change_amount == 900.0
    assert expense.change_percent == pytest.approx(69.230769)
    assert expense.largest_department == "Police"
    assert expense.largest_department_amount == 1000.0
    assert expense.largest_department_share == pytest.approx(5 / 11)
    assert revenue.measure == "Revenues"
    assert revenue.current_amount == 500.0
    assert revenue.prior_amount == 0.0
    assert revenue.change_amount == 500.0
    assert revenue.change_percent is None
    assert revenue.largest_department == "Utilities"
    assert revenue.largest_department_amount == 300.0
    assert revenue.largest_department_share == 0.6


def test_measure_summary_scope_changes_every_contextual_value() -> None:
    summary = build_overview_measure_summary(
        mixed_rows(), year=2027, flow="expense", fund_scope="general_fund"
    )

    assert summary.current_amount == 1700.0
    assert summary.prior_amount == 1200.0
    assert summary.change_amount == 500.0
    assert summary.change_percent == pytest.approx(41.666667)
    assert summary.largest_department == "Police"
    assert summary.largest_department_amount == 1000.0
    assert summary.largest_department_share == pytest.approx(10 / 17)


def test_measure_summary_uses_exact_prior_year_and_preserves_missing_prior() -> None:
    summary = build_overview_measure_summary(mixed_rows(), year=2026, flow="expense", fund_scope="all_funds")

    assert summary.year == 2026
    assert summary.prior_year == 2025
    assert summary.prior_amount is None
    assert summary.change_amount is None
    assert summary.change_percent is None


def test_fixed_expense_benchmark_ignores_active_context() -> None:
    assert fixed_fy2027_expense_benchmark(mixed_rows()) == 2200.0


def test_signed_formatters_keep_complete_signs_and_values() -> None:
    assert format_signed_currency(84_321_004) == "+$84,321,004"
    assert format_signed_currency(-2_000) == "-$2,000"
    assert format_signed_percent(5.6) == "+5.6%"
    assert format_signed_percent(-1.2) == "-1.2%"
