"""Pure, context-bound measures for the Overview page."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from budget_app.data.domain import filter_rows

FLOW_VALUES = {"revenue": "Revenues", "expense": "Expenses"}


@dataclass(frozen=True, slots=True)
class OverviewMeasureSummary:
    year: int
    prior_year: int
    measure: str
    current_amount: float
    prior_amount: float | None
    change_amount: float | None
    change_percent: float | None
    largest_department: str | None
    largest_department_amount: float | None
    largest_department_share: float | None


def build_overview_measure_summary(
    rows: pd.DataFrame,
    *,
    year: int,
    flow: Literal["revenue", "expense"],
    fund_scope: str,
) -> OverviewMeasureSummary:
    """Summarize one flow, scope, and current fiscal year without mixing measures."""

    measure = FLOW_VALUES[flow]
    active = filter_rows(rows, year=year, flow=measure, scope=fund_scope)
    prior_year = year - 1
    prior = filter_rows(rows, year=prior_year, flow=measure, scope=fund_scope)
    current_amount = float(active["amount"].sum())
    prior_amount = float(prior["amount"].sum()) if not prior.empty else None
    change_amount = current_amount - prior_amount if prior_amount is not None else None
    change_percent = (
        change_amount / prior_amount * 100 if change_amount is not None and prior_amount != 0 else None
    )
    departments = (
        active.groupby("department", as_index=False)["amount"]
        .sum()
        .sort_values(["amount", "department"], ascending=[False, True])
    )
    if departments.empty:
        largest_department = None
        largest_department_amount = None
        largest_department_share = None
    else:
        largest = departments.iloc[0]
        largest_department = str(largest["department"])
        largest_department_amount = float(largest["amount"])
        largest_department_share = largest_department_amount / current_amount if current_amount else None
    return OverviewMeasureSummary(
        year=year,
        prior_year=prior_year,
        measure=measure,
        current_amount=current_amount,
        prior_amount=prior_amount,
        change_amount=change_amount,
        change_percent=change_percent,
        largest_department=largest_department,
        largest_department_amount=largest_department_amount,
        largest_department_share=largest_department_share,
    )


def fixed_fy2027_expense_benchmark(rows: pd.DataFrame) -> float:
    """Return the fixed all-funds FY2027 expense amount for comparison."""

    benchmark_rows = filter_rows(rows, year=2027, flow="Expenses", scope="all_funds")
    return float(benchmark_rows["amount"].sum())


def format_signed_currency(value: float) -> str:
    """Format a whole-dollar value with an explicit sign."""

    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.0f}"


def format_signed_percent(value: float) -> str:
    """Format a one-decimal percentage with an explicit sign."""

    return f"{value:+.1f}%"
