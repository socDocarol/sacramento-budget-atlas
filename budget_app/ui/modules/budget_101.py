"""Plain-language budget orientation with guided real-data examples."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd
from shiny import module, reactive, render, ui

from ..components import coerce_snapshot, empty_state, format_currency, surface
from ..shell import page_intro, page_section


@module.ui
def budget_101_ui(id: str = "budget101") -> Any:
    terms = (
        (
            "Revenue",
            "Money the City expects to receive, such as taxes, fees, grants, and other sources.",
        ),
        (
            "Expenses",
            "Approved plans for services, programs, contracts, personnel, and other costs.",
        ),
        (
            "Funds",
            "Separate accounting containers that can have legal, grant, or operational restrictions.",
        ),
        (
            "Approved budget",
            "A plan authorized for the fiscal year. It is not a report of actual spending.",
        ),
    )
    return page_section(
        page_intro(
            "Budget 101",
            "A short, practical guide to reading approved-budget data responsibly, "
            "with examples that open the same real records used throughout this pilot.",
            eyebrow_text="Start here",
        ),
        ui.div(
            *(
                surface(
                    ui.h2(title, class_="city-card-heading"),
                    ui.p(copy),
                    variant="panel",
                    class_="city-guide-card",
                )
                for title, copy in terms
            ),
            class_="city-grid city-grid--2",
        ),
        ui.div(
            ui.div("Interpretation guardrails", class_="city-callout__label"),
            ui.p(
                "A larger or smaller approved amount does not, by itself, describe "
                "service quality, waste, performance, cause, or actual spending. "
                "Use exact records and Sources & Methods before presenting a conclusion."
            ),
            class_="city-callout",
        ),
        ui.div(
            ui.div(
                ui.div("Guided examples", class_="city-eyebrow"),
                ui.h2("Try the hierarchy with real data", class_="city-section-title"),
                ui.p(
                    "Each example opens quick detail over this guide. Expand it when you "
                    "want the full department, fund, category, and exact-record workspace."
                ),
            ),
            ui.output_ui("examples"),
            class_="city-surface city-surface--outlined city-guide-card",
        ),
        ui.div(
            ui.h2("A practical reading path", class_="city-section-title"),
            ui.tags.ol(
                ui.tags.li("Set a fiscal year, comparison year, flow, and fund scope in Overview."),
                ui.tags.li("Choose a KPI, change, chart mark, or guided example."),
                ui.tags.li("Read current, comparison, dollar-change, and record-count context."),
                ui.tags.li("Expand analysis to move from department to fund to category."),
                ui.tags.li("Inspect exact ObjectIds before sharing an interpretation."),
                class_="city-reading-path",
            ),
            ui.div(
                ui.a(
                    "Open Overview",
                    href="#overview",
                    data_nav_value="overview",
                    data_nav_input="app_view",
                    class_="city-button city-button--secondary",
                ),
                ui.a(
                    "Inspect exact records",
                    href="#explorer",
                    data_nav_value="explorer",
                    data_nav_input="app_view",
                    class_="city-button city-button--secondary",
                ),
                ui.a(
                    "Review sources and methods",
                    href="#methods",
                    data_nav_value="methods",
                    data_nav_input="app_view",
                    class_="city-button city-button--secondary",
                ),
                class_="city-guided-links",
            ),
            class_="city-surface city-surface--panel city-reading-card",
        ),
        section_id="budget101",
    )


@module.server
def budget_101_server(
    input: Any,
    output: Any,
    session: Any,
    snapshot: Any = None,
    navigation_callback: Callable[[Mapping[str, Any] | str], Any] | None = None,
) -> None:
    @reactive.calc
    def frame() -> pd.DataFrame:
        return coerce_snapshot(snapshot)

    def examples() -> Any:
        value = frame()
        if value.empty:
            return empty_state(
                "Examples are loading",
                "Guided examples will appear after the approved budget snapshot is ready.",
            )
        latest = int(value["fiscal_year"].max())
        compare = int(
            value.loc[value["fiscal_year"].lt(latest), "fiscal_year"].max()
            if value["fiscal_year"].lt(latest).any()
            else latest
        )
        expenses = value.loc[value["fiscal_year"].eq(latest) & value["expense_revenue"].eq("Expenses")]
        top_department = str(
            expenses.groupby("department")["amount"].sum().sort_values(ascending=False).index[0]
        )
        top_amount = float(expenses.loc[expenses["department"].eq(top_department), "amount"].sum())

        def example_button(
            title: str,
            detail: str,
            *,
            flow: str,
            scope: str,
            department: str = "",
        ) -> Any:
            return ui.tags.button(
                ui.span(title, class_="city-card-heading"),
                ui.span(detail, class_="city-chart-summary"),
                type="button",
                class_="city-interactive-card city-surface city-surface--panel",
                data_overview_select="true",
                data_selection_year=str(latest),
                data_selection_flow=flow,
                data_selection_scope=scope,
                data_selection_department=department,
            )

        return ui.div(
            example_button(
                "Citywide revenue and expenses",
                f"FY{latest} compared with FY{compare}, all fund scopes.",
                flow="all",
                scope="all_funds",
            ),
            example_button(
                "General Fund expenses",
                f"Open the FY{latest} General Fund expense context.",
                flow="expense",
                scope="general_fund",
            ),
            example_button(
                top_department,
                f"Top FY{latest} expense department: {format_currency(top_amount)}.",
                flow="expense",
                scope="all_funds",
                department=top_department,
            ),
            class_="city-grid city-grid--3",
        )

    output(render.ui(examples), id="examples")
