"""Clearly labeled exploratory scenario and statistical review tools."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd
from shiny import module, reactive, render, ui

from budget_app.data import FUND_SCOPE_LABELS, robust_change_signals, validate_scenario

from ..components import coerce_snapshot, empty_state, format_currency, stat_card, years
from ..shell import page_intro, page_section


def _adjustment_row(index: int) -> Any:
    return ui.div(
        ui.div(
            ui.input_select(
                f"department_{index}",
                f"Department {index}",
                {"": "No department selected"},
            ),
            class_="city-control",
        ),
        ui.div(
            ui.input_numeric(
                f"adjustment_{index}",
                "Modeled change",
                0,
                min=-1_000_000_000,
                max=1_000_000_000,
                step=1000,
            ),
            class_="city-control",
        ),
        class_="city-adjustment-row",
    )


@module.ui
def lab_ui(id: str = "lab") -> Any:
    return page_section(
        page_intro(
            "Lab",
            "Try hypothetical allocation adjustments and inspect review signals. "
            "Nothing here changes or uploads the approved-budget source.",
            eyebrow_text="Exploratory only",
        ),
        ui.div(
            ui.span("Exploratory outputs", class_="city-status-badge"),
            ui.strong("Hypothetical scenarios and review signals are not approved-budget changes."),
            ui.p(
                "Fund restrictions may prevent a modeled transfer in practice. "
                "Signals do not establish waste, performance, cause, or service impact."
            ),
            class_="city-lab-banner",
            role="note",
        ),
        ui.div(
            ui.div(
                ui.input_select("year", "Scenario fiscal year", {"latest": "Latest fiscal year"}),
                class_="city-control",
            ),
            ui.div(
                ui.input_select("fund_scope", "Fund scope", {"all_funds": "All funds total"}),
                class_="city-control",
            ),
            ui.div(
                ui.input_checkbox("balanced", "Require adjustments to net to zero", True),
                class_="city-control city-checkbox",
            ),
            class_="city-controls",
            aria_label="Lab context",
        ),
        ui.div(
            ui.div("Scenario inputs", class_="city-eyebrow"),
            ui.h2("Allocation sandbox", class_="city-section-title"),
            ui.p(
                "Positive values add to a department and negative values reduce it. "
                "The source snapshot remains unchanged."
            ),
            ui.div(_adjustment_row(1), _adjustment_row(2), class_="city-lab-adjustments"),
            ui.tags.details(
                ui.tags.summary("Add up to eight more department adjustments"),
                ui.div(
                    *(_adjustment_row(index) for index in range(3, 11)),
                    class_="city-lab-adjustments",
                ),
                class_="city-progressive",
            ),
            class_="city-surface city-surface--outlined city-guide-card",
        ),
        ui.div(
            ui.div(
                ui.div("Validation and warnings", class_="city-eyebrow"),
                ui.h2("Scenario status", class_="city-section-title"),
                ui.output_ui("scenario_state"),
                class_="city-surface city-surface--panel city-guide-card",
            ),
            ui.div(
                ui.div("Hypothetical result", class_="city-eyebrow"),
                ui.h2("Adjusted department totals", class_="city-section-title"),
                ui.div(ui.output_data_frame("scenario_table"), class_="city-table-wrap"),
                class_="city-surface city-surface--outlined city-guide-card",
            ),
            class_="city-grid city-grid--2",
        ),
        ui.div(
            ui.div("Statistical review", class_="city-eyebrow"),
            ui.h2("Robust change and direction signals", class_="city-section-title"),
            ui.p(
                "Scores appear only when at least six historical changes exist and "
                "historical deviation is nonzero. Open one entity for raw history, "
                "formula, suppression, and warning detail."
            ),
            ui.output_ui("signal_metrics"),
            ui.output_ui("signals"),
            class_="city-surface city-surface--panel city-guide-card",
        ),
        section_id="lab",
        tone="alternate",
    )


@module.server
def lab_server(
    input: Any,
    output: Any,
    session: Any,
    snapshot: Any,
    navigation_callback: Callable[[Mapping[str, Any] | str], Any] | None = None,
) -> None:
    @reactive.calc
    def frame() -> pd.DataFrame:
        return coerce_snapshot(snapshot)

    @reactive.effect
    def _update_choices() -> None:
        value = frame()
        available = years(value)
        if available:
            with reactive.isolate():
                current_year = str(input.year() or "")
            ui.update_select(
                "year",
                choices={item: item for item in available},
                selected=current_year if current_year in available else available[0],
            )
        with reactive.isolate():
            current_scope = str(input.fund_scope() or "")
        ui.update_select(
            "fund_scope",
            choices=FUND_SCOPE_LABELS,
            selected=current_scope if current_scope in FUND_SCOPE_LABELS else "general_fund",
        )
        departments = sorted(value["department"].dropna().astype(str).unique()) if not value.empty else []
        for index in range(1, 11):
            with reactive.isolate():
                current = str(input[f"department_{index}"]() or "")
            ui.update_select(
                f"department_{index}",
                choices={"": "No department selected", **{item: item for item in departments}},
                selected=current if current in departments else "",
            )

    def selected_year() -> int:
        available = [int(value) for value in years(frame())]
        try:
            candidate = int(input.year())
        except (TypeError, ValueError):
            candidate = available[0] if available else 0
        return candidate if candidate in available else (available[0] if available else 0)

    def selected_scope() -> str:
        value = str(input.fund_scope() or "")
        return value if value in FUND_SCOPE_LABELS else "general_fund"

    def adjustments() -> list[tuple[str, float]]:
        values: list[tuple[str, float]] = []
        for index in range(1, 11):
            department = str(input[f"department_{index}"]() or "").strip()
            if not department:
                continue
            try:
                amount = float(input[f"adjustment_{index}"]() or 0)
            except (TypeError, ValueError):
                amount = float("nan")
            values.append((department, amount))
        return values

    @reactive.calc
    def scenario_result() -> Any:
        entries = adjustments()
        departments = [department for department, _amount in entries]
        result = validate_scenario(
            frame(),
            year=selected_year(),
            scope=selected_scope(),
            adjustments=entries,
            balanced=bool(input.balanced()),
        )
        if len(set(departments)) != len(departments):
            result = type(result)(
                valid=False,
                balanced=result.balanced,
                total_delta=result.total_delta,
                errors=(*result.errors, "Each adjusted department may appear only once"),
                adjusted=result.adjusted,
            )
        return result

    def scenario_state() -> Any:
        if frame().empty:
            return empty_state(
                "No approved expense rows",
                "Choose a fiscal year and fund scope with expense records.",
            )
        if not adjustments():
            return ui.div(
                ui.span("No scenario yet", class_="city-status-badge"),
                ui.p("Select one or more departments to model a hypothetical allocation change."),
                class_="city-callout city-callout--exploratory",
            )
        result = scenario_result()
        if not result.valid:
            return ui.div(
                ui.span("Needs attention", class_="city-status-badge"),
                ui.tags.ul(*(ui.tags.li(error) for error in result.errors)),
                ui.p(f"Modeled net change: {format_currency(result.total_delta)}."),
                class_="city-callout",
                role="alert",
            )
        return ui.div(
            ui.span("Valid hypothetical input", class_="city-status-badge"),
            ui.p(
                f"Modeled net change: {format_currency(result.total_delta)}. "
                "The approved-budget source is unchanged."
            ),
            class_="city-callout city-callout--exploratory",
        )

    def scenario_table() -> Any:
        result = scenario_result()
        if result.adjusted is None or result.adjusted.empty:
            return render.DataGrid(
                pd.DataFrame({"Status": ["Select a department and enter a modeled adjustment."]}),
                selection_mode="none",
            )
        value = result.adjusted.rename(
            columns={
                "department": "Department",
                "base": "Approved expenses",
                "delta": "Modeled change",
                "adjusted": "Modeled total",
            }
        )
        for name in ("Approved expenses", "Modeled change", "Modeled total"):
            value[name] = value[name].map(format_currency)
        return render.DataGrid(value, height="320px", selection_mode="none")

    @reactive.calc
    def signal_data() -> pd.DataFrame:
        value = frame()
        if value.empty:
            return pd.DataFrame()
        return robust_change_signals(
            value,
            flow="Expenses",
            scope=selected_scope(),
            latest_year=selected_year(),
        )

    def signal_metrics() -> Any:
        result = signal_data()
        if result.empty:
            return empty_state("No signal history is available")
        flagged = int(result["reason"].astype(str).ne("").sum())
        scored = int(result["modified_z"].notna().sum())
        suppressed = len(result) - scored
        return ui.div(
            stat_card(
                "Entities reviewed",
                f"{len(result):,}",
                "Departments with annual history",
                tone="cobalt",
            ),
            stat_card(
                "Review signals",
                f"{flagged:,}",
                "Entities with at least one transparent rule",
                tone="gold" if flagged else "green",
            ),
            stat_card(
                "Robust scores",
                f"{scored:,}",
                "Entities with sufficient nonzero history",
                tone="sky",
            ),
            stat_card(
                "Suppressed scores",
                f"{suppressed:,}",
                "Insufficient history or zero deviation",
                tone="cobalt",
            ),
            class_="city-grid city-grid--4",
        )

    def signals() -> Any:
        result = signal_data()
        if result.empty:
            return empty_state(
                "Signals are unavailable",
                "The source needs fiscal year, department, and amount fields.",
            )
        flagged = result.loc[result["reason"].astype(str).ne("")]
        review = (flagged if not flagged.empty else result).head(12)
        cards = []
        for row in review.itertuples(index=False):
            series_text = ", ".join(
                f"FY{year}: {format_currency(amount)}" for year, amount in row.annual_series
            )
            score_text = (
                f"{row.modified_z:.2f}"
                if pd.notna(row.modified_z)
                else f"Suppressed: {row.suppression_reason.replace('_', ' ')}"
            )
            reason = row.reason.replace("_", " ") if row.reason else "No review flag"
            cards.append(
                ui.tags.details(
                    ui.tags.summary(
                        ui.span(
                            "Review" if row.reason else "No flag",
                            class_="city-status-badge",
                        ),
                        ui.span(f"{row.entity}: {format_currency(row.change)} latest change"),
                    ),
                    ui.div(
                        ui.p(
                            f"Current: {format_currency(row.current)}. Prior: {format_currency(row.prior)}."
                        ),
                        ui.p(f"Modified score: {score_text}. Reason: {reason}."),
                        ui.p(f"Formula: {row.formula}"),
                        ui.p(f"Raw annual series: {series_text}"),
                        ui.p(
                            "This is a review signal only. It is not evidence of cause, "
                            "performance, waste, or service impact."
                        ),
                        class_="city-signal-card__body",
                    ),
                    class_="city-signal-card",
                )
            )
        return ui.div(*cards, class_="city-signal-stack")

    output(render.ui(scenario_state), id="scenario_state")
    output(render.data_frame(scenario_table), id="scenario_table")
    output(render.ui(signal_metrics), id="signal_metrics")
    output(render.ui(signals), id="signals")
