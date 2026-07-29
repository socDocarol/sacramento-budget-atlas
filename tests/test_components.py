from __future__ import annotations

import math

from budget_app.ui.components import format_currency, format_percent


def test_formatters_do_not_expose_nonfinite_values() -> None:
    for value in (math.nan, math.inf, -math.inf):
        assert format_currency(value) == "Not available"
        assert format_percent(value) == "Not available"
