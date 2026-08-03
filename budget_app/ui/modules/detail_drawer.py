"""Persistent accessible Overview detail drawer for the Sacramento budget story."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_widget

from budget_app.data import FUND_SCOPE_LABELS
from budget_app.state import VALID_PRESENTATION_LENSES, OverviewSelectionState

from ..components import (
    coerce_bundle,
    coerce_snapshot,
    empty_state,
    ensure_scope_column,
    format_currency,
    format_percent,
)

_REQUIRED_COLUMNS = {
    "fiscal_year",
    "department",
    "fund",
    "category",
    "amount",
    "expense_revenue",
    "fund_category",
    "object_id",
}
_DIMENSIONS = ("department", "fund", "category")
_DIMENSION_LABELS = {
    "department": "Department",
    "fund": "Fund",
    "category": "Category",
}

_FLOW_COPY = {
    "all": "combined approved authority",
    "revenue": "approved revenue",
    "expense": "approved expenses",
}
_FLOW_EYEBROW = {
    "all": "COMBINED APPROVED AUTHORITY",
    "revenue": "APPROVED REVENUE",
    "expense": "APPROVED EXPENSES",
}


@dataclass(frozen=True, slots=True)
class DetailPresentation:
    """Pure display contract for one analytical context and presentation lens."""

    lens: str
    eyebrow: str
    title: str
    context_prefix: str
    breadcrumb: str
    current_label: str
    comparison_label: str
    change_label: str
    change_explanation: str
    record_label: str
    record_detail: str
    trend_title: str
    trend_status: str
    trend_value_label: str
    annual_value_label: str
    annual_caption: str
    composition_copy: str
    exact_section_title: str
    exact_caption: str
    expand_target: str
    accent: str


def detail_presentation(
    state: OverviewSelectionState,
    lens: str = "authority",
) -> DetailPresentation:
    """Return deterministic drawer copy without reading reactive or source state."""

    safe_lens = lens if lens in VALID_PRESENTATION_LENSES else "authority"
    path = ["Citywide"]
    path.extend(str(getattr(state, dimension)) for dimension in _DIMENSIONS if getattr(state, dimension))
    if state.selected_record is not None:
        path.append(f"ObjectId {state.selected_record}")
    breadcrumb = " / ".join(path)
    if state.selected_record is not None:
        deepest = f"ObjectId {state.selected_record}"
    else:
        deepest = next(
            (str(getattr(state, dimension)) for dimension in reversed(_DIMENSIONS) if getattr(state, dimension)),
            None,
        )
    year_label = f"FY{state.year}" if state.year is not None else "Current fiscal year"
    scope_label = FUND_SCOPE_LABELS.get(state.fund_scope, state.fund_scope)

    if safe_lens == "net_position":
        eyebrow = "NET POSITION"
        title = f"{deepest} net position" if deepest else "Citywide net position"
        context_label = "Net position"
        current_label = "Current net position"
        comparison_label = "Comparison net position"
        change_label = "Change in net position"
        change_explanation = "Current net position less comparison net position"
        record_label = "Exact supporting records"
        record_detail = "Revenue and expense rows substantiate this net position"
        trend_title = "Annual net position"
        trend_status = "Preparing annual net position..."
        trend_value_label = "Net position"
        annual_value_label = "Exact net position"
        annual_caption = "Exact annual net position for the selected context."
        composition_copy = "Values are exact approved revenue and expense amounts in the current year."
        exact_section_title = "Supporting records for net position"
        exact_caption = "Exact revenue and expense records supporting the selected net position."
        expand_target = "records"
        accent = "net"
    elif safe_lens == "source_records":
        eyebrow = "SOURCE RECORDS"
        title = (
            f"{deepest} approved-budget source records"
            if deepest
            else f"{year_label} approved-budget source records"
        )
        context_label = "Matching source records"
        current_label = "Matching current-year rows"
        comparison_label = "Comparison matching rows"
        change_label = "Change in matching rows"
        change_explanation = "Current matching rows less comparison matching rows"
        record_label = "Revenue rows"
        record_detail = "Expense rows shown below"
        trend_title = "Annual matching source records"
        trend_status = "Preparing annual matching source records..."
        trend_value_label = "Matching records"
        annual_value_label = "Matching source records"
        annual_caption = "Exact annual matching source-record counts for the selected context."
        composition_copy = "Values are exact matching source-record counts in the current year."
        exact_section_title = "Matching source records"
        exact_caption = "Exact source records matching the selected fiscal year and hierarchy."
        expand_target = "records"
        accent = "records"
    else:
        flow = state.flow if state.flow in _FLOW_COPY else "all"
        flow_copy = _FLOW_COPY[flow]
        flow_eyebrow = _FLOW_EYEBROW[flow]
        if state.selected_record is not None:
            level_label = "EXACT RECORD"
        elif state.category:
            level_label = "CATEGORY"
        elif state.fund:
            level_label = "FUND"
        elif state.department:
            level_label = "DEPARTMENT"
        elif state.fund_scope != "all_funds":
            level_label = "FUND SCOPE"
        else:
            level_label = "CITYWIDE"
        eyebrow = f"{level_label} | {flow_eyebrow}"
        if deepest:
            title = deepest
        elif state.fund_scope != "all_funds":
            title = f"{scope_label} {flow_copy}"
        else:
            title = f"Citywide {flow_copy}"
        context_label = flow_copy.capitalize()
        current_label = f"Current {flow_copy}"
        comparison_label = f"Comparison {flow_copy}"
        change_label = f"Change in {flow_copy}"
        change_explanation = "Current less comparison"
        record_label = "Exact records"
        record_detail = "Matching current-year rows"
        trend_title = f"Historical {flow_copy}"
        trend_status = f"Preparing historical {flow_copy}..."
        trend_value_label = flow_copy.capitalize()
        annual_value_label = f"Exact {flow_copy}"
        annual_caption = f"Exact annual {flow_copy} for the selected context."
        composition_copy = "Values are exact approved amounts in the current year."
        exact_section_title = "Exact supporting records"
        exact_caption = "Exact approved records matching the selected fiscal year and hierarchy."
        expand_target = "workspace"
        accent = "revenue" if flow == "revenue" else "expense" if flow == "expense" else "authority"

    return DetailPresentation(
        lens=safe_lens,
        eyebrow=eyebrow,
        title=title,
        context_prefix=f"{year_label} | {context_label} | {scope_label}",
        breadcrumb=breadcrumb,
        current_label=current_label,
        comparison_label=comparison_label,
        change_label=change_label,
        change_explanation=change_explanation,
        record_label=record_label,
        record_detail=record_detail,
        trend_title=trend_title,
        trend_status=trend_status,
        trend_value_label=trend_value_label,
        annual_value_label=annual_value_label,
        annual_caption=annual_caption,
        composition_copy=composition_copy,
        exact_section_title=exact_section_title,
        exact_caption=exact_caption,
        expand_target=expand_target,
        accent=accent,
    )


@module.ui
def detail_drawer_ui(id: str = "detail") -> Any:
    """Render one stable drawer shell. Server outputs fill its content slots."""

    ns = module.resolve_id(id)

    def action(name: str, label: str, *, class_: str, **attrs: Any) -> Any:
        return ui.input_action_button(name, label, class_=class_, **attrs)

    def metric(label_id: str, output_id: str, detail_id: str, *, tone: str) -> Any:
        return ui.div(
            ui.span(ui.output_text(label_id, inline=True), class_="city-stat-card__label"),
            ui.span(ui.output_text(output_id, inline=True), class_="city-stat-card__value tabular"),
            ui.span(ui.output_text(detail_id, inline=True), class_="city-stat-card__detail"),
            class_=f"city-stat-card city-stat-card--{tone}",
        )

    return ui.div(
        action(
            "backdrop",
            "",
            class_="city-detail-backdrop",
            data_detail_backdrop="true",
            aria_label="Close budget detail",
        ),
        ui.tags.aside(
            ui.div(
                ui.div(
                    ui.div(ui.output_text("eyebrow", inline=True), class_="city-eyebrow"),
                    ui.h2(
                        ui.output_text("title_text", inline=True),
                        id=ns("title"),
                        class_="city-detail-drawer__title",
                    ),
                    ui.p(
                        ui.output_text("context_summary", inline=True),
                        class_="city-detail-drawer__context",
                    ),
                    ui.p(
                        ui.output_text("breadcrumb", inline=True),
                        class_="city-breadcrumbs",
                        aria_live="polite",
                    ),
                    ui.div(
                        "",
                        class_="sr-only",
                        role="status",
                        aria_live="polite",
                        data_detail_client_status="true",
                    ),
                    ui.output_ui("content_status"),
                    class_="city-detail-drawer__heading",
                ),
                action(
                    "close",
                    "Close",
                    class_="city-button city-button--secondary",
                    data_detail_close="true",
                ),
                class_="city-detail-drawer__header city-detail-header",
            ),
            ui.div(
                ui.div(
                    metric("current_label", "current_total", "current_detail", tone="cobalt"),
                    metric("comparison_label", "compare_total", "compare_detail", tone="sky"),
                    ui.div(
                        ui.span(ui.output_text("change_label", inline=True), class_="city-stat-card__label"),
                        ui.span(
                            ui.output_text("change_amount", inline=True),
                            class_="city-stat-card__value tabular city-detail-change__amount",
                        ),
                        ui.span(
                            ui.output_text("change_percent", inline=True),
                            class_="city-stat-card__detail city-detail-change__percent",
                        ),
                        ui.span(
                            ui.output_text("change_explanation", inline=True),
                            class_="city-detail-change__explanation",
                        ),
                        class_="city-stat-card city-stat-card--gold city-detail-change",
                    ),
                    metric("record_label", "record_count", "record_count_detail", tone="green"),
                    class_="city-grid city-grid--2 city-detail-kpis city-detail-metrics",
                ),
                ui.div(
                    ui.h3(ui.output_text("trend_title", inline=True), class_="city-card-heading"),
                    ui.div(
                        ui.output_ui("trend_state"),
                        output_widget("trend", height="240px"),
                        class_="city-detail-trend",
                    ),
                    ui.output_ui("annual_table"),
                    ui.p(ui.output_text("trend_caption", inline=True), class_="city-chart-summary"),
                    class_="city-surface city-surface--outlined city-chart-frame",
                ),
                ui.div(
                    ui.h3("Composition", class_="city-card-heading"),
                    ui.output_ui("composition"),
                    class_="city-surface city-surface--panel",
                ),
                ui.div(
                    ui.h3(ui.output_text("exact_section_title", inline=True), class_="city-card-heading"),
                    ui.output_ui("record_detail"),
                    ui.output_ui("exact_table"),
                    class_="city-surface city-surface--outlined",
                ),
                class_="city-detail-drawer__body",
            ),
            ui.div(
                action("back", "Back", class_="city-button city-button--secondary", data_detail_back="true"),
                action(
                    "inspect",
                    "Inspect records",
                    class_="city-button",
                    data_detail_inspect="true",
                ),
                action(
                    "expand",
                    "Expand analysis",
                    class_="city-button city-button--secondary",
                    data_detail_expand="true",
                ),
                action(
                    "copy",
                    "Copy state",
                    class_="city-button city-button--secondary",
                    data_detail_copy="true",
                ),
                action(
                    "clear",
                    "Clear selection",
                    class_="city-button city-button--quiet",
                    data_detail_clear="true",
                ),
                action(
                    "close_footer",
                    "Close",
                    class_="city-button city-button--secondary",
                    data_detail_close="true",
                ),
                class_="city-detail-drawer__actions city-detail-actions",
            ),
            id=ns("drawer"),
            role="dialog",
            aria_modal="true",
            aria_labelledby=ns("title"),
            aria_hidden="true",
            class_="city-detail-drawer",
            data_detail_drawer="true",
        ),
        id=ns("overlay"),
        class_="city-detail-overlay",
        data_detail_overlay="true",
        data_detail_lifecycle="closed",
        data_detail_content_state="idle",
        aria_hidden="true",
    )


def _safe_frame(snapshot: Any) -> pd.DataFrame:
    value = coerce_snapshot(snapshot)
    if value.empty or not _REQUIRED_COLUMNS.issubset(value.columns):
        return pd.DataFrame()
    return value


def _flow_rows(value: pd.DataFrame, flow: str) -> pd.DataFrame:
    if value.empty:
        return value
    if flow == "revenue":
        return value.loc[value["expense_revenue"].eq("Revenues")]
    if flow == "expense":
        return value.loc[value["expense_revenue"].eq("Expenses")]
    return value


def _scope_rows(value: pd.DataFrame, scope: str) -> pd.DataFrame:
    if value.empty or scope in {"", "all", "all_funds"}:
        return value
    try:
        scoped = ensure_scope_column(value)
    except (KeyError, TypeError, ValueError):
        return pd.DataFrame()
    return scoped.loc[scoped["fund_scope"].eq(scope)]


def _hierarchy_rows(value: pd.DataFrame, state: OverviewSelectionState) -> pd.DataFrame:
    result = value
    for dimension in _DIMENSIONS:
        selected = getattr(state, dimension)
        if selected:
            result = result.loc[result[dimension].astype(str).eq(str(selected))]
    return result


def _year_rows(value: pd.DataFrame, year: int | None) -> pd.DataFrame:
    if value.empty or year is None:
        return value
    return value.loc[value["fiscal_year"].eq(int(year))]


def _breadcrumb(state: OverviewSelectionState) -> str:
    labels = ["Citywide"]
    labels.extend(str(getattr(state, dimension)) for dimension in _DIMENSIONS if getattr(state, dimension))
    return " / ".join(labels)


def _next_dimension(state: OverviewSelectionState) -> str | None:
    for dimension in _DIMENSIONS:
        if not getattr(state, dimension):
            return dimension
    return None


@module.server
def detail_drawer_server(
    input: Any,
    output: Any,
    session: Any,
    snapshot: Any,
    selection: reactive.Value[OverviewSelectionState],
    drawer_desired_open: reactive.Value[bool],
    presentation_lens: reactive.Value[str],
    context_callback: Callable[[OverviewSelectionState], Any],
    expand_callback: Callable[[str], Any] | None = None,
    close_callback: Callable[[], Any] | None = None,
) -> None:
    """Operate static drawer content from the last explicit detail context."""

    @reactive.calc
    def frame() -> pd.DataFrame:
        return _safe_frame(snapshot() if callable(snapshot) else snapshot)

    @reactive.calc
    def bundle() -> Any:
        return coerce_bundle(snapshot)

    @reactive.calc
    def context_rows() -> pd.DataFrame:
        state = selection()
        value = _scope_rows(frame(), state.fund_scope)
        return _hierarchy_rows(value, state).copy()

    @reactive.calc
    def filtered_rows() -> pd.DataFrame:
        state = selection()
        return _flow_rows(context_rows(), state.flow).copy()

    @reactive.calc
    def current_rows() -> pd.DataFrame:
        return _year_rows(filtered_rows(), selection().year).copy()

    @reactive.calc
    def comparison_rows() -> pd.DataFrame:
        return _year_rows(filtered_rows(), selection().compare_year).copy()

    @reactive.calc
    def historical_summary() -> pd.DataFrame:
        """Return one cached annual table for amounts and row-count lenses."""

        state = selection()
        current_bundle = bundle()
        if current_bundle is not None and not any(
            (state.department, state.fund, state.category)
        ):
            value = current_bundle.aggregate("totals_by_year_flow_scope")
            value = value.loc[value["fund_scope"].eq(state.fund_scope)].copy()
            if value.empty:
                return pd.DataFrame(
                    columns=[
                        "fiscal_year",
                        "approved_revenue",
                        "approved_expenses",
                        "combined_authority",
                        "net_position",
                        "matching_records",
                        "revenue_records",
                        "expense_records",
                    ]
                )
            value["approved_revenue"] = value["amount"].where(
                value["expense_revenue"].eq("Revenues"), 0.0
            )
            value["approved_expenses"] = value["amount"].where(
                value["expense_revenue"].eq("Expenses"), 0.0
            )
            value["revenue_records"] = value["line_items"].where(
                value["expense_revenue"].eq("Revenues"), 0
            )
            value["expense_records"] = value["line_items"].where(
                value["expense_revenue"].eq("Expenses"), 0
            )
            summary = (
                value.groupby("fiscal_year", as_index=False)[
                    ["approved_revenue", "approved_expenses", "revenue_records", "expense_records"]
                ]
                .sum()
                .sort_values("fiscal_year")
            )
        else:
            value = context_rows()
            if value.empty:
                return pd.DataFrame(
                    columns=[
                        "fiscal_year",
                        "approved_revenue",
                        "approved_expenses",
                        "combined_authority",
                        "net_position",
                        "matching_records",
                        "revenue_records",
                        "expense_records",
                    ]
                )
            value = value.assign(
                approved_revenue=value["amount"].where(value["expense_revenue"].eq("Revenues"), 0.0),
                approved_expenses=value["amount"].where(value["expense_revenue"].eq("Expenses"), 0.0),
                revenue_records=value["expense_revenue"].eq("Revenues").astype(int),
                expense_records=value["expense_revenue"].eq("Expenses").astype(int),
            )
            summary = (
                value.groupby("fiscal_year", as_index=False)
                .agg(
                    approved_revenue=("approved_revenue", "sum"),
                    approved_expenses=("approved_expenses", "sum"),
                    revenue_records=("revenue_records", "sum"),
                    expense_records=("expense_records", "sum"),
                    matching_records=("object_id", "size"),
                )
                .sort_values("fiscal_year")
            )
        summary["matching_records"] = summary["revenue_records"] + summary["expense_records"]
        summary["combined_authority"] = summary["approved_revenue"] + summary["approved_expenses"]
        summary["net_position"] = summary["approved_revenue"] - summary["approved_expenses"]
        return summary.reset_index(drop=True)

    @reactive.calc
    def selected_record_rows() -> pd.DataFrame:
        record = selection().selected_record
        if record is None:
            return pd.DataFrame()
        current_bundle = bundle()
        if current_bundle is not None:
            return current_bundle.exact_rows(int(record))
        value = filtered_rows()
        if value.empty:
            return value
        return value.loc[value["object_id"].eq(int(record))].copy()

    def _content_key() -> tuple[Any, ...]:
        state = selection()
        return (
            state.year,
            state.compare_year,
            state.flow,
            state.fund_scope,
            state.department,
            state.fund,
            state.category,
            state.selected_record,
            presentation_lens(),
        )

    trend_ready_key = reactive.Value[tuple[Any, ...] | None](None)
    heavy_ready_key = reactive.Value[tuple[Any, ...] | None](None)
    lifecycle_generation = 0

    def _summary_ready() -> bool:
        return drawer_desired_open()

    def _heavy_ready() -> bool:
        return heavy_ready_key.get() == _content_key()

    def _set_context(value: OverviewSelectionState) -> None:
        if selection.get() == value:
            return
        result = context_callback(value)
        if inspect.isawaitable(result):
            raise RuntimeError("The detail context callback must be synchronous")

    async def _notify_closed() -> None:
        if close_callback is None:
            return
        result = close_callback()
        if inspect.isawaitable(result):
            await result

    async def _close_drawer() -> bool:
        if not drawer_desired_open.get():
            return False
        drawer_desired_open.set(False)
        await _notify_closed()
        return True

    def _summary_row(year: int | None) -> pd.Series | None:
        if year is None:
            return None
        value = historical_summary()
        matches = value.loc[value["fiscal_year"].eq(int(year))]
        return matches.iloc[0] if not matches.empty else None

    def _summary_metric(row: pd.Series | None, state: OverviewSelectionState, view: DetailPresentation) -> float:
        if row is None:
            return 0.0
        if view.lens == "net_position":
            return float(row["net_position"])
        if view.lens == "source_records":
            return float(row["matching_records"])
        if state.flow == "revenue":
            return float(row["approved_revenue"])
        if state.flow == "expense":
            return float(row["approved_expenses"])
        return float(row["combined_authority"])

    def _summary_count(row: pd.Series | None, state: OverviewSelectionState, view: DetailPresentation) -> int:
        if row is None:
            return 0
        if view.lens in {"net_position", "source_records"} or state.flow == "all":
            return int(row["matching_records"])
        key = "revenue_records" if state.flow == "revenue" else "expense_records"
        return int(row[key])

    def _supporting_counts(row: pd.Series | None) -> tuple[int, int]:
        if row is None:
            return 0, 0
        return int(row["revenue_records"]), int(row["expense_records"])

    def _change_values() -> tuple[float, float, float, float | None]:
        state = selection()
        view = detail_presentation(state, presentation_lens())
        current_total = _summary_metric(_summary_row(state.year), state, view)
        compare_total = _summary_metric(_summary_row(state.compare_year), state, view)
        change = current_total - compare_total
        percent = change / compare_total * 100 if compare_total else None
        return current_total, compare_total, change, percent

    def _display_metric(value: float, view: DetailPresentation) -> str:
        if view.lens == "source_records":
            return f"{int(round(value)):,}"
        return format_currency(value, compact=True)

    def _composition() -> Any:
        if not _heavy_ready():
            return ui.div(
                ui.div(class_="city-spinner", aria_hidden="true"),
                "Preparing composition detail...",
                class_="city-detail-trend__status city-detail-trend__status--loading",
                role="status",
                aria_live="polite",
            )
        state = selection()
        view = detail_presentation(state, presentation_lens())
        dimension = _next_dimension(state)
        value = current_rows()
        if dimension is None:
            return ui.p("The selected category is the deepest available hierarchy level.")
        if value.empty:
            return empty_state(
                "No composition is available",
                "No exact approved records match the current hierarchy and year.",
            )
        if view.lens == "source_records":
            grouped = value.groupby(dimension, dropna=False).size().sort_values(ascending=False).head(12)
        else:
            values = value["amount"]
            if view.lens == "net_position":
                values = values.where(value["expense_revenue"].eq("Revenues"), -values)
            grouped = (
                value.assign(_presentation_amount=values)
                .groupby(dimension, dropna=False)["_presentation_amount"]
                .sum()
                .sort_values(key=lambda values: values.abs(), ascending=False)
                .head(12)
            )
        items = []
        for label, amount in grouped.items():
            display = (
                str(label)
                if pd.notna(label) and str(label).strip()
                else f"Unknown {_DIMENSION_LABELS[dimension].lower()}"
            )
            display_value = (
                f"{int(amount):,} records"
                if view.lens == "source_records"
                else format_currency(amount, compact=True)
            )
            items.append(
                ui.tags.li(
                    ui.span(display, class_="city-detail-composition__label"),
                    ui.span(display_value, class_="city-detail-composition__value tabular"),
                    class_="city-detail-composition__item",
                )
            )
        return ui.div(
            ui.p(
                f"Next level: {_DIMENSION_LABELS[dimension]}. {view.composition_copy}",
                class_="city-detail-copy",
            ),
            ui.tags.ul(*items, class_="city-detail-composition"),
        )

    def _exact_table() -> Any:
        if not _heavy_ready():
            return ui.div(
                "Preparing exact approved records...",
                class_="city-detail-empty city-detail-copy",
                role="status",
                aria_live="polite",
            )
        view = detail_presentation(selection(), presentation_lens())
        value = current_rows().copy()
        columns = (
            ("fiscal_year", "Fiscal year"),
            ("department", "Department"),
            ("fund", "Fund"),
            ("category", "Category"),
            ("amount", "Amount"),
            ("expense_revenue", "Revenue or expense"),
            ("object_id", "ObjectId"),
        )
        if value.empty:
            return ui.div(
                ui.p("No exact records match the current hierarchy and year."),
                class_="city-detail-empty city-detail-copy",
                role="status",
            )
        rows = []
        for record in value.head(100).itertuples(index=False):
            cells = []
            for key, _label in columns:
                cell = getattr(record, key)
                text = format_currency(cell) if key == "amount" else str(cell)
                cells.append(ui.tags.td(text))
            rows.append(ui.tags.tr(*cells))
        header = ui.tags.tr(*(ui.tags.th(label, scope="col") for _key, label in columns))
        return ui.div(
            ui.tags.table(
                ui.tags.caption(
                    f"{view.exact_caption} Showing {min(len(value), 100):,} of {len(value):,} matching rows."
                ),
                ui.tags.thead(header),
                ui.tags.tbody(*rows),
                class_="city-detail-table",
            ),
            class_="city-table-wrap",
        )

    def _annual_table() -> Any:
        if not _heavy_ready():
            return ui.tags.details(
                ui.tags.summary("Show exact annual values"),
                ui.p("Preparing exact annual values...", role="status"),
                class_="city-detail-annual",
            )
        view = detail_presentation(selection(), presentation_lens())
        value = historical_summary()
        if view.lens == "source_records":
            metric_column = "matching_records"
        elif view.lens == "net_position":
            metric_column = "net_position"
        elif selection().flow == "revenue":
            metric_column = "approved_revenue"
        elif selection().flow == "expense":
            metric_column = "approved_expenses"
        else:
            metric_column = "combined_authority"
        if value.empty:
            table = ui.tags.table(
                ui.tags.caption(f"No exact annual {view.trend_value_label.lower()} are available."),
                ui.tags.thead(
                    ui.tags.tr(
                        ui.tags.th("Fiscal year", scope="col"),
                        ui.tags.th(view.annual_value_label, scope="col"),
                    )
                ),
                ui.tags.tbody(ui.tags.tr(ui.tags.td("No matching records"), ui.tags.td("Not available"))),
                class_="city-exact-table",
            )
        else:
            rows = [
                ui.tags.tr(
                    ui.tags.td(f"FY{int(record.fiscal_year)}"),
                    ui.tags.td(
                        f"{int(getattr(record, metric_column)):,}"
                        if view.lens == "source_records"
                        else format_currency(getattr(record, metric_column))
                    ),
                )
                for record in value.itertuples(index=False)
            ]
            table = ui.tags.table(
                ui.tags.caption(view.annual_caption),
                ui.tags.thead(
                    ui.tags.tr(
                        ui.tags.th("Fiscal year", scope="col"),
                        ui.tags.th(view.annual_value_label, scope="col"),
                    )
                ),
                ui.tags.tbody(*rows),
                class_="city-exact-table",
            )
        return ui.tags.details(
            ui.tags.summary("Show exact annual values"),
            table,
            class_="city-detail-annual",
        )

    def _record_detail() -> Any:
        if not _heavy_ready():
            return ui.p("Preparing exact record detail...", class_="city-detail-copy", role="status")
        value = selected_record_rows()
        if value.empty:
            return ui.p(
                "Select an exact record from the table to see its ObjectId detail.",
                class_="city-detail-copy",
            )
        row = value.iloc[0]
        if "fund_scope" in value.columns:
            fund_scope = row["fund_scope"]
        else:
            fund_scope = ensure_scope_column(value.iloc[[0]]).iloc[0]["fund_scope"]
        return ui.div(
            ui.h3(f"ObjectId {int(row['object_id'])}", class_="city-card-heading"),
            ui.p(
                f"{row['department']} / {row['fund']} / {row['category']}: "
                f"{format_currency(row['amount'])} ({row['expense_revenue']})."
            ),
            ui.p(
                f"Fiscal year FY{int(row['fiscal_year'])}. Fund scope: {FUND_SCOPE_LABELS.get(fund_scope, fund_scope)}."
            ),
            class_="city-detail-copy",
        )

    def trend() -> Any:
        if not _heavy_ready():
            # Keep the hidden persistent shell free of an empty Plotly widget.
            # The visible status region carries the progressive loading state.
            return None
        trend_key = _content_key()
        state = selection()
        view = detail_presentation(state, presentation_lens())
        summary = historical_summary()
        if view.lens == "source_records":
            metric_column = "matching_records"
            hover_template = "FY%{x}<br>%{y:,.0f} matching records<extra></extra>"
        elif view.lens == "net_position":
            metric_column = "net_position"
            hover_template = "FY%{x}<br>$%{y:,.0f} net position<extra></extra>"
        elif state.flow == "revenue":
            metric_column = "approved_revenue"
            hover_template = "FY%{x}<br>$%{y:,.0f} approved revenue<extra></extra>"
        elif state.flow == "expense":
            metric_column = "approved_expenses"
            hover_template = "FY%{x}<br>$%{y:,.0f} approved expenses<extra></extra>"
        else:
            metric_column = "combined_authority"
            hover_template = "FY%{x}<br>$%{y:,.0f} combined authority<extra></extra>"
        value = summary[["fiscal_year", metric_column]].rename(columns={metric_column: "metric"})
        if value.empty:
            trend_ready_key.set(trend_key)
            return go.FigureWidget()
        figure = go.FigureWidget(
            go.Scatter(
                x=value["fiscal_year"].astype(str),
                y=value["metric"],
                mode="lines+markers",
                line=dict(color="#0072ce", width=3),
                marker=dict(color="#003c71", size=7),
                hovertemplate=hover_template,
                name=view.trend_value_label,
            )
        )
        figure.update_layout(
            margin=dict(l=12, r=12, t=8, b=32),
            height=240,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", color="#0f172a"),
            xaxis=dict(title=None, automargin=True),
            yaxis=dict(
                title=None,
                tickprefix="" if view.lens == "source_records" else "$",
                separatethousands=True,
                gridcolor="#e2e6ed",
            ),
            showlegend=False,
        )
        trend_ready_key.set(trend_key)
        return figure

    def trend_state() -> Any:
        view = detail_presentation(selection(), presentation_lens())
        if not _heavy_ready():
            return ui.div(
                ui.div(class_="city-spinner", aria_hidden="true"),
                view.trend_status,
                class_="city-detail-trend__status city-detail-trend__status--loading",
                role="status",
                aria_live="polite",
            )
        value = historical_summary()
        if value.empty:
            return ui.div(
                f"No historical {view.trend_value_label.lower()} are available for this selection.",
                class_="city-detail-trend__status",
                role="status",
            )
        if trend_ready_key.get() != _content_key():
            return ui.div(
                ui.div(class_="city-spinner", aria_hidden="true"),
                f"Updating {view.trend_value_label.lower()}...",
                class_="city-detail-trend__status city-detail-trend__status--loading",
                role="status",
                aria_live="polite",
            )
        return None

    def content_status() -> Any:
        if not drawer_desired_open():
            return ui.div("", class_="sr-only", role="status", aria_live="polite")
        if trend_ready_key.get() != _content_key():
            return ui.div(
                "Updating budget detail.",
                class_="sr-only",
                role="status",
                aria_live="polite",
            )
        return ui.div("Budget detail ready.", class_="sr-only", role="status", aria_live="polite")

    def eyebrow() -> str:
        return detail_presentation(selection(), presentation_lens()).eyebrow

    def title_text() -> str:
        return detail_presentation(selection(), presentation_lens()).title

    def context_summary() -> str:
        if not _summary_ready():
            return ""
        state = selection()
        view = detail_presentation(state, presentation_lens())
        row = _summary_row(state.year)
        if row is None:
            return view.context_prefix
        current_metric = _summary_metric(row, state, view)
        current_count = _summary_count(row, state, view)
        revenue = float(row["approved_revenue"])
        expenses = float(row["approved_expenses"])
        revenue_count, expense_count = _supporting_counts(row)
        if view.lens == "net_position":
            return (
                f"{view.context_prefix} | {format_currency(current_metric, compact=True)} | "
                f"Revenue {format_currency(revenue, compact=True)} | "
                f"Expenses {format_currency(expenses, compact=True)} | {current_count:,} records"
            )
        if view.lens == "source_records":
            return (
                f"{view.context_prefix} | {current_count:,} matching rows | "
                f"Revenue rows {revenue_count:,} | Expense rows {expense_count:,}"
            )
        return f"{view.context_prefix} | {format_currency(current_metric, compact=True)} | {current_count:,} records"

    def breadcrumb() -> str:
        return detail_presentation(selection(), presentation_lens()).breadcrumb

    def current_label() -> str:
        return detail_presentation(selection(), presentation_lens()).current_label

    def comparison_label() -> str:
        return detail_presentation(selection(), presentation_lens()).comparison_label

    def change_label() -> str:
        return detail_presentation(selection(), presentation_lens()).change_label

    def record_label() -> str:
        return detail_presentation(selection(), presentation_lens()).record_label

    def trend_title() -> str:
        return detail_presentation(selection(), presentation_lens()).trend_title

    def trend_caption() -> str:
        view = detail_presentation(selection(), presentation_lens())
        return f"{view.annual_caption} Approved budget authority is not actual spending or a forecast."

    def exact_section_title() -> str:
        return detail_presentation(selection(), presentation_lens()).exact_section_title

    def current_total() -> str:
        if not _summary_ready():
            return ""
        return _display_metric(_change_values()[0], detail_presentation(selection(), presentation_lens()))

    def current_detail() -> str:
        if not _summary_ready():
            return ""
        state = selection()
        view = detail_presentation(state, presentation_lens())
        row = _summary_row(state.year)
        revenue_count, expense_count = _supporting_counts(row)
        if view.lens == "source_records":
            return f"Revenue rows: {revenue_count:,} | Expense rows: {expense_count:,}"
        if view.lens == "net_position" and row is not None:
            return (
                f"Revenue {format_currency(row['approved_revenue'], compact=True)} | "
                f"Expenses {format_currency(row['approved_expenses'], compact=True)}"
            )
        count = _summary_count(row, state, view)
        return f"FY{state.year} | {count:,} records" if state.year is not None else f"{count:,} records"

    def compare_total() -> str:
        if not _summary_ready():
            return ""
        return _display_metric(_change_values()[1], detail_presentation(selection(), presentation_lens()))

    def compare_detail() -> str:
        if not _summary_ready():
            return ""
        state = selection()
        view = detail_presentation(state, presentation_lens())
        row = _summary_row(state.compare_year)
        revenue_count, expense_count = _supporting_counts(row)
        if view.lens == "source_records":
            return f"Revenue rows: {revenue_count:,} | Expense rows: {expense_count:,}"
        if view.lens == "net_position" and row is not None:
            return (
                f"Revenue {format_currency(row['approved_revenue'], compact=True)} | "
                f"Expenses {format_currency(row['approved_expenses'], compact=True)}"
            )
        count = _summary_count(row, state, view)
        return (
            f"FY{state.compare_year} | {count:,} records"
            if state.compare_year is not None
            else f"{count:,} records"
        )

    def change_amount() -> str:
        if not _summary_ready():
            return ""
        return _display_metric(_change_values()[2], detail_presentation(selection(), presentation_lens()))

    def change_percent() -> str:
        if not _summary_ready():
            return ""
        percent = _change_values()[3]
        return format_percent(percent) if percent is not None else "Percentage unavailable"

    def change_explanation() -> str:
        return detail_presentation(selection(), presentation_lens()).change_explanation if _summary_ready() else ""

    def record_count() -> str:
        if not _summary_ready():
            return ""
        state = selection()
        view = detail_presentation(state, presentation_lens())
        row = _summary_row(state.year)
        if view.lens == "source_records":
            revenue_count, _expense_count = _supporting_counts(row)
            return f"{revenue_count:,}"
        return f"{_summary_count(row, state, view):,}"

    def record_count_detail() -> str:
        if not _summary_ready():
            return ""
        state = selection()
        view = detail_presentation(state, presentation_lens())
        row = _summary_row(state.year)
        revenue_count, expense_count = _supporting_counts(row)
        if view.lens in {"net_position", "source_records"}:
            return f"Revenue rows: {revenue_count:,} | Expense rows: {expense_count:,}"
        return view.record_detail

    heavy_request_key: tuple[Any, ...] | None = None

    @reactive.effect
    def _defer_heavy_content() -> None:
        """Move Plotly and exact-record work into a timer-driven follow-up flush."""

        nonlocal heavy_request_key
        if not drawer_desired_open():
            heavy_request_key = None
            return

        key = _content_key()
        if heavy_ready_key.get() == key:
            heavy_request_key = None
            return
        if heavy_request_key != key:
            heavy_request_key = key
            # Keep the shell responsive to an immediate close before Plotly and
            # exact-record outputs begin their heavier follow-up render.
            reactive.invalidate_later(0.35, session=session)
            return

        heavy_request_key = None
        heavy_ready_key.set(key)

    @reactive.effect
    async def _sync_lifecycle() -> None:
        nonlocal lifecycle_generation
        desired_open = drawer_desired_open()
        lifecycle_generation += 1
        await session.send_custom_message(
            "budget-detail-lifecycle",
            {
                "open": desired_open,
                "generation": lifecycle_generation,
                "content_key": "|".join("" if value is None else str(value) for value in _content_key()),
                "content_state": "loading" if desired_open else "idle",
                "title": title_text() if desired_open else "",
                "lens": presentation_lens() if desired_open else "authority",
                "accent": detail_presentation(selection(), presentation_lens()).accent
                if desired_open
                else "authority",
            },
        )

    @reactive.effect
    @reactive.event(input.close, input.close_footer, input.backdrop)
    async def _close() -> None:
        await _close_drawer()

    @reactive.effect
    @reactive.event(input.back)
    def _back() -> None:
        if not drawer_desired_open.get():
            return
        presentation_lens.set("authority")
        state = selection.get()
        changes: dict[str, Any] = {"selected_record": None}
        if state.selected_record is None:
            if state.category:
                changes["category"] = None
            elif state.fund:
                changes["fund"] = None
            elif state.department:
                changes["department"] = None
        _set_context(state.updated(**changes))

    @reactive.effect
    @reactive.event(input.clear)
    async def _clear() -> None:
        if not drawer_desired_open.get():
            return
        presentation_lens.set("authority")
        _set_context(
            selection.get().updated(
                department=None,
                fund=None,
                category=None,
                selected_record=None,
            )
        )
        await _close_drawer()

    async def _expand(kind: str) -> None:
        if not await _close_drawer():
            return
        if expand_callback:
            result = expand_callback(kind)
            if inspect.isawaitable(result):
                await result

    @reactive.effect
    @reactive.event(input.expand)
    async def _expand_analysis() -> None:
        await _expand(detail_presentation(selection(), presentation_lens()).expand_target)

    @reactive.effect
    @reactive.event(input.inspect)
    async def _inspect_records() -> None:
        await _expand("records")

    @reactive.effect
    @reactive.event(input.copy)
    async def _copy_state() -> None:
        await session.bookmark.do_bookmark()

    output(render.text(eyebrow), id="eyebrow")
    output(render.text(title_text), id="title_text")
    output(render.text(context_summary), id="context_summary")
    output(render.text(breadcrumb), id="breadcrumb")
    output(render.text(current_label), id="current_label")
    output(render.text(comparison_label), id="comparison_label")
    output(render.text(change_label), id="change_label")
    output(render.text(record_label), id="record_label")
    output(render.text(trend_title), id="trend_title")
    output(render.text(trend_caption), id="trend_caption")
    output(render.text(exact_section_title), id="exact_section_title")
    output(render.text(current_total), id="current_total")
    output(render.text(current_detail), id="current_detail")
    output(render.text(compare_total), id="compare_total")
    output(render.text(compare_detail), id="compare_detail")
    output(render.text(change_amount), id="change_amount")
    output(render.text(change_percent), id="change_percent")
    output(render.text(change_explanation), id="change_explanation")
    output(render.text(record_count), id="record_count")
    output(render.text(record_count_detail), id="record_count_detail")
    output(render_widget(trend), id="trend")
    output(render.ui(trend_state), id="trend_state")
    output(render.ui(content_status), id="content_status")
    output(render.ui(_annual_table), id="annual_table")
    output(render.ui(_composition), id="composition")
    output(render.ui(_record_detail), id="record_detail")
    output(render.ui(_exact_table), id="exact_table")
