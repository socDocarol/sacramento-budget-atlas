from __future__ import annotations

import math

from budget_app.ui.components import format_currency, format_percent, stat_card
from budget_app.ui.modules.overview import format_overview_currency, overview_ui


def test_formatters_do_not_expose_nonfinite_values() -> None:
    for value in (math.nan, math.inf, -math.inf):
        assert format_currency(value) == "Not available"
        assert format_percent(value) == "Not available"


def test_overview_visible_amounts_use_full_dollars() -> None:
    """Catch compact million or billion values in rendered Overview cards."""

    markup = str(stat_card("Largest change", format_overview_currency(1_200_000)))

    assert "$1,200,000" in markup
    assert "$1.2M" not in markup


def test_overview_opening_uses_the_simplified_analytical_context() -> None:
    """Catch accidental restoration of removed filters or duplicate authority copy."""

    markup = str(overview_ui("overview"))

    for removed in (
        "Fiscal year",
        "Compare with",
        "Budget flow",
        "Active context",
        "Every figure represents approved budget authority",
    ):
        assert removed not in markup
    assert 'id="overview-fund_scope"' in markup
    assert 'id="overview-reset"' in markup
    assert 'aria-label="Reset to FY2027 expenses and all funds"' in markup
    assert 'title="Reset to FY2027 expenses and all funds"' in markup
    assert "FY2027 approved expenses benchmark" in markup
    assert markup.count("not actual spending") == 1
    assert 'id="overview-context_year"' in markup
    assert 'id="overview-kpis"' in markup
    assert 'id="overview-trend_chart"' in markup
    assert "Budget change by fiscal year" in markup
    assert "Largest movements" not in markup
    assert "No department movements" not in markup
