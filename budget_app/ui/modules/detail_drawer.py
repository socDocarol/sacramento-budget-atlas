"""Persistent accessible Overview detail drawer for the Sacramento budget story."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_widget

from budget_app.data import FUND_SCOPE_LABELS
from budget_app.state import OverviewSelectionState

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


@module.ui
def detail_drawer_ui(id: str = "detail") -> Any:
    """Render one stable drawer shell. Server outputs fill its content slots."""

    ns = module.resolve_id(id)

    def action(name: str, label: str, *, class_: str, **attrs: Any) -> Any:
        return ui.input_action_button(name, label, class_=class_, **attrs)

    def metric(label: str, output_id: str, detail_id: str, *, tone: str) -> Any:
        return ui.div(
            ui.span(label, class_="city-stat-card__label"),
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
                    ui.div("Approved budget detail", class_="city-eyebrow"),
                    ui.h2(
                        ui.output_text("title_text", inline=True),
                        id=ns("title"),
                        class_="city-detail-drawer__title",
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
                    metric("Current approved total", "current_total", "current_detail", tone="cobalt"),
                    metric("Comparison total", "compare_total", "compare_detail", tone="sky"),
                    ui.div(
                        ui.span("Change", class_="city-stat-card__label"),
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
                    metric("Exact records", "record_count", "record_count_detail", tone="green"),
                    class_="city-grid city-grid--2 city-detail-kpis city-detail-metrics",
                ),
                ui.div(
                    ui.h3("Historical approved amounts", class_="city-card-heading"),
                    ui.div(
                        ui.output_ui("trend_state"),
                        output_widget("trend", height="240px"),
                        class_="city-detail-trend",
                    ),
                    ui.output_ui("annual_table"),
                    ui.p(
                        "Historical approved budget totals for the selected hierarchy. This is not actual spending or a forecast.",
                        class_="city-chart-summary",
                    ),
                    class_="city-surface city-surface--outlined city-chart-frame",
                ),
                ui.div(
                    ui.h3("Composition", class_="city-card-heading"),
                    ui.output_ui("composition"),
                    class_="city-surface city-surface--panel",
                ),
                ui.div(
                    ui.h3("Exact record detail", class_="city-card-heading"),
                    ui.output_ui("record_detail"),
                    ui.output_ui("exact_table"),
                    class_="city-surface city-surface--outlined",
                ),
                class_="city-detail-drawer__body",
            ),
            ui.div(
                action("back", "Back", class_="city-button city-button--secondary", data_detail_back="true"),
                action("expand", "Expand analysis", class_="city-button", data_detail_expand="true"),
                action(
                    "inspect",
                    "Inspect records",
                    class_="city-button city-button--secondary",
                    data_detail_inspect="true",
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
    def filtered_rows() -> pd.DataFrame:
        state = selection()
        value = _scope_rows(_flow_rows(frame(), state.flow), state.fund_scope)
        return _hierarchy_rows(value, state).copy()

    @reactive.calc
    def current_rows() -> pd.DataFrame:
        return _year_rows(filtered_rows(), selection().year).copy()

    @reactive.calc
    def comparison_rows() -> pd.DataFrame:
        return _year_rows(filtered_rows(), selection().compare_year).copy()

    @reactive.calc
    def historical_rows() -> pd.DataFrame:
        value = filtered_rows()
        if value.empty:
            return value
        return value.groupby("fiscal_year", as_index=False)["amount"].sum().sort_values("fiscal_year")

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

    def _change_values() -> tuple[float, float, float, float | None]:
        current_total = float(current_rows()["amount"].sum()) if not current_rows().empty else 0.0
        compare_total = float(comparison_rows()["amount"].sum()) if not comparison_rows().empty else 0.0
        change = current_total - compare_total
        percent = change / compare_total * 100 if compare_total else None
        return current_total, compare_total, change, percent

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
        dimension = _next_dimension(state)
        value = current_rows()
        if dimension is None:
            return ui.p("The selected category is the deepest available hierarchy level.")
        if value.empty:
            return empty_state(
                "No composition is available",
                "No exact approved records match the current hierarchy and year.",
            )
        grouped = (
            value.groupby(dimension, dropna=False)["amount"]
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
            items.append(
                ui.tags.li(
                    ui.span(display, class_="city-detail-composition__label"),
                    ui.span(
                        format_currency(amount, compact=True), class_="city-detail-composition__value tabular"
                    ),
                    class_="city-detail-composition__item",
                )
            )
        return ui.div(
            ui.p(
                f"Next level: {_DIMENSION_LABELS[dimension]}. Values are exact approved amounts in the current year.",
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
                    f"Exact approved records, showing {min(len(value), 100):,} of {len(value):,} matching rows."
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
        value = historical_rows()
        if value.empty:
            table = ui.tags.table(
                ui.tags.caption("No exact annual approved amounts are available."),
                ui.tags.thead(
                    ui.tags.tr(
                        ui.tags.th("Fiscal year", scope="col"),
                        ui.tags.th("Exact approved amount", scope="col"),
                    )
                ),
                ui.tags.tbody(ui.tags.tr(ui.tags.td("No matching records"), ui.tags.td("Not available"))),
                class_="city-exact-table",
            )
        else:
            rows = [
                ui.tags.tr(
                    ui.tags.td(f"FY{int(record.fiscal_year)}"),
                    ui.tags.td(format_currency(record.amount)),
                )
                for record in value.itertuples(index=False)
            ]
            table = ui.tags.table(
                ui.tags.caption("Exact approved amount by fiscal year for the selected hierarchy."),
                ui.tags.thead(
                    ui.tags.tr(
                        ui.tags.th("Fiscal year", scope="col"),
                        ui.tags.th("Exact approved amount", scope="col"),
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
        value = historical_rows()
        if value.empty:
            trend_ready_key.set(trend_key)
            return go.FigureWidget()
        figure = go.FigureWidget(
            go.Scatter(
                x=value["fiscal_year"].astype(str),
                y=value["amount"],
                mode="lines+markers",
                line=dict(color="#0072ce", width=3),
                marker=dict(color="#003c71", size=7),
                hovertemplate="FY%{x}<br>$%{y:,.0f}<extra></extra>",
                name="Approved amount",
            )
        )
        figure.update_layout(
            margin=dict(l=12, r=12, t=8, b=32),
            height=240,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", color="#0f172a"),
            xaxis=dict(title=None, automargin=True),
            yaxis=dict(title=None, tickprefix="$", separatethousands=True, gridcolor="#e2e6ed"),
            showlegend=False,
        )
        trend_ready_key.set(trend_key)
        return figure

    def trend_state() -> Any:
        if not _heavy_ready():
            return ui.div(
                ui.div(class_="city-spinner", aria_hidden="true"),
                "Preparing historical approved amounts...",
                class_="city-detail-trend__status city-detail-trend__status--loading",
                role="status",
                aria_live="polite",
            )
        value = historical_rows()
        if value.empty:
            return ui.div(
                "No historical approved amounts are available for this selection.",
                class_="city-detail-trend__status",
                role="status",
            )
        if trend_ready_key.get() != _content_key():
            return ui.div(
                ui.div(class_="city-spinner", aria_hidden="true"),
                "Updating historical approved amounts...",
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

    def title_text() -> str:
        state = selection()
        return next(
            (
                str(getattr(state, dimension))
                for dimension in reversed(_DIMENSIONS)
                if getattr(state, dimension)
            ),
            "Citywide budget detail",
        )

    def breadcrumb() -> str:
        return _breadcrumb(selection())

    def current_total() -> str:
        if not _summary_ready():
            return ""
        return format_currency(_change_values()[0], compact=True)

    def current_detail() -> str:
        if not _summary_ready():
            return ""
        state = selection()
        return f"FY{state.year}" if state.year is not None else "Current year"

    def compare_total() -> str:
        if not _summary_ready():
            return ""
        return format_currency(_change_values()[1], compact=True)

    def compare_detail() -> str:
        if not _summary_ready():
            return ""
        state = selection()
        return f"FY{state.compare_year}" if state.compare_year is not None else "Comparison year"

    def change_amount() -> str:
        if not _summary_ready():
            return ""
        return format_currency(_change_values()[2])

    def change_percent() -> str:
        if not _summary_ready():
            return ""
        percent = _change_values()[3]
        return format_percent(percent) if percent is not None else "Percentage unavailable"

    def change_explanation() -> str:
        return "Current less comparison" if _summary_ready() else ""

    def record_count() -> str:
        if not _summary_ready():
            return ""
        current_bundle = bundle()
        if current_bundle is not None:
            state = selection()
            return f"{current_bundle.record_count(year=state.year, flow={'revenue': 'Revenues', 'expense': 'Expenses'}.get(state.flow, 'all'), scope=state.fund_scope, department=state.department, fund=state.fund, category=state.category):,}"
        return f"{len(current_rows()):,}"

    def record_count_detail() -> str:
        return "Matching current-year rows" if _summary_ready() else ""

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
        await _expand("workspace")

    @reactive.effect
    @reactive.event(input.inspect)
    async def _inspect_records() -> None:
        await _expand("records")

    @reactive.effect
    @reactive.event(input.copy)
    async def _copy_state() -> None:
        await session.bookmark.do_bookmark()

    output(render.text(title_text), id="title_text")
    output(render.text(breadcrumb), id="breadcrumb")
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
