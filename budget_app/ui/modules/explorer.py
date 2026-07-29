"""Filterable exact-record explorer with linked full-width comparison."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from shiny import module, reactive, render, req, ui
from shiny.testmode import export_test_values, snapshot_preprocess_input

from budget_app.data import FUND_SCOPE_LABELS, safe_csv_export

from ..components import (
    coerce_bundle,
    coerce_snapshot,
    compact_chart_label,
    empty_state,
    ensure_scope_column,
    format_currency,
    section_header,
    years,
)
from ..shell import page_intro, page_section

FLOW_LABELS = {
    "all": "Revenue and expenses",
    "revenue": "Revenue",
    "expense": "Expenses",
}


@module.ui
def explorer_ui(id: str = "explorer") -> Any:
    chart_id = module.resolve_id("chart")
    chart_host_id = module.resolve_id("chart_host")
    return page_section(
        page_intro(
            "Explorer",
            "Filter the exact records behind the story. Compare departments at full width, "
            "then select a source row without losing fiscal-year or fund context.",
            eyebrow_text="Supporting records",
        ),
        ui.div(
            ui.div(ui.input_select("year", "Fiscal year", {"all": "All years"}), class_="city-control"),
            ui.div(
                ui.input_select("compare", "Compare with", {"prior": "Prior fiscal year"}),
                class_="city-control",
            ),
            ui.div(
                ui.input_select("flow", "Budget flow", FLOW_LABELS),
                class_="city-control city-control--flow",
            ),
            ui.div(
                ui.input_select("fund_scope", "Fund scope", {"all_funds": "All funds total"}),
                class_="city-control",
            ),
            ui.div(
                ui.input_select("department", "Department", {"all": "All departments"}),
                class_="city-control",
            ),
            ui.div(ui.input_select("fund", "Fund", {"all": "All funds"}), class_="city-control"),
            ui.div(
                ui.input_select("category", "Category", {"all": "All categories"}),
                class_="city-control",
            ),
            class_="city-controls",
            aria_label="Explorer filters",
        ),
        ui.output_ui("filter_chips"),
        ui.div(
            ui.input_action_button(
                "reset",
                "Reset filters",
                class_="city-button city-button--secondary",
            ),
            ui.download_button(
                "download",
                "Export filtered CSV",
                class_="city-button city-button--secondary",
            ),
            ui.input_action_button(
                "copy_state",
                "Copy Explorer state",
                class_="city-button city-button--secondary",
            ),
            ui.output_text("summary"),
            class_="city-action-row city-explorer-toolbar",
        ),
        ui.output_ui("state"),
        ui.div(
            ui.div(
                section_header(
                    "Department comparison",
                    "The full-width chart compares the active and reference years. Labels are shortened for scanability; exact names remain available in hover and the table.",
                ),
                ui.output_ui("chart_key"),
                ui.div(
                    ui.div(
                        id=chart_host_id,
                        class_="city-client-plot",
                        style="height: 440px;",
                        tabindex="0",
                    ),
                    id=chart_id,
                    class_="city-client-plot-output",
                    style="height: 440px;",
                    aria_label="Department comparison chart",
                ),
                ui.output_text("chart_summary"),
                class_="city-surface city-surface--outlined city-chart-frame",
            ),
            class_="city-chart-frame--wide",
        ),
        ui.output_ui("detail"),
        ui.div(
            section_header(
                "Exact supporting records",
                "Sort and filter the virtualized grid. Selecting one row opens the same exact "
                "record in quick detail while preserving this Explorer state.",
            ),
            ui.div(ui.output_data_frame("table"), class_="city-table-wrap"),
            class_="city-surface city-surface--outlined city-guide-card",
        ),
        section_id="explorer",
        tone="alternate",
    )


@module.server
def explorer_server(
    input: Any,
    output: Any,
    session: Any,
    snapshot: Any,
    navigation_callback: Callable[[Mapping[str, Any] | str], Any] | None = None,
    detail_close_signal: Any | None = None,
    active: Callable[[], bool] | None = None,
) -> None:
    def _scrub_action_count(_value: Any) -> str:
        return "<action-count>"

    snapshot_preprocess_input("reset", _scrub_action_count)
    snapshot_preprocess_input("copy_state", _scrub_action_count)

    @reactive.calc
    def frame() -> pd.DataFrame:
        return coerce_snapshot(snapshot)

    @reactive.calc
    def bundle() -> Any:
        return coerce_bundle(snapshot)

    def available_years() -> list[int]:
        current_bundle = bundle()
        if current_bundle is not None:
            return list(current_bundle.years)
        return [int(value) for value in years(frame())]

    def selected_year(name: str, fallback_index: int) -> int | None:
        available = available_years()
        selected = input[name]()
        if name == "year" and str(selected or "").strip() == "all":
            return None
        try:
            candidate = int(selected)
        except (TypeError, ValueError):
            candidate = available[fallback_index] if len(available) > fallback_index else None
        return candidate if candidate in available else None

    def year_label(name: str, fallback_index: int) -> str:
        selected = selected_year(name, fallback_index)
        return "All years" if selected is None and name == "year" else f"FY{selected}"

    def optional_input(name: str) -> str | None:
        candidate = str(input[name]() or "").strip()
        return None if candidate in {"", "all"} else candidate

    last_choice_updates: dict[str, tuple[tuple[tuple[str, str], ...], str | None]] = {}

    def update_select_if_changed(name: str, choices: dict[str, str], selected: str | None) -> None:
        signature = (tuple(choices.items()), selected)
        if last_choice_updates.get(name) == signature:
            return
        last_choice_updates[name] = signature
        ui.update_select(name, choices=choices, selected=selected)

    def context_rows(*, include_year: bool, hierarchy_depth: int = 3) -> pd.DataFrame:
        value = frame()
        if value.empty:
            return value.copy()
        result = ensure_scope_column(value)
        flow = str(input.flow() or "all")
        if flow in {"revenue", "expense"}:
            expected = "Revenues" if flow == "revenue" else "Expenses"
            result = result.loc[result["expense_revenue"].eq(expected)]
        scope = str(input.fund_scope() or "all_funds")
        if scope not in {"all", "all_funds"}:
            result = result.loc[result["fund_scope"].eq(scope)]
        if include_year:
            year = selected_year("year", 0)
            if year is not None:
                result = result.loc[result["fiscal_year"].eq(year)]
        for index, name in enumerate(("department", "fund", "category")):
            if index >= hierarchy_depth:
                break
            selected = optional_input(name)
            if selected:
                result = result.loc[result[name].astype(str).eq(selected)]
        return result.copy()

    @reactive.calc
    def filtered() -> pd.DataFrame:
        return context_rows(include_year=True)

    @reactive.calc
    def comparison_rows() -> pd.DataFrame:
        value = context_rows(include_year=False)
        year = selected_year("compare", 1)
        return value.loc[value["fiscal_year"].eq(year)].copy() if year is not None else value.iloc[0:0]

    @reactive.effect
    def _update_filter_choices() -> None:
        value = frame()
        current_bundle = bundle()
        with reactive.isolate():
            active_flow = str(input.flow() or "all")
            active_scope = str(input.fund_scope() or "all_funds")
        use_prepared_choices = (
            current_bundle is not None and active_flow == "all" and active_scope in {"all", "all_funds"}
        )
        available = [str(year) for year in available_years()]
        if available:
            with reactive.isolate():
                current_year = str(input.year() or "")
                compare_year = str(input.compare() or "")
            update_select_if_changed(
                "year",
                {"all": "All years", **{year: year for year in available}},
                current_year if current_year == "all" or current_year in available else "all",
            )
            update_select_if_changed(
                "compare",
                {year: year for year in available},
                (
                    compare_year
                    if compare_year in available
                    else (available[1] if len(available) > 1 else available[0])
                ),
            )
        with reactive.isolate():
            selected_scope = str(input.fund_scope() or "")
        update_select_if_changed(
            "fund_scope",
            FUND_SCOPE_LABELS,
            selected_scope if selected_scope in FUND_SCOPE_LABELS else "all_funds",
        )
        if value.empty:
            return

        with reactive.isolate():
            department = str(input.department() or "all")
        departments = (
            list(current_bundle.choices_for("department"))
            if use_prepared_choices
            else sorted(
                context_rows(include_year=False, hierarchy_depth=0)["department"]
                .dropna()
                .astype(str)
                .unique()
            )
        )
        update_select_if_changed(
            "department",
            {"all": "All departments", **{item: item for item in departments}},
            department if department in departments else "all",
        )

        with reactive.isolate():
            fund = str(input.fund() or "all")
        funds = (
            list(current_bundle.choices_for("fund", department=department if department != "all" else None))
            if use_prepared_choices
            else sorted(
                context_rows(include_year=False, hierarchy_depth=1)["fund"].dropna().astype(str).unique()
            )
        )
        update_select_if_changed(
            "fund",
            {"all": "All funds", **{item: item for item in funds}},
            fund if fund in funds else "all",
        )

        with reactive.isolate():
            category = str(input.category() or "all")
        categories = (
            list(
                current_bundle.choices_for(
                    "category",
                    department=department if department != "all" else None,
                    fund=fund if fund != "all" else None,
                )
            )
            if use_prepared_choices
            else sorted(
                context_rows(include_year=False, hierarchy_depth=2)["category"].dropna().astype(str).unique()
            )
        )
        update_select_if_changed(
            "category",
            {"all": "All categories", **{item: item for item in categories}},
            category if category in categories else "all",
        )

    @reactive.effect
    @reactive.event(input.reset)
    def _reset() -> None:
        available = [str(year) for year in available_years()]
        if available:
            ui.update_select("year", selected="all")
            ui.update_select("compare", selected=available[1] if len(available) > 1 else available[0])
        ui.update_select("flow", selected="all")
        ui.update_select("fund_scope", selected="all_funds")
        ui.update_select("department", selected="all")
        ui.update_select("fund", selected="all")
        ui.update_select("category", selected="all")

    def selection_payload(row: pd.Series | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "year": selected_year("year", 0),
            "compare_year": selected_year("compare", 1),
            "flow": str(input.flow() or "all"),
            "fund_scope": str(input.fund_scope() or "all_funds"),
            "department": optional_input("department"),
            "fund": optional_input("fund"),
            "category": optional_input("category"),
        }
        if row is not None:
            payload.update(
                department=str(row["department"]),
                fund=str(row["fund"]),
                category=str(row["category"]),
                selected_record=int(row["object_id"]),
            )
        return payload

    def filter_chips() -> Any:
        chips = [
            year_label("year", 0),
            f"compared with {year_label('compare', 1)}",
            FLOW_LABELS.get(str(input.flow()), FLOW_LABELS["all"]),
            FUND_SCOPE_LABELS.get(
                str(input.fund_scope()),
                FUND_SCOPE_LABELS["all_funds"],
            ),
        ]
        chips.extend(
            value
            for value in (
                optional_input("department"),
                optional_input("fund"),
                optional_input("category"),
            )
            if value
        )
        return ui.div(
            ui.span("Active filters", class_="city-filter-chips__label"),
            *(ui.span(value, class_="city-filter-chip") for value in chips),
            class_="city-filter-chips",
            aria_live="polite",
        )

    def chart_data() -> pd.DataFrame:
        current = filtered()
        prior = comparison_rows()
        if current.empty:
            return pd.DataFrame()
        current_totals = current.groupby("department")["amount"].sum()
        prior_totals = prior.groupby("department")["amount"].sum()
        rank = current_totals.abs().nlargest(15).index
        return pd.DataFrame(
            {
                "department": rank,
                "current": current_totals.reindex(rank).fillna(0).values,
                "compare": prior_totals.reindex(rank).fillna(0).values,
            }
        ).sort_values("current")

    def chart() -> Any:
        req(active is None or active())
        value = chart_data()
        if value.empty:
            return go.Figure()
        full_labels = value["department"].astype(str)
        axis_labels = full_labels.map(lambda value: compact_chart_label(value, limit=18))
        figure = go.Figure()
        figure.add_bar(
            x=value["compare"],
            y=axis_labels,
            customdata=full_labels,
            orientation="h",
            name=year_label("compare", 1),
            marker_color="#9fb4c8",
            hovertemplate="%{customdata}<br>$%{x:,.0f}<extra></extra>",
        )
        figure.add_bar(
            x=value["current"],
            y=axis_labels,
            customdata=full_labels,
            orientation="h",
            name=year_label("year", 0),
            marker_color="#0072ce",
            hovertemplate="%{customdata}<br>$%{x:,.0f}<extra></extra>",
        )

        figure.update_layout(
            barmode="group",
            margin=dict(l=24, r=24, t=16, b=48),
            height=max(380, 30 * len(value)),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif"),
            showlegend=False,
            xaxis=dict(
                title="Approved amount",
                tickprefix="$",
                separatethousands=True,
                gridcolor="#e2e6ed",
                fixedrange=True,
            ),
            yaxis=dict(automargin=True, fixedrange=True),
        )
        return figure

    @reactive.effect
    async def _render_chart_client() -> None:
        req(active is None or active())
        payload = json.loads(chart().to_json())
        await session.send_custom_message(
            "budget-plotly-react",
            {
                "id": str(session.ns("chart_host")),
                "inputId": str(session.ns("chart_click")),
                "selectionInputId": "overview-selection_request",
                "selection": {
                    "year": selected_year("year", 0),
                    "flow": str(input.flow() or "all"),
                    "scope": str(input.fund_scope() or "all_funds"),
                },
                "data": payload["data"],
                "layout": payload["layout"],
                "config": {"displaylogo": False, "responsive": True},
            },
        )

    @reactive.effect
    @reactive.event(input.chart_click)
    def _select_chart_department() -> None:
        event = input.chart_click()
        if not isinstance(event, Mapping):
            return
        department = str(event.get("customdata") or "").strip()
        if not department:
            return
        ui.update_select("department", selected=department, session=session)
        if navigation_callback:
            payload = selection_payload()
            payload["department"] = department
            payload["fund"] = None
            payload["category"] = None
            navigation_callback(payload)

    def chart_summary() -> str:
        return (
            f"Full-width comparison of up to 15 departments for {year_label('year', 0)} "
            f"and {year_label('compare', 1)}. Axis labels are shortened for scanability; "
            "hover and the exact table retain full names. Select a bar for synchronized quick detail."
        )

    def chart_key() -> Any:
        return ui.div(
            ui.span("Year key", class_="sr-only"),
            ui.span(
                ui.span(class_="city-chart-key__swatch city-chart-key__swatch--compare", aria_hidden="true"),
                year_label("compare", 1),
                class_="city-chart-key__item",
                role="listitem",
            ),
            ui.span(
                ui.span(class_="city-chart-key__swatch city-chart-key__swatch--current", aria_hidden="true"),
                year_label("year", 0),
                class_="city-chart-key__item",
                role="listitem",
            ),
            class_="city-chart-key",
            role="list",
            aria_label="Department comparison year key",
        )

    def table() -> Any:
        value = filtered()
        if value.empty:
            return render.DataGrid(
                pd.DataFrame({"Status": ["No records match these filters."]}),
                selection_mode="none",
            )
        return render.DataGrid(
            value.head(2000),
            height="560px",
            filters=True,
            selection_mode="row",
        )

    table_renderer = render.data_frame(table)

    @reactive.calc
    def selected_row() -> pd.DataFrame:
        try:
            selected = table_renderer.data_view(selected=True)
        except Exception:
            return pd.DataFrame()
        if not isinstance(selected, pd.DataFrame):
            return pd.DataFrame()
        current_bundle = bundle()
        if current_bundle is not None and len(selected) == 1 and "object_id" in selected.columns:
            try:
                return current_bundle.exact_rows(int(selected.iloc[0]["object_id"]))
            except (TypeError, ValueError):
                return selected
        return selected

    last_selected_record = reactive.Value[int | None](None)
    suppress_selected_record_open = reactive.Value(False)

    if detail_close_signal is not None:

        @reactive.effect
        @reactive.event(detail_close_signal, ignore_init=True)
        async def _clear_record_selection_after_close() -> None:
            if len(selected_row()) != 1:
                last_selected_record.set(None)
                return
            suppress_selected_record_open.set(True)
            try:
                await table_renderer.update_cell_selection(None)
            except Exception:
                # The Explorer grid may not be mounted in the active view.
                suppress_selected_record_open.set(False)
                last_selected_record.set(None)
                return

    @reactive.effect
    def _open_selected_record() -> None:
        selected = selected_row()
        if len(selected) != 1:
            if last_selected_record.get() is not None:
                last_selected_record.set(None)
            if suppress_selected_record_open.get():
                suppress_selected_record_open.set(False)
            return
        if suppress_selected_record_open.get():
            return
        row = selected.iloc[0]
        record = int(row["object_id"])
        if last_selected_record.get() == record:
            return
        last_selected_record.set(record)
        if navigation_callback:
            navigation_callback(selection_payload(row))

    def detail() -> Any:
        selected = selected_row()
        if len(selected) == 1:
            row = selected.iloc[0]
            return ui.div(
                ui.div(
                    ui.div("Selected source record", class_="city-eyebrow"),
                    ui.h3(f"ObjectId {int(row['object_id'])}", class_="city-card-heading"),
                    ui.p(f"{row['department']} / {row['fund']} / {row['category']}"),
                    ui.p(
                        f"{format_currency(row['amount'])} · {row['expense_revenue']} · "
                        f"FY{int(row['fiscal_year'])}"
                    ),
                ),
                ui.span(
                    "Quick detail is synchronized with this exact row.",
                    class_="city-status-badge",
                ),
                class_="city-surface city-surface--panel city-compact-detail",
            )
        value = filtered()
        return ui.div(
            ui.div(
                ui.div("Current filter result", class_="city-eyebrow"),
                ui.h3(f"{len(value):,} exact records", class_="city-card-heading"),
                ui.p(f"Approved amount total: {format_currency(value['amount'].sum())}."),
            ),
            ui.span("Select one row for exact detail", class_="city-status-badge"),
            class_="city-surface city-surface--panel city-compact-detail",
        )

    def summary() -> str:
        value = filtered()
        count = len(value)
        current_bundle = bundle()
        if current_bundle is not None:
            flow = str(input.flow() or "all")
            count = current_bundle.record_count(
                year=selected_year("year", 0),
                flow={"revenue": "Revenues", "expense": "Expenses"}.get(flow, "all"),
                scope=str(input.fund_scope() or "all_funds"),
                department=optional_input("department"),
                fund=optional_input("fund"),
                category=optional_input("category"),
            )
        return (
            f"{count:,} records match. The grid displays up to 2,000 rows "
            f"and totals {format_currency(value['amount'].sum())}."
        )

    def state() -> Any:
        if frame().empty:
            return empty_state(
                "Waiting for the source snapshot",
                "Explorer will populate when approved budget data is available.",
            )
        if filtered().empty:
            return empty_state(
                "No records match these filters",
                "Reset filters or broaden one hierarchy selection.",
            )
        return ui.div()

    @reactive.effect
    @reactive.event(input.copy_state)
    async def _copy_state() -> None:
        await session.bookmark.do_bookmark()

    @render.download_button(filename="sacramento-budget-explorer.csv", media_type="text/csv")
    async def download() -> Any:
        yield safe_csv_export(filtered()).encode("utf-8")

    output(render.ui(filter_chips), id="filter_chips")
    output(render.ui(chart_key), id="chart_key")
    output(render.text(chart_summary), id="chart_summary")
    output(table_renderer, id="table")
    output(render.ui(detail), id="detail")
    output(render.text(summary), id="summary")
    output(render.ui(state), id="state")

    def _explorer_test_state() -> dict[str, Any]:
        value = filtered()
        try:
            visible = table_renderer.data_view()
        except Exception:
            visible = value.head(2000)
        selected = selected_row()
        return {
            "filtered_rows": len(value),
            "rendered_rows": min(len(value), 2000),
            "visible_rows": len(visible),
            "visible_object_ids": [int(item) for item in visible["object_id"].head(25)]
            if "object_id" in visible
            else [],
            "visible_departments": sorted({str(item) for item in visible["department"].dropna().unique()})
            if "department" in visible
            else [],
            "selected_object_ids": [int(item) for item in selected["object_id"]]
            if "object_id" in selected
            else [],
        }

    export_test_values(test_state=_explorer_test_state)
