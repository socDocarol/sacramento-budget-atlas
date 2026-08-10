"""Overview narrative and integrated hierarchical analysis workspace."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from shiny import module, reactive, render, ui
from shiny.testmode import export_test_values
from shinywidgets import output_widget, render_widget

from budget_app.data import FUND_SCOPE_LABELS, filter_rows
from budget_app.state import (
    VALID_PRESENTATION_LENSES,
    OverviewPresentationState,
    OverviewSelectionState,
    sanitize_overview_selection,
)

from ..components import (
    chart_frame,
    coerce_bundle,
    coerce_snapshot,
    compact_chart_label,
    empty_state,
    ensure_scope_column,
    format_currency,
    format_percent,
    section_header,
    stat_card,
    years,
)
from ..overview_metrics import (
    OverviewMeasureSummary,
    build_overview_measure_summary,
    fixed_fy2027_expense_benchmark,
    format_signed_currency,
    format_signed_percent,
)
from ..shell import page_section
from ..story_studio import story_studio_ui

FLOW_LABELS = {
    "all": "Revenue and expenses",
    "revenue": "Revenue",
    "expense": "Expenses",
}
FLOW_VALUES = {
    "all": "all",
    "revenue": "Revenues",
    "expense": "Expenses",
}


@dataclass(frozen=True, slots=True)
class OverviewController:
    """Imperative bridge used by other views to open integrated detail."""

    open_selection: Callable[[Mapping[str, Any] | None], None]
    restore: Callable[[OverviewSelectionState, OverviewPresentationState], None]


def _state_rows(
    frame: pd.DataFrame,
    state: OverviewSelectionState,
    *,
    year: int | None,
    include_hierarchy: bool = True,
    flow: str | None = None,
    scope: str | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return filter_rows(
        frame,
        year=year,
        flow=FLOW_VALUES.get(flow or state.flow, "all"),
        scope=scope or state.fund_scope,
        department=state.department if include_hierarchy else None,
        fund=state.fund if include_hierarchy else None,
        category=state.category if include_hierarchy else None,
    )


def _hierarchy_label(state: OverviewSelectionState) -> str:
    labels = ["Citywide"]
    labels.extend(value for value in (state.department, state.fund, state.category) if value is not None)
    if state.selected_record is not None:
        labels.append(f"ObjectId {state.selected_record}")
    return " / ".join(labels)


def _next_dimension(state: OverviewSelectionState) -> str:
    if state.department is None:
        return "department"
    if state.fund is None:
        return "fund"
    return "category"


def _exact_table(
    frame: pd.DataFrame,
    *,
    columns: tuple[tuple[str, str], ...],
    caption: str,
    limit: int = 20,
) -> Any:
    if frame.empty:
        return ui.p("No exact values are available for this view.", class_="city-chart-summary")
    rows = []
    for item in frame.head(limit).itertuples(index=False):
        values = item._asdict()
        cells = []
        for key, _label in columns:
            value = values.get(key, "")
            if key in {"amount", "current", "prior", "change"}:
                value = format_currency(value)
            cells.append(ui.tags.td(str(value)))
        rows.append(ui.tags.tr(*cells))
    return ui.tags.table(
        ui.tags.caption(caption),
        ui.tags.thead(ui.tags.tr(*(ui.tags.th(label, scope="col") for _key, label in columns))),
        ui.tags.tbody(*rows),
        class_="city-exact-table",
    )


@module.ui
def overview_ui(id: str = "overview") -> Any:
    analysis_slot = ui.div(
        ui.div(
            ui.div(
                ui.input_select(
                    "fund_scope",
                    "Fund scope",
                    {"all_funds": "All funds total"},
                ),
                class_="city-story-studio__live-control",
            ),
            ui.input_action_button(
                "reset",
                ui.span("↺", aria_hidden="true"),
                class_="city-button city-button--secondary city-story-studio__live-reset",
                aria_label="Reset to FY2027 expenses and all funds",
                title="Reset to FY2027 expenses and all funds",
            ),
            class_="city-controls city-context-bar city-story-studio__live-controls",
            aria_label="Overview filters",
        ),
        ui.div(ui.output_ui("kpis"), class_="city-overview-kpis city-story-studio__live-kpis"),
        ui.div(
            chart_frame(
                "Budget change by fiscal year",
                output_widget("trend_chart", height="232px"),
                ui.div(
                    ui.output_text("trend_summary"),
                    ui.tags.details(
                        ui.tags.summary("Exact data for this chart"),
                        ui.output_ui("trend_exact"),
                        class_="city-progressive",
                    ),
                ),
                source="Source: City of Sacramento Approved Budgets",
            ),
            class_="city-story-studio__live-chart",
        ),
        class_="city-story-studio__analysis-slot",
    )
    return page_section(
        story_studio_ui(
            analysis_slot=analysis_slot,
            benchmark_value=ui.output_text("benchmark_value"),
        ),
        ui.div(
            ui.div(
                section_header(
                    "Largest changes",
                    "Choose a department to open quick detail without leaving Overview.",
                ),
                ui.output_ui("movements"),
                class_=("city-surface city-surface--panel city-overview-next city-overview-movement-panel"),
            ),
            ui.div(
                section_header(
                    "Fund-scope summary",
                    "Approved expense scopes preserve the citywide reconciliation while making "
                    "restricted and operational contexts visible.",
                ),
                ui.output_ui("fund_scopes"),
                class_=("city-surface city-surface--panel city-overview-next city-overview-scope-panel"),
            ),
            class_="city-overview-summary-grid",
        ),
        ui.div(
            ui.output_ui("workspace"),
            ui.output_ui("state"),
            class_="city-overview-continuation",
        ),
        section_id="overview",
    )


@module.server
def overview_server(
    input: Any,
    output: Any,
    session: Any,
    snapshot: Any,
    selection: Any,
    detail_selection: Any,
    drawer_desired_open: Any,
    workspace_desired_open: Any,
    presentation_lens: Any,
    defer_context_callback: Callable[[OverviewSelectionState], None],
    detail_close_signal: Any | None = None,
) -> OverviewController:
    """Bind Overview outputs to the shared per-session selection state."""

    @reactive.calc
    def frame() -> pd.DataFrame:
        return coerce_snapshot(snapshot)

    @reactive.calc
    def bundle() -> Any:
        return coerce_bundle(snapshot)

    def _available_years() -> list[int]:
        current_bundle = bundle()
        if current_bundle is not None:
            return list(current_bundle.years)
        return [int(value) for value in years(frame())]

    def _default_state() -> OverviewSelectionState:
        value = frame()
        current_bundle = bundle()
        return sanitize_overview_selection(
            None,
            years=_available_years(),
            departments=(
                current_bundle.choices_for("department")
                if current_bundle is not None
                else tuple(value["department"].dropna().astype(str).unique())
            )
            if not value.empty
            else (),
            funds=(
                current_bundle.choices_for("fund")
                if current_bundle is not None
                else tuple(value["fund"].dropna().astype(str).unique())
            )
            if not value.empty
            else (),
            categories=(
                current_bundle.choices_for("category")
                if current_bundle is not None
                else tuple(value["category"].dropna().astype(str).unique())
            )
            if not value.empty
            else (),
            records=tuple(value["object_id"].dropna().astype(int).unique()) if not value.empty else (),
        )

    def _sanitize_state(value: OverviewSelectionState) -> OverviewSelectionState:
        data = frame()
        current_bundle = bundle()
        safe = sanitize_overview_selection(
            value,
            years=_available_years(),
            departments=(
                current_bundle.choices_for("department")
                if current_bundle is not None
                else tuple(data["department"].dropna().astype(str).unique())
            )
            if not data.empty
            else (),
            funds=(
                current_bundle.choices_for("fund")
                if current_bundle is not None
                else tuple(data["fund"].dropna().astype(str).unique())
            )
            if not data.empty
            else (),
            categories=(
                current_bundle.choices_for("category")
                if current_bundle is not None
                else tuple(data["category"].dropna().astype(str).unique())
            )
            if not data.empty
            else (),
            records=tuple(data["object_id"].dropna().astype(int).unique()) if not data.empty else (),
        )
        if data.empty:
            return safe
        context = _state_rows(data, safe, year=None, include_hierarchy=False)
        department = safe.department
        fund = safe.fund
        category = safe.category
        record = safe.selected_record
        if department and department not in set(context["department"].astype(str)):
            department = fund = category = None
            record = None
        if department:
            context = context.loc[context["department"].astype(str).eq(department)]
        if fund and fund not in set(context["fund"].astype(str)):
            fund = category = None
            record = None
        if fund:
            context = context.loc[context["fund"].astype(str).eq(fund)]
        if category and category not in set(context["category"].astype(str)):
            category = None
            record = None
        candidate = safe.updated(
            department=department,
            fund=fund,
            category=category,
            selected_record=record,
        )
        if record is not None:
            current = _state_rows(data, candidate, year=candidate.year)
            if record not in set(current["object_id"].astype(int)):
                candidate = candidate.updated(selected_record=None)
        return candidate

    @reactive.calc
    def current_state() -> OverviewSelectionState:
        """Sanitize once per source or selection invalidation."""

        return _sanitize_state(selection())

    def _update_context_inputs(value: OverviewSelectionState) -> None:
        ui.update_select(
            "fund_scope",
            choices=FUND_SCOPE_LABELS,
            selected=value.fund_scope,
            session=session,
        )

    def _set_value(value: Any, candidate: Any) -> None:
        if value.get() != candidate:
            value.set(candidate)

    def _set_presentation_lens(value: Any) -> None:
        candidate = str(value or "authority")
        _set_value(
            presentation_lens,
            candidate if candidate in VALID_PRESENTATION_LENSES else "authority",
        )

    def restore(value: OverviewSelectionState, presentation: OverviewPresentationState) -> None:
        # Bookmark restoration runs from a post-flush callback, outside a normal
        # reactive consumer. Isolate the reads used to revalidate current source values.
        with reactive.isolate():
            safe = _sanitize_state(value)
            _set_value(selection, safe)
            _set_presentation_lens(presentation.lens)
            _set_value(workspace_desired_open, presentation.workspace_open)
            if presentation.drawer_open:
                _set_value(detail_selection, safe)
            _set_value(drawer_desired_open, presentation.drawer_open)
            _update_context_inputs(safe)

    def open_selection(payload: Mapping[str, Any] | None = None) -> None:
        raw = dict(payload or {})
        current = current_state()
        updates: dict[str, Any] = {}

        # Every explicit selection resolves its presentation meaning. Missing
        # lenses are ordinary authority selections, preserving old triggers.
        _set_presentation_lens(raw.get("lens"))

        for key in ("year", "compare_year"):
            if key in raw:
                with suppress(TypeError, ValueError):
                    updates[key] = int(raw[key])
        if "flow" in raw and str(raw["flow"]) in FLOW_LABELS:
            updates["flow"] = str(raw["flow"])
        if "fund_scope" in raw:
            scope = str(raw["fund_scope"])
            if scope in FUND_SCOPE_LABELS:
                updates["fund_scope"] = scope

        if "department" in raw:
            department = str(raw.get("department") or "").strip()
            updates.update(
                department=None if department in {"", "all"} else department,
                fund=None,
                category=None,
                selected_record=None,
            )
        if "fund" in raw:
            fund = str(raw.get("fund") or "").strip()
            updates.update(
                fund=None if fund in {"", "all"} else fund,
                category=None,
                selected_record=None,
            )
        if "category" in raw:
            category = str(raw.get("category") or "").strip()
            updates.update(
                category=None if category in {"", "all"} else category,
                selected_record=None,
            )
        if "selected_record" in raw:
            try:
                updates["selected_record"] = int(raw["selected_record"])
            except (TypeError, ValueError):
                updates["selected_record"] = None
        if "workspace_open" in raw:
            _set_value(workspace_desired_open, bool(raw["workspace_open"]))

        updated = _sanitize_state(current.updated(**updates))
        defer_context_callback(updated)
        _set_value(drawer_desired_open, True)

    @reactive.effect
    def _initialize() -> None:
        if frame().empty:
            return
        current = selection.get()
        safe = _sanitize_state(current)
        if safe != current:
            selection.set(safe)
            if drawer_desired_open.get():
                _set_value(detail_selection, safe)
        _update_context_inputs(safe)

    def _sync_context_value(**updates: Any) -> None:
        if frame().empty:
            return
        current = current_state()
        safe = _sanitize_state(current.updated(**updates, selected_record=None))
        if safe != current:
            _set_presentation_lens("authority")
            selection.set(safe)

    def _selected_year(raw: Any, fallback: int | None) -> int | None:
        try:
            candidate = int(raw)
        except (TypeError, ValueError):
            return fallback
        return candidate if candidate in _available_years() else fallback

    @reactive.effect
    @reactive.event(input.fund_scope)
    def _sync_fund_scope() -> None:
        value = str(input.fund_scope())
        _sync_context_value(fund_scope=value if value in FUND_SCOPE_LABELS else "all_funds")

    @reactive.effect
    @reactive.event(input.measure_request)
    def _sync_measure_request() -> None:
        requested = str(input.measure_request() or "")
        if requested in {"revenue", "expense"}:
            _sync_context_value(flow=requested)

    @reactive.effect
    @reactive.event(input.year_request)
    def _sync_year_request() -> None:
        payload = input.year_request()
        requested = payload.get("year") if isinstance(payload, Mapping) else payload
        current = current_state()
        _sync_context_value(year=_selected_year(requested, current.year))

    @reactive.effect
    @reactive.event(input.selection_request)
    def _open_requested_selection() -> None:
        payload = input.selection_request()
        if isinstance(payload, Mapping):
            normalized = {
                "year": payload.get("year"),
                "flow": payload.get("flow"),
                "fund_scope": payload.get("scope"),
                "department": payload.get("department"),
                "fund": payload.get("fund"),
                "category": payload.get("category"),
                "selected_record": payload.get("record"),
                "lens": payload.get("lens"),
            }
            open_selection({key: value for key, value in normalized.items() if value is not None})

    @reactive.effect
    @reactive.event(input.legacy_drilldown)
    def _open_legacy_workspace() -> None:
        _set_presentation_lens("authority")
        _set_value(drawer_desired_open, False)
        _set_value(workspace_desired_open, True)

        async def _focus_workspace() -> None:
            await session.send_custom_message(
                "budget-workspace-focus",
                {"id": "overview-analysis-workspace"},
            )

        session.on_flushed(_focus_workspace, once=True)

    @reactive.effect
    @reactive.event(input.reset)
    def _reset() -> None:
        reset = _default_state()
        _set_value(selection, reset)
        _set_presentation_lens("authority")
        _set_value(workspace_desired_open, False)
        _update_context_inputs(reset)

    @reactive.effect
    @reactive.event(input.workspace_department, input.workspace_fund, input.workspace_category)
    def _sync_workspace_inputs() -> None:
        current = selection.get()

        def optional(value: Any) -> str | None:
            candidate = str(value or "").strip()
            return None if candidate in {"", "all"} else candidate

        department = optional(input.workspace_department())
        fund = optional(input.workspace_fund())
        category = optional(input.workspace_category())
        if department != current.department:
            fund = None
            category = None
        elif fund != current.fund:
            category = None
        updated = _sanitize_state(
            current.updated(
                department=department,
                fund=fund,
                category=category,
                selected_record=None,
            )
        )
        if updated != current:
            _set_presentation_lens("authority")
            selection.set(updated)

    @reactive.effect
    @reactive.event(input.workspace_back)
    def _workspace_back() -> None:
        _set_presentation_lens("authority")
        current = selection.get()
        if current.selected_record is not None:
            updated = current.updated(selected_record=None)
        elif current.category is not None:
            updated = current.updated(category=None)
        elif current.fund is not None:
            updated = current.updated(fund=None, category=None)
        elif current.department is not None:
            updated = current.updated(department=None, fund=None, category=None)
        else:
            updated = current
        selection.set(updated)

    @reactive.effect
    @reactive.event(input.workspace_clear)
    def _workspace_clear() -> None:
        _set_presentation_lens("authority")
        current = selection.get()
        selection.set(
            current.updated(
                department=None,
                fund=None,
                category=None,
                selected_record=None,
            )
        )

    @reactive.effect
    @reactive.event(input.workspace_collapse)
    def _workspace_collapse() -> None:
        _set_value(workspace_desired_open, False)

    @reactive.calc
    def current_rows() -> pd.DataFrame:
        current = current_state()
        return _state_rows(frame(), current, year=current.year)

    @reactive.calc
    def comparison_rows() -> pd.DataFrame:
        current = current_state()
        return _state_rows(frame(), current, year=current.compare_year)

    @reactive.calc
    def history_rows() -> pd.DataFrame:
        return _state_rows(frame(), current_state(), year=None)

    def _measure_summary(flow: str) -> OverviewMeasureSummary | None:
        current = current_state()
        if frame().empty or current.year is None:
            return None
        return build_overview_measure_summary(
            frame(),
            year=current.year,
            flow=flow,  # type: ignore[arg-type]
            fund_scope=current.fund_scope,
        )

    def context_year() -> str:
        current = current_state()
        return f"FY{current.year}" if current.year is not None else "Fiscal year unavailable"

    def benchmark_value() -> str:
        data = frame()
        return format_currency(fixed_fy2027_expense_benchmark(data)) if not data.empty else "Not available"

    def kpis() -> Any:
        data = frame()
        current = current_state()
        if data.empty or current.year is None:
            return empty_state(
                "Waiting for a budget snapshot",
                "The Overview will populate after the source refresh completes.",
            )
        revenue = _measure_summary("revenue")
        expense = _measure_summary("expense")
        selected = expense if current.flow == "expense" else revenue
        assert revenue is not None
        assert expense is not None
        assert selected is not None

        def interactive_card(
            label: str,
            summary: OverviewMeasureSummary,
            *,
            flow: str,
            tone: str,
        ) -> Any:
            return ui.tags.button(
                ui.span(label, class_="city-stat-card__label"),
                ui.span(format_currency(summary.current_amount), class_="city-stat-card__value tabular"),
                ui.span(
                    f"Viewing {label.lower()}" if current.flow == flow else f"View {label.lower()}",
                    class_="city-stat-card__detail",
                ),
                type="button",
                class_=f"city-stat-card city-stat-card--{tone} city-kpi-button",
                data_overview_measure=flow,
                aria_pressed="true" if current.flow == flow else "false",
                aria_label=f"View {label.lower()} for fiscal year {current.year}",
            )

        if selected.change_amount is None:
            change_detail = f"Comparison from FY{selected.prior_year} unavailable"
            change_value = "Not available"
        elif selected.prior_amount == 0:
            change_detail = f"New in FY{selected.year}"
            change_value = format_signed_currency(selected.change_amount)
        else:
            change_detail = format_signed_percent(selected.change_percent or 0)
            change_value = format_signed_currency(selected.change_amount)
        largest_detail = (
            f"{format_currency(selected.largest_department_amount)} · "
            f"{selected.largest_department_share:.1%} of FY{selected.year} {selected.measure.lower()}"
            if selected.largest_department_amount is not None and selected.largest_department_share is not None
            else "No department amount is available"
        )
        return ui.div(
            interactive_card(
                "Approved revenue estimate",
                revenue,
                flow="revenue",
                tone="sky",
            ),
            interactive_card(
                "Approved spending plan",
                expense,
                flow="expense",
                tone="gold",
            ),
            stat_card(
                f"Change from FY{selected.prior_year}",
                change_value,
                change_detail,
                tone="green" if (selected.change_amount or 0) >= 0 else "gold",
            ),
            stat_card(
                "Largest department",
                selected.largest_department or "Not available",
                largest_detail,
                tone="cobalt",
            ),
            class_="city-grid city-grid--4",
        )

    def _movement_data() -> pd.DataFrame:
        current = current_state()
        current_bundle = bundle()
        if current_bundle is not None and current.year is not None and current.compare_year is not None:
            flow_value = FLOW_VALUES.get(current.flow, "all")
            hierarchy = current_bundle.hierarchy(
                "department",
                flow=None if flow_value == "all" else flow_value,
                scope=current.fund_scope,
            )
            hierarchy = hierarchy.loc[hierarchy["fiscal_year"].isin([current.year, current.compare_year])]
            if hierarchy.empty:
                return pd.DataFrame()
            current_totals = (
                hierarchy.loc[hierarchy["fiscal_year"].eq(current.year)].groupby("name")["amount"].sum()
            )
            prior_totals = (
                hierarchy.loc[hierarchy["fiscal_year"].eq(current.compare_year)]
                .groupby("name")["amount"]
                .sum()
            )
            result = pd.concat({"current": current_totals, "prior": prior_totals}, axis=1).fillna(0)
            result["change"] = result["current"] - result["prior"]
            return (
                result.reset_index()
                .rename(columns={"name": "department"})
                .sort_values("change", key=lambda value: value.abs(), ascending=False)
                .head(6)
            )
        data = _state_rows(frame(), current, year=None, include_hierarchy=False)
        if data.empty or current.year is None or current.compare_year is None:
            return pd.DataFrame()
        current_totals = (
            data.loc[data["fiscal_year"].eq(current.year)].groupby("department", dropna=False)["amount"].sum()
        )
        prior_totals = (
            data.loc[data["fiscal_year"].eq(current.compare_year)]
            .groupby("department", dropna=False)["amount"]
            .sum()
        )
        result = pd.concat({"current": current_totals, "prior": prior_totals}, axis=1).fillna(0)
        result["change"] = result["current"] - result["prior"]
        return (
            result.reset_index().sort_values("change", key=lambda value: value.abs(), ascending=False).head(6)
        )

    def movements() -> Any:
        current = current_state()
        data = _movement_data()
        if data.empty:
            return empty_state("No department changes are available")
        max_change = float(data["change"].abs().max())
        cards = []
        for row in data.itertuples(index=False):
            department = str(row.department or "Unspecified department")
            selected = department == current.department
            change = float(row.change)
            direction = "positive" if change >= 0 else "negative"
            width = min(100.0, abs(change) / max_change * 100.0) if max_change else 0.0
            movement_label = (
                f"{department}: change {format_currency(change)}; "
                f"FY{current.year} total {format_currency(row.current)}; "
                f"FY{current.compare_year} total {format_currency(row.prior)}"
            )
            cards.append(
                ui.tags.button(
                    ui.span(department, class_="city-movement__label"),
                    ui.span(
                        ui.span(
                            class_="city-movement__bar-fill",
                            style=f"width: {width:.2f}%",
                        ),
                        class_="city-movement__bar",
                        aria_hidden="true",
                    ),
                    ui.span(
                        format_currency(change, compact=True),
                        class_="city-movement__value tabular",
                    ),
                    ui.span(
                        f"FY{current.year} {format_currency(row.current, compact=True)}",
                        class_="city-movement__context",
                    ),
                    type="button",
                    class_=f"city-movement{' is-selected' if selected else ''}",
                    data_overview_select="true",
                    data_selection_department=department,
                    data_movement_direction=direction,
                    aria_pressed="true" if selected else "false",
                    aria_label=movement_label,
                    title=movement_label,
                )
            )
        return ui.div(*cards, class_="city-movement-list")

    def trend_data() -> pd.DataFrame:
        current = current_state()
        current_bundle = bundle()
        if current_bundle is not None:
            flow_value = FLOW_VALUES.get(current.flow, "all")
            scope = current.fund_scope
            totals = current_bundle.aggregate("totals_by_year_flow_scope")
            totals = totals.loc[totals["fund_scope"].eq(scope)]
            if flow_value != "all":
                totals = totals.loc[totals["expense_revenue"].eq(flow_value)]
            return totals.groupby("fiscal_year", as_index=False)["amount"].sum().sort_values("fiscal_year")
        data = _state_rows(frame(), current, year=None, include_hierarchy=False)
        if data.empty:
            return pd.DataFrame(columns=["fiscal_year", "amount"])
        return data.groupby("fiscal_year", as_index=False)["amount"].sum().sort_values("fiscal_year")

    def trend_chart() -> Any:
        data = trend_data()
        current = current_state()
        if data.empty:
            return go.FigureWidget()
        selected = data["fiscal_year"].eq(current.year)
        figure = go.FigureWidget(
            go.Bar(
                x=data["fiscal_year"].map(lambda year: f"FY{int(year)}"),
                y=data["amount"],
                marker={
                    "color": ["#003c71" if value else "#0072ce" for value in selected],
                    "line": {
                        "color": ["#c99a3b" if value else "rgba(0,0,0,0)" for value in selected],
                        "width": [3 if value else 0 for value in selected],
                    },
                },
                hovertemplate="%{x}<br>$%{y:,.0f}<br>View %{x} details<extra></extra>",
                name=FLOW_LABELS[current.flow],
            )
        )

        def _open_year(_trace: Any, points: Any, _state: Any) -> None:
            if not points.point_inds:
                return
            selected_year = int(data.iloc[points.point_inds[0]]["fiscal_year"])
            _sync_context_value(year=selected_year)

        figure.data[0].on_click(_open_year)
        figure.update_layout(
            margin=dict(l=18, r=12, t=12, b=42),
            height=330,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", color="#0f172a"),
            xaxis=dict(title=None, fixedrange=True),
            yaxis=dict(
                title=None,
                tickprefix="$",
                separatethousands=True,
                gridcolor="#e2e6ed",
                zeroline=False,
                fixedrange=True,
            ),
            showlegend=False,
        )
        return figure

    def trend_summary() -> str:
        data = trend_data()
        current = current_state()
        if data.empty or current.year is None:
            return "No trend is available until the normalized snapshot is ready."
        summary = _measure_summary(current.flow)
        if summary is None:
            return "No change is available until the normalized snapshot is ready."
        if summary.change_amount is None:
            return (
                f"FY{summary.year}: {format_currency(summary.current_amount)} | "
                f"Change from FY{summary.prior_year}: unavailable"
            )
        if summary.prior_amount == 0:
            return (
                f"FY{summary.year}: {format_currency(summary.current_amount)} | "
                f"Change from FY{summary.prior_year}: {format_signed_currency(summary.change_amount)} | "
                f"New in FY{summary.year}"
            )
        return (
            f"FY{summary.year}: {format_currency(summary.current_amount)} | "
            f"Change from FY{summary.prior_year}: {format_signed_currency(summary.change_amount)} "
            f"({format_signed_percent(summary.change_percent or 0)})"
        )

    def trend_exact() -> Any:
        data = trend_data().rename(columns={"fiscal_year": "year"})
        return _exact_table(
            data,
            columns=(("year", "Fiscal year"), ("amount", "Approved amount")),
            caption="Exact annual approved budget totals for the active Overview context.",
            limit=40,
        )

    def fund_scopes() -> Any:
        data = frame()
        current = current_state()
        if data.empty or current.year is None:
            return empty_state("Fund scopes are unavailable")
        current_bundle = bundle()
        if current_bundle is not None:
            totals = current_bundle.aggregate("fund_scope_totals")
            totals = (
                totals.loc[totals["fiscal_year"].eq(current.year) & totals["expenses"].gt(0)]
                .rename(columns={"expenses": "amount", "line_items": "records"})
                .sort_values("amount", ascending=False)
            )
        else:
            expenses = data.loc[data["fiscal_year"].eq(current.year) & data["expense_revenue"].eq("Expenses")]
            scoped = ensure_scope_column(expenses)
            totals = (
                scoped.groupby("fund_scope", as_index=False)
                .agg(amount=("amount", "sum"), records=("object_id", "size"))
                .sort_values("amount", ascending=False)
            )
        total = float(totals["amount"].sum())
        cards = []
        for row in totals.itertuples(index=False):
            label = FUND_SCOPE_LABELS.get(str(row.fund_scope), str(row.fund_scope))
            selected = current.fund_scope == str(row.fund_scope)
            detail = (
                f"{row.amount / total:.1%} of FY{current.year} expenses, {row.records:,} records"
                if total
                else "No approved expenses"
            )
            tone = "cobalt" if row.fund_scope == "general_fund" else "sky"
            cards.append(
                ui.tags.button(
                    ui.span(label, class_="city-stat-card__label"),
                    ui.span(
                        format_currency(row.amount, compact=True),
                        class_="city-stat-card__value tabular",
                    ),
                    ui.span(detail, class_="city-stat-card__detail"),
                    type="button",
                    class_=(
                        f"city-stat-card city-stat-card--{tone} city-interactive-card"
                        + (" is-selected" if selected else "")
                    ),
                    data_overview_select="true",
                    data_selection_year=str(current.year),
                    data_selection_flow="expense",
                    data_selection_scope=str(row.fund_scope),
                    data_selection_department="",
                    aria_pressed="true" if selected else "false",
                )
            )
        return ui.div(*cards, class_="city-grid city-grid--3")

    def _workspace_choices(
        state: OverviewSelectionState,
    ) -> tuple[list[str], list[str], list[str]]:
        current_bundle = bundle()
        if current_bundle is not None:
            departments = list(current_bundle.choices_for("department"))
            funds = list(current_bundle.choices_for("fund", department=state.department))
            categories = list(
                current_bundle.choices_for("category", department=state.department, fund=state.fund)
            )
            return departments, funds, categories
        data = _state_rows(frame(), state, year=None, include_hierarchy=False)
        departments = sorted(data["department"].dropna().astype(str).unique())
        if state.department:
            data = data.loc[data["department"].astype(str).eq(state.department)]
        funds = sorted(data["fund"].dropna().astype(str).unique())
        if state.fund:
            data = data.loc[data["fund"].astype(str).eq(state.fund)]
        categories = sorted(data["category"].dropna().astype(str).unique())
        return departments, funds, categories

    def workspace() -> Any:
        current = current_state()
        if not workspace_desired_open():
            return ui.div()
        departments, funds, categories = _workspace_choices(current)

        def choices(label: str, values: list[str]) -> dict[str, str]:
            return {"all": label, **{value: value for value in values}}

        return ui.tags.section(
            ui.div(
                ui.div(
                    ui.div("Integrated analysis", class_="city-eyebrow"),
                    ui.h2("Explore the selected budget context", class_="city-section-title"),
                    ui.p(_hierarchy_label(current), class_="city-workspace-breadcrumb"),
                ),
                ui.div(
                    ui.input_action_button(
                        "workspace_back",
                        "Back one level",
                        class_="city-button city-button--secondary",
                        disabled=(
                            current.department is None
                            and current.fund is None
                            and current.category is None
                            and current.selected_record is None
                        ),
                    ),
                    ui.input_action_button(
                        "workspace_clear",
                        "Clear selection",
                        class_="city-button city-button--secondary",
                    ),
                    ui.input_action_button(
                        "workspace_collapse",
                        "Collapse analysis",
                        class_="city-button city-button--quiet",
                    ),
                    class_="city-action-row",
                ),
                class_="city-workspace-header",
            ),
            ui.div(
                ui.div(
                    ui.input_select(
                        "workspace_department",
                        "Department",
                        choices("All departments", departments),
                        selected=current.department or "all",
                    ),
                    class_="city-control",
                ),
                ui.div(
                    ui.input_select(
                        "workspace_fund",
                        "Fund",
                        choices("All funds", funds),
                        selected=current.fund or "all",
                    ),
                    class_="city-control",
                ),
                ui.div(
                    ui.input_select(
                        "workspace_category",
                        "Category",
                        choices("All categories", categories),
                        selected=current.category or "all",
                    ),
                    class_="city-control",
                ),
                class_="city-controls",
                aria_label="Integrated analysis hierarchy",
            ),
            ui.output_ui("workspace_metrics"),
            ui.div(
                chart_frame(
                    f"Budget by {_next_dimension(current)}",
                    output_widget("workspace_chart", height="420px"),
                    ui.output_text("workspace_chart_summary"),
                ),
                ui.div(
                    section_header(
                        "Composition",
                        "Choose the next level to keep charts, totals, and records linked.",
                    ),
                    ui.output_ui("workspace_composition"),
                    class_="city-surface city-surface--panel city-overview-next",
                ),
                class_="city-split city-split--wide city-workspace-grid",
            ),
            chart_frame(
                "Historical trend",
                output_widget("workspace_trend", height="320px"),
                ui.tags.details(
                    ui.tags.summary("Exact data for this trend"),
                    ui.output_ui("workspace_trend_exact"),
                    class_="city-progressive",
                ),
            ),
            ui.div(
                ui.div(
                    section_header(
                        "Exact supporting records",
                        "Select one row to open its ObjectId and synchronized quick detail.",
                    ),
                    ui.div(
                        ui.output_data_frame("workspace_table"),
                        class_="city-table-wrap",
                        id="overview-records",
                    ),
                    ui.output_text("workspace_table_summary"),
                ),
                ui.output_ui("workspace_record_detail"),
                class_="city-chart-grid",
            ),
            id="overview-analysis-workspace",
            tabindex="-1",
            class_="city-workspace",
            aria_label="Expanded Overview analysis",
        )

    def workspace_metrics() -> Any:
        current = current_state()
        current_total = float(current_rows()["amount"].sum())
        prior_total = float(comparison_rows()["amount"].sum())
        change = current_total - prior_total
        percent = change / prior_total * 100 if prior_total else None
        return ui.div(
            stat_card(
                f"FY{current.year}",
                format_currency(current_total, compact=True),
                _hierarchy_label(current),
                tone="cobalt",
            ),
            stat_card(
                f"FY{current.compare_year}",
                format_currency(prior_total, compact=True),
                "Comparison amount",
                tone="sky",
            ),
            stat_card(
                "Change",
                format_currency(change, compact=True),
                format_percent(percent) if percent is not None else "Percentage unavailable",
                tone="green" if change >= 0 else "gold",
            ),
            stat_card(
                "Exact records",
                f"{len(current_rows()):,}",
                "Current-year supporting rows",
                tone="cobalt",
            ),
            class_="city-grid city-grid--4 city-detail-metrics",
        )

    def workspace_groups() -> pd.DataFrame:
        current = current_state()
        dimension = _next_dimension(current)
        data = current_rows()
        if data.empty:
            return pd.DataFrame(columns=[dimension, "amount", "records"])
        return (
            data.groupby(dimension, as_index=False, dropna=False)
            .agg(amount=("amount", "sum"), records=("object_id", "size"))
            .sort_values("amount", ascending=False)
            .head(15)
        )

    def workspace_chart() -> Any:
        current = current_state()
        dimension = _next_dimension(current)
        data = workspace_groups().sort_values("amount")
        if data.empty:
            return go.FigureWidget()
        full_labels = data[dimension].fillna("Unspecified").astype(str)
        labels = full_labels.map(compact_chart_label)
        figure = go.FigureWidget(
            go.Bar(
                x=data["amount"],
                y=labels,
                orientation="h",
                marker_color="#0072ce",
                customdata=pd.DataFrame(
                    {
                        "label": full_labels,
                        "records": data["records"],
                    }
                ).to_numpy(),
                hovertemplate=(
                    "%{customdata[0]}<br>$%{x:,.0f}<br>%{customdata[1]:,} exact records<extra></extra>"
                ),
            )
        )

        def _open_group(_trace: Any, points: Any, _state: Any) -> None:
            if not points.point_inds:
                return
            row = data.iloc[points.point_inds[0]]
            open_selection({dimension: str(row[dimension])})

        figure.data[0].on_click(_open_group)
        figure.update_layout(
            margin=dict(l=20, r=16, t=12, b=36),
            height=max(340, len(data) * 30),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif"),
            xaxis=dict(
                tickprefix="$",
                separatethousands=True,
                gridcolor="#e2e6ed",
                fixedrange=True,
            ),
            yaxis=dict(automargin=True, fixedrange=True),
            showlegend=False,
        )
        return figure

    def workspace_chart_summary() -> str:
        current = current_state()
        return (
            f"Showing up to 15 {_next_dimension(current)} totals from "
            f"{len(current_rows()):,} exact FY{current.year} records."
        )

    def workspace_composition() -> Any:
        current = current_state()
        dimension = _next_dimension(current)
        data = workspace_groups().head(8)
        if data.empty:
            return empty_state("No composition is available")
        total = float(current_rows()["amount"].sum())
        buttons = []
        for row in data.itertuples(index=False):
            values = row._asdict()
            label = str(values[dimension] or "Unspecified")
            amount = float(values["amount"])
            share = amount / total if total else 0
            movement_label = f"{label}: {format_currency(amount, compact=True)} ({share:.1%})"
            buttons.append(
                ui.tags.button(
                    ui.span(label, class_="city-movement__label"),
                    ui.span(
                        f"{format_currency(amount, compact=True)} · {share:.1%}",
                        class_="city-movement__value tabular",
                    ),
                    type="button",
                    class_="city-movement",
                    data_overview_select="true",
                    **{f"data_selection_{dimension}": label},
                    aria_label=movement_label,
                    title=movement_label,
                )
            )
        return ui.div(*buttons, class_="city-movement-list")

    def workspace_trend_data() -> pd.DataFrame:
        data = history_rows()
        if data.empty:
            return pd.DataFrame(columns=["fiscal_year", "amount"])
        return data.groupby("fiscal_year", as_index=False)["amount"].sum().sort_values("fiscal_year")

    def workspace_trend() -> Any:
        data = workspace_trend_data()
        current = current_state()
        if data.empty:
            return go.FigureWidget()
        figure = go.FigureWidget(
            go.Scatter(
                x=data["fiscal_year"].astype(str),
                y=data["amount"],
                mode="lines+markers",
                line=dict(color="#0072ce", width=3),
                marker=dict(
                    color=[
                        "#003c71" if int(year) == current.year else "#0072ce" for year in data["fiscal_year"]
                    ],
                    size=8,
                ),
                hovertemplate="FY%{x}<br>$%{y:,.0f}<extra></extra>",
            )
        )
        figure.update_layout(
            margin=dict(l=18, r=12, t=12, b=42),
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif"),
            xaxis=dict(fixedrange=True),
            yaxis=dict(
                tickprefix="$",
                separatethousands=True,
                gridcolor="#e2e6ed",
                fixedrange=True,
            ),
            showlegend=False,
        )
        return figure

    def workspace_trend_exact() -> Any:
        data = workspace_trend_data().rename(columns={"fiscal_year": "year"})
        return _exact_table(
            data,
            columns=(("year", "Fiscal year"), ("amount", "Approved amount")),
            caption=f"Exact historical totals for {_hierarchy_label(selection.get())}.",
            limit=40,
        )

    def workspace_table() -> Any:
        data = current_rows()
        if data.empty:
            return render.DataGrid(
                pd.DataFrame({"Status": ["No records match the active context."]}),
                selection_mode="none",
            )
        display = data[
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
        return render.DataGrid(
            display,
            height="420px",
            filters=True,
            selection_mode="row",
        )

    table_renderer = render.data_frame(workspace_table)
    last_table_record = reactive.Value[int | None](None)
    suppress_table_record_open = reactive.Value(False)

    if detail_close_signal is not None:

        @reactive.effect
        @reactive.event(detail_close_signal, ignore_init=True)
        async def _clear_workspace_record_selection() -> None:
            try:
                selected = table_renderer.data_view(selected=True)
            except Exception:
                selected = pd.DataFrame()
            if not isinstance(selected, pd.DataFrame) or len(selected) != 1:
                last_table_record.set(None)
                return
            suppress_table_record_open.set(True)
            try:
                await table_renderer.update_cell_selection(None)
            except Exception:
                # The workspace table may not be mounted in the active view.
                suppress_table_record_open.set(False)
                last_table_record.set(None)
                return

    @reactive.effect
    def _open_workspace_record() -> None:
        try:
            selected = table_renderer.data_view(selected=True)
        except Exception:
            return
        if not isinstance(selected, pd.DataFrame) or len(selected) != 1:
            if last_table_record.get() is not None:
                last_table_record.set(None)
            if suppress_table_record_open.get():
                suppress_table_record_open.set(False)
            return
        if suppress_table_record_open.get():
            return
        row = selected.iloc[0]
        record = int(row["object_id"])
        if last_table_record.get() == record:
            return
        last_table_record.set(record)
        open_selection(
            {
                "department": str(row["department"]),
                "fund": str(row["fund"]),
                "category": str(row["category"]),
                "selected_record": record,
                "workspace_open": True,
            }
        )

    def workspace_table_summary() -> str:
        return (
            f"Showing up to 1,000 records. {len(current_rows()):,} exact records "
            "match the integrated analysis context."
        )

    def workspace_record_detail() -> Any:
        current = current_state()
        if current.selected_record is None:
            return ui.div(
                ui.h3("Record detail", class_="city-card-heading"),
                ui.p("Select one row to see its exact ObjectId and open synchronized quick detail."),
                class_="city-surface city-surface--panel city-compact-detail",
            )
        row = frame().loc[frame()["object_id"].eq(current.selected_record)]
        if row.empty:
            return empty_state("The selected record is no longer available")
        record = row.iloc[0]
        return ui.div(
            ui.div("Exact source record", class_="city-eyebrow"),
            ui.h3(f"ObjectId {current.selected_record}", class_="city-card-heading"),
            ui.p(f"{record['department']} / {record['fund']} / {record['category']}"),
            ui.p(
                f"{format_currency(record['amount'])} · {record['expense_revenue']} · "
                f"FY{int(record['fiscal_year'])}"
            ),
            class_="city-surface city-surface--panel city-compact-detail",
        )

    def state_output() -> Any:
        if frame().empty:
            return empty_state(
                "Waiting for the budget snapshot",
                "Overview content will appear after the approved budget source is ready.",
            )
        if current_rows().empty:
            return empty_state(
                "No records match this context",
                "Reset the view or clear one hierarchy selection.",
            )
        return ui.div(aria_live="polite", class_="city-overview-status")

    output(render.text(context_year), id="context_year")
    output(render.text(benchmark_value), id="benchmark_value")
    output(render.ui(kpis), id="kpis")
    output(render.ui(movements), id="movements")
    output(render_widget(trend_chart), id="trend_chart")
    output(render.text(trend_summary), id="trend_summary")
    output(render.ui(trend_exact), id="trend_exact")
    output(render.ui(fund_scopes), id="fund_scopes")
    output(render.ui(workspace), id="workspace")
    output(render.ui(workspace_metrics), id="workspace_metrics")
    output(render_widget(workspace_chart), id="workspace_chart")
    output(render.text(workspace_chart_summary), id="workspace_chart_summary")
    output(render.ui(workspace_composition), id="workspace_composition")
    output(render_widget(workspace_trend), id="workspace_trend")
    output(render.ui(workspace_trend_exact), id="workspace_trend_exact")
    output(table_renderer, id="workspace_table")
    output(render.text(workspace_table_summary), id="workspace_table_summary")
    output(render.ui(workspace_record_detail), id="workspace_record_detail")
    output(render.ui(state_output), id="state")

    def _overview_test_state() -> dict[str, Any]:
        current = current_state()
        return {
            "selection": current.as_bookmark_value(),
            "current_rows": len(current_rows()),
            "comparison_rows": len(comparison_rows()),
            "history_rows": len(history_rows()),
        }

    export_test_values(test_state=_overview_test_state)

    return OverviewController(open_selection=open_selection, restore=restore)
