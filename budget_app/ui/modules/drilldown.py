"""Hierarchical citywide to department to fund drilldown module."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_widget

from budget_app.data import FUND_SCOPE_LABELS

from ..components import (
    chart_frame,
    coerce_snapshot,
    column,
    empty_state,
    ensure_scope_column,
    format_currency,
    section_header,
    unique_options,
    years,
)
from ..shell import page_intro, page_section


def _value(frame: pd.DataFrame, key: str, *aliases: str) -> str | None:
    return column(frame, key, *aliases)


@module.ui
def drilldown_ui(id: str = "drilldown") -> Any:
    return page_section(
        page_intro(
            "Follow the budget into the details",
            "Move from a citywide total to a department, fund, and category. Every visual is paired with exact supporting records.",
            eyebrow_text="Overview to drilldown",
        ),
        ui.div(
            ui.div(
                ui.input_select("department", "Department", {"all": "All departments"}), class_="city-control"
            ),
            ui.div(ui.input_select("fund", "Fund", {"all": "All funds"}), class_="city-control"),
            ui.div(ui.input_select("category", "Category", {"all": "All categories"}), class_="city-control"),
            ui.div(
                ui.input_select("year", "Fiscal year", {"all": "Latest fiscal year"}), class_="city-control"
            ),
            ui.div(
                ui.input_select("compare", "Compare with", {"all": "Prior fiscal year"}),
                class_="city-control",
            ),
            ui.div(
                ui.input_select(
                    "flow",
                    "Revenue or expense",
                    {"all": "All flows", "revenue": "Revenue", "expense": "Expenses"},
                ),
                class_="city-control",
            ),
            ui.div(
                ui.input_select("fund_scope", "Fund scope", {"all": "All fund scopes"}), class_="city-control"
            ),
            ui.div(ui.output_text("breadcrumb"), class_="city-filter-note"),
            class_="city-controls",
        ),
        ui.output_ui("state"),
        ui.div(
            chart_frame(
                "Budget by department",
                output_widget("chart", height="360px"),
                ui.output_text("chart_summary"),
            ),
            chart_frame(
                "Fund and category path",
                output_widget("sunburst", height="360px"),
                ui.output_text("sunburst_summary"),
            ),
            chart_frame(
                "Selected records",
                ui.div(ui.output_data_frame("table"), class_="city-table-wrap"),
                ui.output_text("table_summary"),
            ),
            class_="city-grid city-grid--2",
        ),
        ui.div(
            chart_frame(
                "Historical trend", output_widget("trend", height="300px"), ui.output_text("trend_summary")
            ),
            ui.output_ui("comparison_detail"),
            class_="city-split city-split--wide",
        ),
        ui.div(
            section_header(
                "How to read this view",
                "Use the filters to narrow the hierarchy. Unknown or uncategorized source values remain visible.",
            ),
            ui.output_ui("detail"),
            class_="city-surface city-surface--panel",
        ),
        section_id="drilldown",
    )


@module.server
def drilldown_server(
    input: Any,
    output: Any,
    session: Any,
    snapshot: Any,
    navigation_callback: Callable[[str], Any] | None = None,
) -> None:
    @reactive.calc
    def frame() -> pd.DataFrame:
        return coerce_snapshot(snapshot)

    def _selected_year(input_name: str, fallback_index: int) -> int | None:
        available = [int(value) for value in years(frame())]
        selected = input[input_name]()
        if selected and str(selected).isdigit() and int(selected) in available:
            return int(selected)
        return (
            available[fallback_index]
            if len(available) > fallback_index
            else (available[0] if available else None)
        )

    def _scope_and_flow(value: pd.DataFrame) -> pd.DataFrame:
        if value.empty:
            return value
        result = ensure_scope_column(value)
        scope = input.fund_scope()
        if scope and scope not in {"all", "all_funds"}:
            result = result.loc[result["fund_scope"].eq(str(scope))]
        flow = input.flow()
        if flow in {"revenue", "expense"}:
            expected = "Revenues" if flow == "revenue" else "Expenses"
            result = result.loc[result["expense_revenue"].eq(expected)]
        return result

    def _hierarchy(value: pd.DataFrame) -> pd.DataFrame:
        result = value
        for name in ("department", "fund", "category"):
            selected = input[name]()
            if selected and selected != "all":
                result = result.loc[result[name].astype(str).eq(str(selected))]
        return result

    @reactive.calc
    def current_rows() -> pd.DataFrame:
        year = _selected_year("year", 0)
        value = _scope_and_flow(frame())
        if year is not None:
            value = value.loc[value["fiscal_year"].eq(year)]
        return _hierarchy(value).copy()

    @reactive.calc
    def prior_rows() -> pd.DataFrame:
        year = _selected_year("compare", 1)
        value = _scope_and_flow(frame())
        if year is not None:
            value = value.loc[value["fiscal_year"].eq(year)]
        return _hierarchy(value).copy()

    @reactive.effect
    def _update_years_and_scope() -> None:
        value = frame().copy()
        available_years = years(value)
        if available_years:
            ui.update_select(
                "year",
                choices={item: item for item in available_years},
                selected=available_years[0],
            )
            ui.update_select(
                "compare",
                choices={item: item for item in available_years},
                selected=(available_years[1] if len(available_years) > 1 else available_years[0]),
            )
        with reactive.isolate():
            selected_scope = input.fund_scope()
        ui.update_select(
            "fund_scope",
            choices={key: label for key, label in FUND_SCOPE_LABELS.items()},
            selected=(selected_scope if selected_scope in FUND_SCOPE_LABELS else "all_funds"),
        )

    @reactive.effect
    def _update_departments() -> None:
        scoped = _scope_and_flow(frame())
        departments = unique_options(scoped, "department")
        with reactive.isolate():
            selected_department = input.department()
        ui.update_select(
            "department",
            choices={"all": "All departments", **{item: item for item in departments}},
            selected=(selected_department if selected_department in departments else "all"),
        )

    @reactive.effect
    def _update_funds() -> None:
        scoped = _scope_and_flow(frame())
        selected_department = input.department()
        if selected_department and selected_department != "all":
            scoped = scoped.loc[scoped["department"].astype(str).eq(str(selected_department))]
        funds = unique_options(scoped, "fund")
        with reactive.isolate():
            selected_fund = input.fund()
        ui.update_select(
            "fund",
            choices={"all": "All funds", **{item: item for item in funds}},
            selected=selected_fund if selected_fund in funds else "all",
        )

    @reactive.effect
    def _update_categories() -> None:
        scoped = _scope_and_flow(frame())
        selected_department = input.department()
        if selected_department and selected_department != "all":
            scoped = scoped.loc[scoped["department"].astype(str).eq(str(selected_department))]
        selected_fund = input.fund()
        if selected_fund and selected_fund != "all":
            scoped = scoped.loc[scoped["fund"].astype(str).eq(str(selected_fund))]
        categories = unique_options(scoped, "category")
        with reactive.isolate():
            selected_category = input.category()
        ui.update_select(
            "category",
            choices={"all": "All categories", **{item: item for item in categories}},
            selected=selected_category if selected_category in categories else "all",
        )

    def _next_dimension() -> str:
        if input.department() in {None, "all"}:
            return "department"
        if input.fund() in {None, "all"}:
            return "fund"
        return "category"

    def chart() -> Any:
        value = current_rows()
        dimension = _next_dimension()
        if value.empty:
            return go.FigureWidget()
        totals = value.groupby(dimension, dropna=False)["amount"].sum().nlargest(15).sort_values()
        labels = [str(index) if pd.notna(index) else "Unknown department" for index in totals.index]
        fig = go.FigureWidget(
            go.Bar(
                x=totals.values,
                y=labels,
                orientation="h",
                marker_color="#0072ce",
                hovertemplate="%{y}<br>$%{x:,.0f}<extra></extra>",
            )
        )

        def _select_bar(_trace: Any, points: Any, _state: Any) -> None:
            if not points.point_inds:
                return
            selected = str(labels[points.point_inds[0]])
            ui.update_select(dimension, selected=selected, session=session)

        fig.data[0].on_click(_select_bar)
        fig.update_layout(
            margin=dict(l=12, r=12, t=8, b=22),
            height=max(300, 26 * len(labels)),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif"),
            xaxis=dict(tickprefix="$", gridcolor="#e2e6ed"),
            yaxis=dict(automargin=True),
        )
        return fig

    def table() -> Any:
        value = current_rows()
        if value.empty:
            return render.DataGrid(
                pd.DataFrame({"Status": ["No records match the selected filters."]}), selection_mode="none"
            )
        display = value[
            [
                "fiscal_year",
                "department",
                "fund",
                "category",
                "amount",
                "expense_revenue",
                "fund_category",
                "object_id",
            ]
        ].head(1000)
        return render.DataGrid(display, height="360px", filters=True, selection_mode="row")

    def state() -> Any:
        if frame().empty:
            return empty_state(
                "Waiting for the budget snapshot", "This view will appear after the source refresh completes."
            )
        if current_rows().empty:
            return empty_state("No records match these filters", "Clear one filter to widen the hierarchy.")
        return ui.div()

    def breadcrumb() -> str:
        labels = []
        for name, _label in (("department", "Department"), ("fund", "Fund"), ("category", "Category")):
            selected = input[name]()
            if selected and selected != "all":
                labels.append(str(selected))
        return "Citywide / " + " / ".join(labels) if labels else "Citywide"

    def chart_summary() -> str:
        value = current_rows()
        return (
            f"Ranked {_next_dimension()} totals represent {len(value):,} exact current-year records."
            if not value.empty
            else "No current-year records match."
        )

    def sunburst() -> Any:
        value = current_rows().loc[lambda rows: rows["amount"] > 0]
        if value.empty:
            return go.FigureWidget()
        grouped = (
            value.groupby(["department", "fund", "category"], dropna=False)["amount"].sum().reset_index()
        )
        departments = grouped.groupby("department")["amount"].sum()
        funds = grouped.groupby(["department", "fund"])["amount"].sum()
        ids = ["root"]
        labels = ["Current selection"]
        parents = [""]
        values = [float(grouped["amount"].sum())]
        for department, amount in departments.items():
            department_id = f"department::{department}"
            ids.append(department_id)
            labels.append(str(department))
            parents.append("root")
            values.append(float(amount))
        for (department, fund), amount in funds.items():
            fund_id = f"fund::{department}::{fund}"
            ids.append(fund_id)
            labels.append(str(fund))
            parents.append(f"department::{department}")
            values.append(float(amount))
        for row in grouped.itertuples(index=False):
            ids.append(f"category::{row.department}::{row.fund}::{row.category}")
            labels.append(str(row.category))
            parents.append(f"fund::{row.department}::{row.fund}")
            values.append(float(row.amount))
        fig = go.FigureWidget(
            go.Sunburst(ids=ids, labels=labels, parents=parents, values=values, branchvalues="total")
        )
        fig.update_layout(
            margin=dict(l=4, r=4, t=4, b=4),
            height=320,
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif"),
        )
        return fig

    def sunburst_summary() -> str:
        return (
            "Fund and category shares use positive approved amounts. "
            "Zero and negative source records remain in the exact table."
        )

    def trend() -> Any:
        value = _hierarchy(_scope_and_flow(frame()))
        if value.empty:
            return go.FigureWidget()
        grouped = value.groupby("fiscal_year")["amount"].sum().reset_index().sort_values("fiscal_year")
        fig = go.FigureWidget(
            go.Scatter(
                x=grouped["fiscal_year"].astype(str),
                y=grouped["amount"],
                mode="lines+markers",
                line=dict(color="#0072ce", width=3),
                marker=dict(color="#003c71"),
                hovertemplate="%{x}<br>$%{y:,.0f}<extra></extra>",
            )
        )
        fig.update_layout(
            margin=dict(l=12, r=12, t=8, b=35),
            height=260,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif"),
            yaxis=dict(tickprefix="$", gridcolor="#e2e6ed"),
        )
        return fig

    def trend_summary() -> str:
        return f"Historical trend for the selected hierarchy across {len(years(frame()))} fiscal years."

    def comparison_detail() -> Any:
        current_total = float(current_rows()["amount"].sum())
        prior_total = float(prior_rows()["amount"].sum())
        change = current_total - prior_total
        percent = change / prior_total * 100 if prior_total else None
        return ui.div(
            ui.h3("Current versus comparison", class_="city-card-heading"),
            ui.p(f"FY{_selected_year('year', 0)}: {format_currency(current_total)}"),
            ui.p(f"FY{_selected_year('compare', 1)}: {format_currency(prior_total)}"),
            ui.p(
                f"Change: {format_currency(change)}"
                + (f" ({percent:+.1f}%)" if percent is not None else " (percentage unavailable)")
            ),
            class_="city-surface city-surface--panel city-detail-copy",
        )

    def table_summary() -> str:
        return f"Showing up to 1,000 records. {len(current_rows()):,} records match the current filters."

    table_renderer = render.data_frame(table)

    @reactive.calc
    def selected_rows() -> pd.DataFrame:
        try:
            selected = table_renderer.data_view(selected=True)
        except Exception:
            return pd.DataFrame()
        return selected if isinstance(selected, pd.DataFrame) else pd.DataFrame()

    @reactive.effect
    def _sync_table_selection() -> None:
        selected = selected_rows()
        if len(selected) != 1:
            return
        row = selected.iloc[0]
        for name in ("department", "fund", "category"):
            selected_value = str(row[name]).strip() if name in selected.columns else ""
            if selected_value and str(input[name]()) != selected_value:
                ui.update_select(name, selected=selected_value, session=session)

    def detail() -> Any:
        selected = selected_rows()
        if not selected.empty:
            row = selected.iloc[0]
            return ui.div(
                ui.strong(f"ObjectId {int(row['object_id'])}"),
                ui.p(
                    f"{row['department']} / {row['fund']} / {row['category']}: "
                    f"{format_currency(row['amount'])} ({row['expense_revenue']})."
                ),
                class_="city-detail-copy",
            )
        value = current_rows()
        return ui.div(
            ui.p(
                f"Current scope contains {len(value):,} records totaling "
                f"{format_currency(value['amount'].sum())}."
            ),
            class_="city-detail-copy",
        )

    output(render_widget(chart), id="chart")
    output(render_widget(sunburst), id="sunburst")
    output(render_widget(trend), id="trend")
    output(table_renderer, id="table")
    output(render.ui(state), id="state")
    output(render.text(breadcrumb), id="breadcrumb")
    output(render.text(chart_summary), id="chart_summary")
    output(render.text(sunburst_summary), id="sunburst_summary")
    output(render.text(trend_summary), id="trend_summary")
    output(render.ui(comparison_detail), id="comparison_detail")
    output(render.text(table_summary), id="table_summary")
    output(render.ui(detail), id="detail")
