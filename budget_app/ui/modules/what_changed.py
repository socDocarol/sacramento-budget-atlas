"""Fiscal-year comparison with linked integrated Overview selections."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from shiny import module, reactive, render, req, ui
from shinywidgets import output_widget, render_widget

from ..components import (
    chart_frame,
    coerce_snapshot,
    compact_chart_label,
    empty_state,
    format_currency,
    format_percent,
    section_header,
    stat_card,
    years,
)
from ..shell import page_intro, page_section

FLOW_LABELS = {
    "all": "Revenue and expenses",
    "revenue": "Revenue",
    "expense": "Expenses",
}


@module.ui
def what_changed_ui(id: str = "changed") -> Any:
    return page_section(
        page_intro(
            "What changed between years?",
            "Compare the same approved-budget scope across two fiscal years, rank the "
            "largest department movements, and inspect exact values before drawing conclusions.",
            eyebrow_text="Year-over-year comparison",
        ),
        ui.div(
            ui.div(
                ui.input_select("current_year", "Current year", {"latest": "Latest fiscal year"}),
                class_="city-control",
            ),
            ui.div(
                ui.input_select("prior_year", "Comparison year", {"prior": "Prior fiscal year"}),
                class_="city-control",
            ),
            ui.div(
                ui.input_select("flow", "Budget flow", FLOW_LABELS),
                class_="city-control",
            ),
            ui.input_action_button(
                "reset",
                "Reset comparison",
                class_="city-button city-button--secondary",
            ),
            class_="city-controls",
            aria_label="Year comparison filters",
        ),
        ui.output_ui("context"),
        ui.output_ui("metrics"),
        ui.output_ui("state"),
        ui.div(
            chart_frame(
                "Largest department movements",
                output_widget("chart", height="460px"),
                ui.output_text("chart_summary"),
            ),
            class_="city-chart-frame--wide",
        ),
        ui.div(
            chart_frame(
                "Current approved total versus change",
                output_widget("scatter", height="380px"),
                ui.output_text("scatter_summary"),
            ),
            ui.div(
                section_header(
                    "How to read this comparison",
                    "Position and direction answer different questions.",
                ),
                ui.tags.ul(
                    ui.tags.li("Farther right means a larger current approved total."),
                    ui.tags.li("Above zero means the approved amount increased."),
                    ui.tags.li("Below zero means the approved amount decreased."),
                    ui.tags.li(
                        "A movement does not explain cause, service impact, performance, or actual spending."
                    ),
                    class_="city-check-list",
                ),
                class_="city-surface city-surface--panel city-guide-card",
            ),
            class_="city-split city-split--wide",
        ),
        ui.div(
            section_header(
                "Exact department comparison",
                "Select one row to open synchronized quick detail. Sort and filter without losing exact values.",
            ),
            ui.div(ui.output_data_frame("table"), class_="city-table-wrap"),
            class_="city-surface city-surface--outlined city-guide-card",
        ),
        section_id="changed",
        tone="alternate",
    )


@module.server
def what_changed_server(
    input: Any,
    output: Any,
    session: Any,
    snapshot: Any,
    navigation_callback: Callable[[Mapping[str, Any] | str], Any] | None = None,
    detail_close_signal: Any | None = None,
    active: Callable[[], bool] | None = None,
) -> None:
    @reactive.calc
    def frame() -> pd.DataFrame:
        return coerce_snapshot(snapshot)

    def available_years() -> list[str]:
        return years(frame())

    def selected_year(name: str, fallback_index: int) -> int | None:
        available = [int(value) for value in available_years()]
        selected = input[name]()
        try:
            candidate = int(selected)
        except (TypeError, ValueError):
            candidate = available[fallback_index] if len(available) > fallback_index else None
        return candidate if candidate in available else None

    @reactive.effect
    def _years() -> None:
        values = available_years()
        if not values:
            return
        with reactive.isolate():
            current = str(input.current_year() or "")
            prior = str(input.prior_year() or "")
        ui.update_select(
            "current_year",
            choices={value: value for value in values},
            selected=current if current in values else values[0],
        )
        ui.update_select(
            "prior_year",
            choices={value: value for value in values},
            selected=prior if prior in values else (values[1] if len(values) > 1 else values[0]),
        )

    @reactive.effect
    @reactive.event(input.reset)
    def _reset() -> None:
        values = available_years()
        if not values:
            return
        ui.update_select("current_year", selected=values[0])
        ui.update_select("prior_year", selected=values[1] if len(values) > 1 else values[0])
        ui.update_select("flow", selected="all")

    @reactive.calc
    def comparison() -> pd.DataFrame:
        value = frame().copy()
        current = selected_year("current_year", 0)
        prior = selected_year("prior_year", 1)
        if value.empty or current is None or prior is None:
            return pd.DataFrame()
        selected_flow = str(input.flow() or "all")
        if selected_flow in {"revenue", "expense"}:
            expected = "Revenues" if selected_flow == "revenue" else "Expenses"
            value = value.loc[value["expense_revenue"].eq(expected)]
        current_rows = (
            value.loc[value["fiscal_year"].eq(current)].groupby("department", dropna=False)["amount"].sum()
        )
        prior_rows = (
            value.loc[value["fiscal_year"].eq(prior)].groupby("department", dropna=False)["amount"].sum()
        )
        result = pd.concat({"current": current_rows, "prior": prior_rows}, axis=1).fillna(0)
        result["change"] = result["current"] - result["prior"]
        result["change_pct"] = result["change"].div(result["prior"].where(result["prior"].ne(0))).mul(100)
        return (
            result.reset_index(names="department")
            .sort_values("change", key=lambda values: values.abs(), ascending=False)
            .reset_index(drop=True)
        )

    def _open_department(department: str) -> None:
        if not navigation_callback:
            return
        navigation_callback(
            {
                "year": selected_year("current_year", 0),
                "compare_year": selected_year("prior_year", 1),
                "flow": str(input.flow() or "all"),
                "fund_scope": "all_funds",
                "department": department,
            }
        )

    def context() -> Any:
        current = selected_year("current_year", 0)
        prior = selected_year("prior_year", 1)
        return ui.div(
            ui.span("Comparison question", class_="city-filter-chips__label"),
            ui.span(f"What changed from FY{prior} to FY{current}?", class_="city-filter-chip"),
            ui.span(FLOW_LABELS.get(str(input.flow()), FLOW_LABELS["all"]), class_="city-filter-chip"),
            class_="city-filter-chips",
            aria_live="polite",
        )

    def metrics() -> Any:
        value = comparison()
        if value.empty:
            return empty_state("Comparison metrics are not available")
        current_total = float(value["current"].sum())
        prior_total = float(value["prior"].sum())
        change = current_total - prior_total
        percent = change / prior_total * 100 if prior_total else None
        return ui.div(
            stat_card(
                f"FY{selected_year('current_year', 0)}",
                format_currency(current_total, compact=True),
                "Current approved total",
                tone="cobalt",
            ),
            stat_card(
                f"FY{selected_year('prior_year', 1)}",
                format_currency(prior_total, compact=True),
                "Comparison approved total",
                tone="sky",
            ),
            stat_card(
                "Net movement",
                format_currency(change, compact=True),
                format_percent(percent) if percent is not None else "Percentage unavailable",
                tone="green" if change >= 0 else "gold",
            ),
            stat_card(
                "Departments",
                f"{len(value):,}",
                "Exact compared entities",
                tone="cobalt",
            ),
            class_="city-grid city-grid--4",
        )

    def chart() -> Any:
        req(active is None or active())
        value = comparison().head(15).sort_values("change")
        if value.empty:
            return go.FigureWidget()
        value = value.assign(
            change_pct_label=value["change_pct"].map(
                lambda amount: f"{amount:+.1f}%" if pd.notna(amount) else "Not available"
            )
        )
        full_labels = value["department"].fillna("Unspecified department").astype(str)
        labels = full_labels.map(compact_chart_label)
        figure = go.FigureWidget(
            go.Bar(
                x=value["change"],
                y=labels,
                orientation="h",
                marker_color=["#c99a3b" if amount < 0 else "#0072ce" for amount in value["change"]],
                customdata=pd.DataFrame(
                    {
                        "department": full_labels,
                        "current": value["current"],
                        "prior": value["prior"],
                        "change_pct_label": value["change_pct_label"],
                    }
                ).to_numpy(),
                hovertemplate=(
                    "%{customdata[0]}<br>Change: $%{x:,.0f}<br>"
                    "Current: $%{customdata[1]:,.0f}<br>"
                    "Comparison: $%{customdata[2]:,.0f}<br>Percent: %{customdata[3]}"
                    "<extra></extra>"
                ),
            )
        )

        def _select(_trace: Any, points: Any, _state: Any) -> None:
            if points.point_inds:
                _open_department(str(value.iloc[points.point_inds[0]]["department"]))

        figure.data[0].on_click(_select)
        figure.update_layout(
            margin=dict(l=20, r=24, t=12, b=42),
            height=max(380, 30 * len(value)),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif"),
            xaxis=dict(
                title="Approved amount change",
                tickprefix="$",
                separatethousands=True,
                gridcolor="#e2e6ed",
                zerolinecolor="#94a3b8",
                fixedrange=True,
            ),
            yaxis=dict(automargin=True, fixedrange=True),
            showlegend=False,
        )
        return figure

    def chart_summary() -> str:
        value = comparison()
        if value.empty:
            return "Choose two fiscal years with records to see department movements."
        largest = value.iloc[0]
        return (
            f"Largest absolute movement: {largest['department']}, "
            f"{format_currency(largest['change'])}. Select a bar for exact detail."
        )

    def scatter() -> Any:
        req(active is None or active())
        value = comparison()
        if value.empty:
            return go.FigureWidget()
        value = value.assign(
            change_pct_label=value["change_pct"].map(
                lambda amount: f"{amount:+.1f}%" if pd.notna(amount) else "Not available"
            )
        )
        figure = go.FigureWidget(
            go.Scatter(
                x=value["current"],
                y=value["change"],
                mode="markers",
                text=value["department"].astype(str),
                customdata=value[["prior", "change_pct_label"]].to_numpy(),
                marker=dict(
                    size=11,
                    color=["#c99a3b" if amount < 0 else "#0072ce" for amount in value["change"]],
                    line=dict(color="#003c71", width=1),
                ),
                hovertemplate=(
                    "%{text}<br>Current: $%{x:,.0f}<br>Change: $%{y:,.0f}"
                    "<br>Comparison: $%{customdata[0]:,.0f}<br>Percent: %{customdata[1]}"
                    "<extra></extra>"
                ),
            )
        )

        def _select(trace: Any, points: Any, _state: Any) -> None:
            if points.point_inds:
                _open_department(str(trace.text[points.point_inds[0]]))

        figure.data[0].on_click(_select)
        figure.update_layout(
            margin=dict(l=20, r=16, t=12, b=54),
            height=350,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif"),
            xaxis=dict(
                title="Current approved total",
                tickprefix="$",
                separatethousands=True,
                gridcolor="#e2e6ed",
                fixedrange=True,
            ),
            yaxis=dict(
                title="Approved amount change",
                tickprefix="$",
                separatethousands=True,
                gridcolor="#e2e6ed",
                zerolinecolor="#94a3b8",
                fixedrange=True,
            ),
            showlegend=False,
        )
        return figure

    def scatter_summary() -> str:
        return (
            "Each point is one department. Use the exact table for keyboard access "
            "and precise current, comparison, dollar-change, and percentage values."
        )

    def table() -> Any:
        value = comparison().copy()
        if value.empty:
            return render.DataGrid(
                pd.DataFrame({"Status": ["Comparison is not available yet."]}),
                selection_mode="none",
            )
        display = value.rename(
            columns={
                "department": "Department",
                "current": "Current approved",
                "prior": "Comparison approved",
                "change": "Dollar change",
                "change_pct": "Percent change",
            }
        )
        for name in ("Current approved", "Comparison approved", "Dollar change"):
            display[name] = display[name].map(format_currency)
        display["Percent change"] = display["Percent change"].map(format_percent)
        return render.DataGrid(
            display,
            height="430px",
            filters=True,
            selection_mode="row",
        )

    table_renderer = render.data_frame(table)
    last_selected = reactive.Value[str | None](None)
    suppress_table_open = reactive.Value(False)

    if detail_close_signal is not None:

        @reactive.effect
        @reactive.event(detail_close_signal, ignore_init=True)
        async def _clear_table_selection() -> None:
            try:
                selected = table_renderer.data_view(selected=True)
            except Exception:
                selected = pd.DataFrame()
            if not isinstance(selected, pd.DataFrame) or len(selected) != 1:
                last_selected.set(None)
                return
            suppress_table_open.set(True)
            try:
                await table_renderer.update_cell_selection(None)
            except Exception:
                # The table may not be mounted in the active view.
                suppress_table_open.set(False)
                last_selected.set(None)
                return

    @reactive.effect
    def _open_table_selection() -> None:
        try:
            selected = table_renderer.data_view(selected=True)
        except Exception:
            return
        if not isinstance(selected, pd.DataFrame) or len(selected) != 1:
            if last_selected.get() is not None:
                last_selected.set(None)
            if suppress_table_open.get():
                suppress_table_open.set(False)
            return
        if suppress_table_open.get():
            return
        department = str(selected.iloc[0]["Department"])
        if last_selected.get() == department:
            return
        last_selected.set(department)
        _open_department(department)

    def state() -> Any:
        if frame().empty:
            return empty_state(
                "Waiting for the source snapshot",
                "The comparison will appear after approved budget data is ready.",
            )
        if comparison().empty:
            return empty_state(
                "No comparison is available",
                "Choose two fiscal years with records in the same budget flow.",
            )
        return ui.div()

    output(render.ui(context), id="context")
    output(render.ui(metrics), id="metrics")
    output(render_widget(chart), id="chart")
    output(render_widget(scatter), id="scatter")
    output(table_renderer, id="table")
    output(render.text(chart_summary), id="chart_summary")
    output(render.text(scatter_summary), id="scatter_summary")
    output(render.ui(state), id="state")
