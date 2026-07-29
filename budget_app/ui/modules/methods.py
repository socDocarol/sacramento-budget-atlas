"""Source, validation, reconciliation, and interpretation notes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd
from shiny import module, reactive, render, ui

from budget_app.data import BudgetSnapshot, PreparedBudgetBundle

from ..components import coerce_snapshot, empty_state, format_currency, stat_card, years
from ..shell import CITY_SOURCE_URL, page_intro, page_section

FIELDS = (
    ("Fiscal_Year", "Fiscal year", "Whole-number fiscal year used for every comparison."),
    ("Department", "Department", "City department or source-provided organizational label."),
    ("Fund", "Fund", "Accounting fund name retained from the source."),
    ("CATEGORY", "Category", "Source budget category within a fund and department."),
    ("Amount", "Approved amount", "Numeric approved budget authority in source dollars."),
    ("ExpenseRevenue", "Budget flow", "Normalized once to Revenues or Expenses."),
    ("Fund_Category", "Fund category", "Source category used with fund name for scope classification."),
    ("ObjectId", "ObjectId", "Exact ArcGIS record identifier used for traceability."),
)


@module.ui
def methods_ui(id: str = "methods") -> Any:
    return page_section(
        page_intro(
            "Sources & Methods",
            "Check freshness, coverage, validation, reconciliation, fields, and limitations "
            "before using an approved-budget chart in a conversation.",
            eyebrow_text="Traceable by design",
        ),
        ui.output_ui("source_state"),
        ui.output_ui("status_cards"),
        ui.div(
            ui.div(
                ui.div("Source contract", class_="city-eyebrow"),
                ui.h2("What enters the pilot", class_="city-section-title"),
                ui.tags.dl(
                    ui.tags.dt("Dataset"),
                    ui.tags.dd(
                        ui.a(
                            "City of Sacramento Approved Budgets",
                            href=CITY_SOURCE_URL,
                            target="_blank",
                            rel="noreferrer",
                        )
                    ),
                    ui.tags.dt("Request order"),
                    ui.tags.dd("ObjectId ascending, 1,000 records per page, with a 100-page safety cap."),
                    ui.tags.dt("Refresh"),
                    ui.tags.dd(
                        "A successful normalized snapshot is refreshed every 24 hours. "
                        "The last successful snapshot remains available during a source outage."
                    ),
                    ui.tags.dt("Storage"),
                    ui.tags.dd(
                        "One process-memory snapshot plus an atomic local Parquet cache and metadata file."
                    ),
                    class_="city-method-list",
                ),
                class_="city-surface city-surface--outlined city-guide-card",
            ),
            ui.div(
                ui.div("Coverage and validation", class_="city-eyebrow"),
                ui.h2("What is checked", class_="city-section-title"),
                ui.output_ui("checks"),
                class_="city-surface city-surface--panel city-guide-card",
            ),
            class_="city-grid city-grid--2",
        ),
        ui.div(
            ui.div("Reconciliation", class_="city-eyebrow"),
            ui.h2("How fund scopes are bounded", class_="city-section-title"),
            ui.output_ui("reconciliation"),
            class_="city-surface city-surface--outlined city-guide-card",
        ),
        ui.div(
            ui.div("Field dictionary", class_="city-eyebrow"),
            ui.h2("Exact fields used by the application", class_="city-section-title"),
            ui.div(
                ui.tags.table(
                    ui.tags.caption("Approved Budgets source fields and their use in this pilot."),
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Source field", scope="col"),
                            ui.tags.th("Application label", scope="col"),
                            ui.tags.th("Use", scope="col"),
                        )
                    ),
                    ui.tags.tbody(
                        *(
                            ui.tags.tr(
                                ui.tags.td(source),
                                ui.tags.td(label),
                                ui.tags.td(description),
                            )
                            for source, label, description in FIELDS
                        )
                    ),
                    class_="city-exact-table",
                ),
                class_="city-table-wrap",
            ),
            class_="city-surface city-surface--panel city-guide-card",
        ),
        ui.div(
            ui.div("Interpretation limits", class_="city-callout__label"),
            ui.p(
                "This pilot uses approved budget records only. It does not join actual "
                "spending, staffing, service outcomes, geography, or performance measures. "
                "It does not establish cause, waste, efficiency, or service impact. "
                "Technical completion still requires City data-owner approval before leadership use."
            ),
            class_="city-callout",
        ),
        section_id="methods",
        tone="alternate",
    )


@module.server
def methods_server(
    input: Any,
    output: Any,
    session: Any,
    snapshot: Any,
    navigation_callback: Callable[[Mapping[str, Any] | str], Any] | None = None,
) -> None:
    @reactive.calc
    def frame() -> pd.DataFrame:
        return coerce_snapshot(snapshot)

    def snapshot_value() -> BudgetSnapshot | None:
        value = snapshot() if callable(snapshot) else snapshot
        if isinstance(value, PreparedBudgetBundle):
            return value.snapshot
        return value if isinstance(value, BudgetSnapshot) else None

    def source_state() -> Any:
        value = frame()
        current = snapshot_value()
        if value.empty or current is None:
            return empty_state(
                "No normalized snapshot",
                "Source status will appear after the first successful refresh.",
            )
        stale = current.status == "stale"
        return ui.div(
            ui.span(
                "Stale snapshot" if stale else "Snapshot ready",
                class_="city-status-badge",
            ),
            ui.div(
                ui.h2(
                    "Last successful normalized snapshot",
                    class_="city-card-heading",
                ),
                ui.p(
                    f"{len(value):,} records across {len(years(value))} fiscal years. "
                    f"Repository fetch time: {current.metadata.fetched_at}."
                ),
            ),
            class_=("city-callout" if stale else "city-callout city-callout--exploratory"),
            role="status",
        )

    def status_cards() -> Any:
        value = frame()
        current = snapshot_value()
        if value.empty or current is None:
            return empty_state("Snapshot metadata is unavailable")
        metadata = current.metadata
        coverage = years(value)
        return ui.div(
            stat_card(
                "Freshness",
                "Stale" if current.stale else "Current",
                "24-hour refresh policy",
                tone="gold" if current.stale else "green",
            ),
            stat_card(
                "Coverage",
                f"{len(coverage)} years",
                (f"FY{coverage[-1]} to FY{coverage[0]}" if coverage else "No fiscal years"),
                tone="cobalt",
            ),
            stat_card(
                "Exact records",
                f"{metadata.row_count:,}",
                "Normalized source rows",
                tone="sky",
            ),
            stat_card(
                "Duplicate IDs",
                f"{metadata.duplicate_object_ids:,}",
                "Duplicate ObjectId check",
                tone="green" if metadata.duplicate_object_ids == 0 else "gold",
            ),
            class_="city-grid city-grid--4",
        )

    def checks() -> Any:
        current = snapshot_value()
        if current is None:
            return empty_state("Checks pending", "Validation runs after normalization.")
        metadata = current.metadata
        checks_with_status = (
            ("Duplicate ObjectIds", metadata.duplicate_object_ids),
            ("Blank departments", metadata.blank_departments),
            ("Blank funds", metadata.blank_funds),
            ("Blank categories", metadata.blank_categories),
            ("Unknown fund scopes retained", metadata.unknown_scopes),
        )
        return ui.tags.ul(
            *(
                ui.tags.li(
                    ui.span(
                        "Pass" if count == 0 else "Review",
                        class_="city-status-badge",
                    ),
                    ui.span(f"{label}: {count:,}"),
                )
                for label, count in checks_with_status
            ),
            ui.tags.li(
                ui.span("Pass", class_="city-status-badge"),
                ui.span("Whitespace and revenue or expense codes are normalized once."),
            ),
            ui.tags.li(
                ui.span("Pass", class_="city-status-badge"),
                ui.span("Unknown source scope values remain visible instead of being dropped."),
            ),
            class_="city-check-list",
        )

    def reconciliation() -> Any:
        current = snapshot_value()
        if current is None:
            return empty_state("Reconciliation metadata is unavailable")
        metadata = current.metadata
        return ui.div(
            ui.div(
                ui.span(
                    "Pass" if abs(metadata.expense_reconciliation_delta) < 0.005 else "Review",
                    class_="city-status-badge",
                ),
                ui.h3("Approved expenses", class_="city-card-heading"),
                ui.p(
                    "All-funds total less classified known scopes: "
                    f"{format_currency(metadata.expense_reconciliation_delta)}."
                ),
                class_="city-surface city-surface--panel city-guide-card",
            ),
            ui.div(
                ui.span(
                    "Pass" if abs(metadata.revenue_reconciliation_delta) < 0.005 else "Review",
                    class_="city-status-badge",
                ),
                ui.h3("Approved revenue", class_="city-card-heading"),
                ui.p(
                    "All-funds total less classified known scopes: "
                    f"{format_currency(metadata.revenue_reconciliation_delta)}."
                ),
                class_="city-surface city-surface--panel city-guide-card",
            ),
            class_="city-grid city-grid--2",
        )

    output(render.ui(source_state), id="source_state")
    output(render.ui(status_cards), id="status_cards")
    output(render.ui(checks), id="checks")
    output(render.ui(reconciliation), id="reconciliation")
