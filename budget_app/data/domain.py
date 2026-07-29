"""Pure pandas domain transformations for the budget story and Python Lab."""

from __future__ import annotations

import io
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

import numpy as np
import pandas as pd

from .models import (
    FUND_SCOPE_LABELS,
    NORMALIZED_COLUMNS,
    BudgetSnapshot,
    DrilldownModel,
    DrilldownNode,
    Flow,
    ScenarioValidation,
    Scope,
    SnapshotMetadata,
)

Dimension = Literal["department", "fund", "category"]
CONCENTRATION_THRESHOLD = 0.50


def _assert_columns(rows: pd.DataFrame) -> None:
    missing = set(NORMALIZED_COLUMNS).difference(rows.columns)
    if missing:
        raise ValueError(f"Budget dataframe is missing fields: {', '.join(sorted(missing))}")


def classify_fund_scope(
    row_or_fund: Mapping[str, Any] | str,
    fund_category: str | None = None,
) -> Scope:
    """Classify a source row without dropping unknown scopes.

    The mapping form accepts canonical or ArcGIS field names.  ``Fund Total``
    remains in the other-governmental bucket, matching the existing storyboard
    reconciliation convention.
    """

    if isinstance(row_or_fund, Mapping):
        fund = row_or_fund.get("fund", row_or_fund.get("Fund", ""))
        category = row_or_fund.get("fund_category", row_or_fund.get("Fund_Category", ""))
    else:
        fund, category = row_or_fund, fund_category or ""
    fund_text = " ".join(str(fund or "").split()).lower()
    category_text = " ".join(str(category or "").split()).lower()
    if fund_text == "general fund":
        return "general_fund"
    if fund_text == "measure u fund":
        return "measure_u"
    if "interdepartmental service fund" in fund_text or category_text in {
        "internal service funds",
        "risk management",
    }:
        return "internal_service_funds"
    if category_text == "enterprise funds":
        return "enterprise_funds"
    if category_text in {
        "governmental funds",
        "other governmental funds",
        "fund total",
    }:
        return "other_governmental_or_restricted"
    return "unknown"


def add_scope_column(rows: pd.DataFrame) -> pd.DataFrame:
    _assert_columns(rows)
    if "fund_scope" in rows.columns:
        # Prepared bundles persist this classification.  Preserve it rather
        # than paying the per-row classification cost on every consumer path.
        return rows.copy()
    result = rows.copy()
    result["fund_scope"] = [
        classify_fund_scope(fund, category)
        for fund, category in zip(result["fund"], result["fund_category"], strict=True)
    ]
    return result


def filter_rows(
    rows: pd.DataFrame,
    *,
    year: int | None = None,
    flow: Flow | Literal["all"] = "all",
    scope: Scope = "all_funds",
    department: str | None = None,
    fund: str | None = None,
    category: str | None = None,
) -> pd.DataFrame:
    """Apply the explorer filter precedence and preserve source row order."""

    _assert_columns(rows)
    mask = pd.Series(True, index=rows.index)
    if year is not None:
        mask &= rows["fiscal_year"].eq(int(year))
    if flow != "all":
        mask &= rows["expense_revenue"].eq(flow)
    if scope != "all_funds":
        if "fund_scope" in rows.columns:
            mask &= rows["fund_scope"].eq(scope)
        else:
            scopes = [
                classify_fund_scope(fund_name, category_name)
                for fund_name, category_name in zip(rows["fund"], rows["fund_category"], strict=True)
            ]
            mask &= pd.Series(scopes, index=rows.index).eq(scope)
    if department:
        mask &= rows["department"].eq(department)
    if fund:
        mask &= rows["fund"].eq(fund)
    if category:
        mask &= rows["category"].eq(category)
    return rows.loc[mask].copy()


def filter_year(rows: pd.DataFrame, year: int) -> pd.DataFrame:
    """Convenience wrapper for views that only need a fiscal-year lens."""

    return filter_rows(rows, year=year)


def filter_flow(rows: pd.DataFrame, flow: Flow | Literal["all"]) -> pd.DataFrame:
    return filter_rows(rows, flow=flow)


def filter_scope(rows: pd.DataFrame, scope: Scope) -> pd.DataFrame:
    return filter_rows(rows, scope=scope)


def overview_totals(rows: pd.DataFrame) -> pd.DataFrame:
    _assert_columns(rows)
    grouped = (
        rows.assign(
            expenses=np.where(rows["expense_revenue"].eq("Expenses"), rows["amount"], 0.0),
            revenues=np.where(rows["expense_revenue"].eq("Revenues"), rows["amount"], 0.0),
        )
        .groupby("fiscal_year", as_index=False)
        .agg(
            expenses=("expenses", "sum"),
            revenues=("revenues", "sum"),
            line_items=("object_id", "size"),
        )
        .sort_values("fiscal_year")
    )
    grouped["net"] = grouped["revenues"] - grouped["expenses"]
    return grouped.reset_index(drop=True)


def aggregate_by_dimension(
    rows: pd.DataFrame,
    dimension: Dimension,
    *,
    year: int,
    flow: Flow,
    scope: Scope = "all_funds",
) -> pd.DataFrame:
    scoped = filter_rows(rows, year=year, flow=flow, scope=scope)
    if dimension not in {"department", "fund", "category"}:
        raise ValueError(f"Unsupported aggregation dimension: {dimension}")
    name = scoped[dimension].fillna("").replace("", "Unspecified")
    result = (
        scoped.assign(name=name)
        .groupby("name", as_index=False)
        .agg(amount=("amount", "sum"), line_items=("object_id", "size"))
        .sort_values(["amount", "name"], ascending=[False, True])
        .reset_index(drop=True)
    )
    total = float(result["amount"].sum()) if not result.empty else 0.0
    result["share"] = result["amount"] / total if total else 0.0
    return result[["name", "amount", "share", "line_items"]]


def aggregate_departments(
    rows: pd.DataFrame, *, year: int, flow: Flow, scope: Scope = "all_funds"
) -> pd.DataFrame:
    return aggregate_by_dimension(rows, "department", year=year, flow=flow, scope=scope)


def aggregate_funds(rows: pd.DataFrame, *, year: int, flow: Flow, scope: Scope = "all_funds") -> pd.DataFrame:
    return aggregate_by_dimension(rows, "fund", year=year, flow=flow, scope=scope)


def aggregate_categories(
    rows: pd.DataFrame, *, year: int, flow: Flow, scope: Scope = "all_funds"
) -> pd.DataFrame:
    return aggregate_by_dimension(rows, "category", year=year, flow=flow, scope=scope)


def fund_scope_totals(rows: pd.DataFrame, *, year: int) -> pd.DataFrame:
    scoped = add_scope_column(filter_rows(rows, year=year))
    result = (
        scoped.assign(
            expenses=np.where(scoped["expense_revenue"].eq("Expenses"), scoped["amount"], 0.0),
            revenues=np.where(scoped["expense_revenue"].eq("Revenues"), scoped["amount"], 0.0),
        )
        .groupby("fund_scope", as_index=False)
        .agg(
            expenses=("expenses", "sum"),
            revenues=("revenues", "sum"),
            line_items=("object_id", "size"),
            funds=("fund", "nunique"),
        )
    )
    result["net"] = result["revenues"] - result["expenses"]
    result["fund_scope_label"] = result["fund_scope"].map(FUND_SCOPE_LABELS)
    return result.sort_values("expenses", ascending=False).reset_index(drop=True)


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "unspecified"


def build_drilldown_model(
    rows: pd.DataFrame,
    year: int,
    compare_year: int | None,
    flow: Flow,
    scope: Scope = "all_funds",
) -> DrilldownModel:
    _assert_columns(rows)
    included = filter_rows(rows, flow=flow, scope=scope)
    included = included.loc[included["fiscal_year"].isin([year, compare_year])]
    root_current = float(included.loc[included["fiscal_year"].eq(year), "amount"].sum())
    root_prior = float(
        included.loc[included["fiscal_year"].eq(compare_year), "amount"].sum()
        if compare_year is not None
        else 0.0
    )
    root = DrilldownNode(
        id="root",
        parent_id=None,
        level="citywide",
        label="Citywide approved budget",
        current=root_current,
        prior=root_prior,
        change=root_current - root_prior,
        percent_change=(root_current - root_prior) / root_prior * 100 if root_prior else None,
        line_items=int(included["fiscal_year"].eq(year).sum()),
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in included.itertuples(index=False):
        is_current = row.fiscal_year == year
        department = row.department or "Unspecified department"
        fund = row.fund or "Unspecified fund"
        category = row.category or "Unspecified category"
        parent = "root"
        for level, label in (("department", department), ("fund", fund), ("category", category)):
            node_id = f"{parent}::{level}::{_slug(label)}"
            item = grouped.setdefault(
                node_id,
                {
                    "id": node_id,
                    "parent_id": parent,
                    "level": level,
                    "label": label,
                    "current": 0.0,
                    "prior": 0.0,
                    "line_items": 0,
                },
            )
            item["current" if is_current else "prior"] += float(row.amount)
            if is_current:
                item["line_items"] += 1
            parent = node_id
    nodes: list[DrilldownNode] = []
    for item in grouped.values():
        change = item["current"] - item["prior"]
        nodes.append(
            DrilldownNode(
                id=item["id"],
                parent_id=item["parent_id"],
                level=item["level"],
                label=item["label"],
                current=item["current"],
                prior=item["prior"],
                change=change,
                percent_change=change / item["prior"] * 100 if item["prior"] else None,
                line_items=item["line_items"],
            )
        )
    nodes.sort(key=lambda node: (node.level, -node.current, node.label))
    return DrilldownModel(
        year=year,
        compare_year=compare_year,
        flow=flow,
        scope=scope,
        scope_label=FUND_SCOPE_LABELS[scope],
        root=root,
        nodes=tuple(nodes),
    )


def _annual_amounts(rows: pd.DataFrame, dimension: Dimension, flow: Flow, scope: Scope) -> pd.DataFrame:
    scoped = filter_rows(rows, flow=flow, scope=scope).copy()
    scoped[dimension] = scoped[dimension].fillna("").replace("", "Unspecified")
    return (
        scoped.groupby([dimension, "fiscal_year"], as_index=False)
        .agg(amount=("amount", "sum"))
        .sort_values([dimension, "fiscal_year"])
    )


def robust_change_signals(
    rows: pd.DataFrame,
    *,
    dimension: Dimension = "department",
    flow: Flow = "Expenses",
    scope: Scope = "all_funds",
    latest_year: int | None = None,
    minimum_history: int = 6,
    threshold: float = 3.5,
) -> pd.DataFrame:
    """Return review signals, never claims of causation or performance."""

    annual = _annual_amounts(rows, dimension, flow, scope)
    if annual.empty:
        return pd.DataFrame(columns=["entity", "current", "prior", "change", "modified_z", "reason"])
    latest = latest_year if latest_year is not None else int(annual["fiscal_year"].max())
    prior_year = latest - 1
    entities = sorted(annual[dimension].dropna().unique())
    records: list[dict[str, Any]] = []
    for entity in entities:
        series = annual.loc[annual[dimension].eq(entity)].set_index("fiscal_year")["amount"]
        current = float(series.get(latest, 0.0))
        prior = float(series.get(prior_year, 0.0))
        change = current - prior
        change_series = series.diff().dropna()
        historical = change_series.loc[change_series.index < latest]
        median = float(historical.median()) if len(historical) else 0.0
        mad = float(np.median(np.abs(historical.to_numpy() - median))) if len(historical) else 0.0
        enough_history = len(historical) >= minimum_history
        modified_z = (0.6745 * (change - median) / mad) if enough_history and mad else np.nan
        if not enough_history:
            formula = "suppressed: fewer than 6 historical changes"
            suppression_reason = "insufficient_history"
        elif not mad:
            formula = "suppressed: historical median absolute deviation is zero"
            suppression_reason = "zero_mad"
        else:
            formula = "modified_z = 0.6745 * (change - median(history)) / MAD(history)"
            suppression_reason = ""
        values = [float(series.get(year, 0.0)) for year in range(latest - 2, latest + 1)]
        directions = [np.sign(values[index] - values[index - 1]) for index in range(1, len(values))]
        reversal = (
            len(directions) == 2
            and directions[0] != 0
            and directions[1] != 0
            and directions[0] != directions[1]
        )
        persistence = len(directions) == 2 and directions[0] != 0 and directions[0] == directions[1]
        present_before = float(series.loc[series.index < latest].sum()) if not series.empty else 0.0
        newly_appeared = current != 0 and present_before == 0
        disappeared = current == 0 and prior != 0
        reasons: list[str] = []
        if not np.isnan(modified_z) and abs(modified_z) >= threshold:
            reasons.append("robust_change")
        if reversal:
            reasons.append("direction_reversal")
        if persistence:
            reasons.append("three_year_directional_persistence")
        if newly_appeared:
            reasons.append("newly_appearing_activity")
        if disappeared:
            reasons.append("disappearing_activity")
        records.append(
            {
                "entity": entity,
                "current": current,
                "prior": prior,
                "change": change,
                "modified_z": modified_z,
                "historical_changes": len(historical),
                "mad": mad,
                "annual_series": tuple((int(year), float(amount)) for year, amount in series.items()),
                "formula": formula,
                "suppression_reason": suppression_reason,
                "robust_flag": "robust_change" in reasons,
                "reversal": reversal,
                "persistence": persistence,
                "newly_appeared": newly_appeared,
                "disappeared": disappeared,
                "reason": ", ".join(reasons),
            }
        )
    result = pd.DataFrame.from_records(records)
    total_abs_change = float(result["change"].abs().sum())
    result["concentration_share"] = result["change"].abs() / total_abs_change if total_abs_change else 0.0
    result["concentrated"] = result["concentration_share"] >= CONCENTRATION_THRESHOLD
    result.loc[result["concentrated"], "reason"] = result.loc[result["concentrated"], "reason"].map(
        lambda value: f"{value}, concentrated_change" if value else "concentrated_change"
    )
    return result.sort_values("change", key=lambda values: values.abs(), ascending=False).reset_index(
        drop=True
    )


def validate_scenario(
    rows: pd.DataFrame,
    *,
    year: int,
    scope: Scope,
    adjustments: Mapping[str, float] | Sequence[tuple[str, float]],
    balanced: bool = True,
    flow: Flow = "Expenses",
) -> ScenarioValidation:
    """Validate hypothetical department deltas without changing source rows."""

    _assert_columns(rows)
    entries = list(adjustments.items()) if isinstance(adjustments, Mapping) else list(adjustments)
    errors: list[str] = []
    if len(entries) > 10:
        errors.append("A scenario may contain at most 10 department adjustments")
    cleaned: dict[str, float] = {}
    for name, delta in entries:
        try:
            value = float(delta)
        except (TypeError, ValueError):
            errors.append(f"Adjustment for {name!s} is not numeric")
            continue
        if not np.isfinite(value):
            errors.append(f"Adjustment for {name!s} is not finite")
            continue
        cleaned[str(name)] = value
    total_delta = float(sum(cleaned.values()))
    is_balanced = bool(np.isclose(total_delta, 0.0, atol=0.005))
    if balanced and not is_balanced:
        errors.append("Balanced scenarios must net to zero")
    base = filter_rows(rows, year=year, flow=flow, scope=scope)
    totals = base.groupby("department")["amount"].sum().to_dict()
    for department, delta in cleaned.items():
        if float(totals.get(department, 0.0)) + delta < -0.005:
            errors.append(f"Adjustment for {department} would create a negative allocation")
    adjusted = pd.DataFrame(
        [
            {
                "department": department,
                "base": float(totals.get(department, 0.0)),
                "delta": delta,
                "adjusted": float(totals.get(department, 0.0)) + delta,
            }
            for department, delta in cleaned.items()
        ]
    )
    return ScenarioValidation(not errors, is_balanced, total_delta, tuple(errors), adjusted)


def safe_csv_export(frame: pd.DataFrame) -> str:
    """Export a table while neutralizing spreadsheet formula injection."""

    safe = frame.copy()
    formula_prefixes = ("=", "+", "-", "@")
    for column in safe.columns:
        if pd.api.types.is_numeric_dtype(safe[column]):
            continue
        safe[column] = safe[column].map(
            lambda value: f"'{value}"
            if isinstance(value, str) and value.startswith(formula_prefixes)
            else value
        )
    output = io.StringIO(newline="")
    safe.to_csv(output, index=False, lineterminator="\n")
    return output.getvalue()


def to_safe_csv(frame: pd.DataFrame) -> str:
    return safe_csv_export(frame)


def build_snapshot(
    frame: pd.DataFrame,
    *,
    source_url: str,
    source_last_edit_date: int | None = None,
    generated_at: str | None = None,
    fetched_at: str | None = None,
    checked_at: str | None = None,
    prepared_at: str | None = None,
    schema_version: int = 1,
    content_hash: str = "",
    version: str = "",
    validation_results: Mapping[str, Any] | None = None,
) -> BudgetSnapshot:
    _assert_columns(frame)
    rows = frame.copy()
    years = tuple(sorted(int(value) for value in rows["fiscal_year"].unique()))
    overview = overview_totals(rows)
    latest_year = years[-1] if years else 0
    scopes = add_scope_column(rows)
    known = scopes.loc[scopes["fund_scope"].ne("unknown")]
    metadata = SnapshotMetadata(
        source_url=source_url,
        source_last_edit_date=source_last_edit_date,
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        fetched_at=fetched_at or datetime.now(UTC).isoformat(),
        row_count=len(rows),
        years=years,
        duplicate_object_ids=int(rows["object_id"].duplicated().sum()),
        blank_departments=int(rows["department"].eq("").sum()),
        blank_funds=int(rows["fund"].eq("").sum()),
        blank_categories=int(rows["category"].eq("").sum()),
        unknown_scopes=int(scopes["fund_scope"].eq("unknown").sum()),
        all_funds_expenses=float(rows.loc[rows["expense_revenue"].eq("Expenses"), "amount"].sum()),
        all_funds_revenues=float(rows.loc[rows["expense_revenue"].eq("Revenues"), "amount"].sum()),
        known_scope_expenses=float(known.loc[known["expense_revenue"].eq("Expenses"), "amount"].sum()),
        known_scope_revenues=float(known.loc[known["expense_revenue"].eq("Revenues"), "amount"].sum()),
        checked_at=checked_at,
        prepared_at=prepared_at,
        schema_version=schema_version,
        content_hash=content_hash,
        version=version,
        validation_results=validation_results or {},
    )
    return BudgetSnapshot(
        rows=rows,
        generated_at=metadata.generated_at,
        latest_year=latest_year,
        years=years,
        metadata=metadata,
        overview=overview,
    )
