"""Small, framework-level UI primitives shared by the Shiny pages.

The application deliberately keeps these primitives free of Budget data access. They
accept plain values or Shiny tags, which makes them useful from both Core and Express
applications and keeps page modules easy to test in isolation.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import pandas as pd
from shiny import ui

from budget_app.data import add_scope_column
from budget_app.data.models import BudgetSnapshot, PreparedBudgetBundle


def page_container(*children: Any, width: str = "wide", class_: str = "") -> Any:
    return ui.div(
        *children,
        class_=f"city-container city-container--{width} {class_}".strip(),
    )


def eyebrow(text: str) -> Any:
    return ui.div(text, class_="city-eyebrow")


def section_header(title: str, description: str | None = None, *, eyebrow_text: str | None = None) -> Any:
    return ui.div(
        *([eyebrow(eyebrow_text)] if eyebrow_text else []),
        ui.h2(title, class_="city-section-title"),
        ui.p(description, class_="city-section-description") if description else None,
        class_="city-section-header",
    )


def surface(*children: Any, variant: str = "outlined", class_: str = "") -> Any:
    return ui.div(
        *children,
        class_=f"city-surface city-surface--{variant} {class_}".strip(),
    )


def stat_card(label: str, value: Any, detail: Any = None, *, tone: str = "sky", id: str | None = None) -> Any:
    attrs = {"class_": f"city-stat-card city-stat-card--{tone}"}
    if id:
        attrs["id"] = id
    return ui.div(
        ui.div(label, class_="city-stat-card__label"),
        ui.div(value, class_="city-stat-card__value tabular"),
        ui.div(detail, class_="city-stat-card__detail") if detail is not None else None,
        **attrs,
    )


def chart_frame(title: str, output: Any, summary_output: Any = None, *, source: str | None = None) -> Any:
    return surface(
        ui.div(title, class_="city-chart-title"),
        output,
        summary_output if summary_output is not None else None,
        ui.div(source, class_="city-chart-source") if source else None,
        variant="outlined",
        class_="city-chart-frame",
    )


def empty_state(
    title: str = "No data available", message: str = "Try changing the filters or refresh the source."
) -> Any:
    return ui.div(
        ui.div("○", aria_hidden="true", class_="city-state-icon"),
        ui.h3(title, class_="city-state-title"),
        ui.p(message, class_="city-state-message"),
        class_="city-state city-state--empty",
        role="status",
    )


def error_state(
    title: str = "Budget data is unavailable",
    message: str = "The last successful snapshot could not be loaded. Try again shortly.",
) -> Any:
    return ui.div(
        ui.div("!", aria_hidden="true", class_="city-state-icon"),
        ui.h3(title, class_="city-state-title"),
        ui.p(message, class_="city-state-message"),
        class_="city-state city-state--error",
        role="alert",
    )


def loading_state(label: str = "Loading Sacramento's budget…") -> Any:
    return ui.div(
        ui.div(class_="city-spinner", aria_hidden="true"),
        ui.span(label),
        class_="city-state city-state--loading",
        role="status",
        aria_live="polite",
    )


def value_or_dash(value: Any, *, empty: str = "Not available") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return empty
    if isinstance(value, str) and not value.strip():
        return empty
    return str(value)


def compact_chart_label(value: Any, *, limit: int = 26) -> str:
    """Shorten an axis label while leaving full text available to hover and tables."""

    text = value_or_dash(value, empty="Unspecified")
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 3)].rstrip()}..."


def format_currency(value: Any, *, compact: bool = False) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "Not available"
    if not math.isfinite(amount):
        return "Not available"
    sign = "−" if amount < 0 else ""
    amount = abs(amount)
    if compact:
        for suffix, divisor in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
            if amount >= divisor:
                return f"{sign}${amount / divisor:,.1f}{suffix}"
    return f"{sign}${amount:,.0f}"


def format_percent(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "Not available"
    return f"{amount:+.1f}%" if math.isfinite(amount) else "Not available"


def coerce_snapshot(snapshot: Any) -> pd.DataFrame:
    """Resolve a session snapshot into a defensive dataframe.

    Data services in the pilot may expose a dataframe directly, a reactive callable,
    or a small snapshot object with ``data``/``frame`` attributes. This adapter keeps
    UI modules independent of that repository detail.
    """
    try:
        value = snapshot() if callable(snapshot) else snapshot
    except Exception:
        return pd.DataFrame()
    for attr in ("data", "frame", "df"):
        if value is not None and hasattr(value, attr):
            value = getattr(value, attr)
            break
    if isinstance(value, PreparedBudgetBundle):
        # Prepared rows are immutable by process-level contract. Returning the
        # shared frame avoids a 29k-row defensive copy on every module calc.
        return value.rows
    if isinstance(value, BudgetSnapshot):
        # Legacy snapshots may not include the persisted scope column. Keep the
        # old defensive copy only for that compatibility path.
        if "fund_scope" in value.rows.columns:
            return value.rows
        return value.rows.copy()
    if isinstance(value, pd.DataFrame):
        return value if "fund_scope" in value.columns else value.copy()
    if isinstance(value, dict):
        for key in ("data", "rows", "records"):
            if key in value and isinstance(value[key], (list, tuple, pd.DataFrame)):
                value = value[key]
                break
    if isinstance(value, (list, tuple)):
        try:
            return pd.DataFrame(value)
        except (TypeError, ValueError):
            return pd.DataFrame()
    return pd.DataFrame()


def coerce_bundle(snapshot: Any) -> PreparedBudgetBundle | None:
    """Resolve a reactive snapshot value to the immutable prepared bundle."""

    try:
        value = snapshot() if callable(snapshot) else snapshot
    except Exception:
        return None
    return value if isinstance(value, PreparedBudgetBundle) else None


def ensure_scope_column(frame: pd.DataFrame) -> pd.DataFrame:
    """Return prepared scope rows without reclassifying or copying them."""

    if frame.empty or "fund_scope" in frame.columns:
        return frame
    return add_scope_column(frame)


def column(frame: pd.DataFrame, *names: str) -> str | None:
    lowered = {str(name).strip().lower().replace(" ", "_"): name for name in frame.columns}
    for name in names:
        key = name.strip().lower().replace(" ", "_")
        if key in lowered:
            return str(lowered[key])
    return None


def series(frame: pd.DataFrame, *names: str, default: Any = "") -> pd.Series:
    found = column(frame, *names)
    if found is None:
        return pd.Series([default] * len(frame), index=frame.index)
    return frame[found]


def unique_options(frame: pd.DataFrame, *names: str, limit: int = 300) -> list[str]:
    values = series(frame, *names).dropna().astype(str).str.strip()
    values = sorted({v for v in values if v})
    return values[:limit]


def years(frame: pd.DataFrame) -> list[str]:
    values = series(frame, "fiscal_year", "fiscal year", "year").dropna().astype(str).str.strip()
    return sorted({value for value in values if value}, key=_year_sort, reverse=True)


def _year_sort(value: str) -> tuple[int, str]:
    digits = "".join(ch for ch in value if ch.isdigit())
    return (int(digits) if digits else -1, value)


def as_records(frame: pd.DataFrame, limit: int = 10) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return frame.head(limit).to_dict(orient="records")


def options_or_default(options: Iterable[str], default: str = "All") -> dict[str, str]:
    values = list(options)
    return {default: default, **{value: value for value in values}}
