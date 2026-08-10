"""Session and bookmark state for the integrated Overview analysis.

Shiny performs URL encoding and restoration. These helpers keep outdated or
manually edited values from becoming application state after the source changes.
The analytical context is deliberately separate from the drawer and workspace
presentation flags. Budget calculations remain in the data domain layer.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any

VALID_VIEWS = frozenset({"overview", "budget101", "changed", "explorer", "methods", "lab"})
VALID_FLOWS = frozenset({"all", "revenue", "expense"})
VALID_PRESENTATION_LENSES = frozenset({"authority", "net_position", "source_records"})
VALID_SCOPES = frozenset(
    {
        "all",
        "all_funds",
        "general_fund",
        "measure_u",
        "enterprise_funds",
        "internal_service_funds",
        "other_governmental_or_restricted",
        "unknown",
    }
)


@dataclass(frozen=True, slots=True)
class OverviewSelectionState:
    """One session's synchronized analytical context."""

    year: int | None = None
    compare_year: int | None = None
    flow: str = "expense"
    fund_scope: str = "all_funds"
    department: str | None = None
    fund: str | None = None
    category: str | None = None
    selected_record: int | None = None

    def updated(self, **changes: Any) -> OverviewSelectionState:
        return replace(self, **changes)

    def as_bookmark_value(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OverviewPresentationState:
    """Bounded presentation flags serialized with the analytical bookmark state."""

    drawer_open: bool = False
    workspace_open: bool = False
    lens: str = "authority"

    def as_bookmark_value(self) -> dict[str, Any]:
        return asdict(self)


def _valid_or_default(value: Any, allowed: Collection[str], default: str) -> str:
    candidate = str(value) if value is not None else ""
    return candidate if candidate in allowed else default


def _optional_dimension(value: Any, allowed: Collection[str]) -> str | None:
    candidate = str(value or "").strip()
    if not candidate or candidate == "all":
        return None
    return candidate if candidate in allowed else None


def _optional_record(value: Any, allowed: Collection[int | str]) -> int | None:
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return None
    return candidate if candidate in {int(item) for item in allowed} else None


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    """Parse bookmark booleans without treating the string ``"false"`` as true."""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
        return default
    if isinstance(value, (int, float)):
        return value != 0
    return default


def sanitize_overview_presentation(
    value: Mapping[str, Any] | OverviewPresentationState | None,
) -> OverviewPresentationState:
    """Return bounded presentation state from a current or legacy bookmark."""

    raw: Mapping[str, Any] = (
        value.as_bookmark_value() if isinstance(value, OverviewPresentationState) else value or {}
    )
    return OverviewPresentationState(
        drawer_open=_coerce_bool(raw.get("drawer_open"), default=False),
        workspace_open=_coerce_bool(raw.get("workspace_open"), default=False),
        lens=_valid_or_default(raw.get("lens"), VALID_PRESENTATION_LENSES, "authority"),
    )


def compose_overview_bookmark_value(
    selection: OverviewSelectionState,
    presentation: OverviewPresentationState,
) -> dict[str, Any]:
    """Preserve legacy bookmark field names while storing runtime state separately."""

    return {
        **selection.as_bookmark_value(),
        **presentation.as_bookmark_value(),
    }


def sanitize_overview_selection(
    value: Mapping[str, Any] | OverviewSelectionState | None,
    *,
    years: Collection[int | str],
    departments: Collection[str] = (),
    funds: Collection[str] = (),
    categories: Collection[str] = (),
    records: Collection[int | str] = (),
) -> OverviewSelectionState:
    """Return a bounded Overview state against the current source dimensions."""

    raw: Mapping[str, Any] = (
        value.as_bookmark_value() if isinstance(value, OverviewSelectionState) else value or {}
    )

    available_years = sorted({int(item) for item in years}, reverse=True)
    default_year = 2027 if 2027 in available_years else (available_years[0] if available_years else None)

    def year_value(key: str, default: int | None) -> int | None:
        try:
            candidate = int(raw.get(key))
        except (TypeError, ValueError):
            return default
        return candidate if candidate in available_years else default

    selected_year = year_value("year", default_year)
    flow = _valid_or_default(raw.get("flow"), VALID_FLOWS, "expense")
    scope = str(raw.get("fund_scope") or "all_funds")
    if scope == "all":
        scope = "all_funds"

    return OverviewSelectionState(
        year=selected_year,
        compare_year=selected_year - 1 if selected_year is not None else None,
        flow="expense" if flow == "all" else flow,
        fund_scope=_valid_or_default(scope, VALID_SCOPES, "all_funds"),
        department=_optional_dimension(raw.get("department"), departments),
        fund=_optional_dimension(raw.get("fund"), funds),
        category=_optional_dimension(raw.get("category"), categories),
        selected_record=_optional_record(raw.get("selected_record"), records),
    )


def sanitize_restored_inputs(
    inputs: Mapping[str, Any],
    *,
    years: Collection[int | str],
    departments: Collection[str] = (),
    funds: Collection[str] = (),
    categories: Collection[str] = (),
) -> dict[str, Any]:
    """Return a bounded copy of bookmarked input values.

    Unknown input names are discarded. Filter values no longer present in the
    normalized snapshot are reset to their broadest valid choice. At most ten
    numeric scenario adjustments and ten corresponding departments are kept.
    """

    result: dict[str, Any] = {}
    allowed_years = {str(value) for value in years}
    allowed_dimensions = {
        "department": {str(value) for value in departments},
        "fund": {str(value) for value in funds},
        "category": {str(value) for value in categories},
    }

    for key, value in inputs.items():
        if key == "app_view":
            candidate = "overview" if str(value) == "drilldown" else value
            result[key] = _valid_or_default(candidate, VALID_VIEWS, "overview")
            continue

        suffix = key.rsplit("-", 1)[-1]
        if suffix in {"year", "compare", "current_year", "prior_year"}:
            aliases = {"latest", "prior", "all"}
            result[key] = _valid_or_default(value, allowed_years | aliases, "all")
        elif suffix == "flow":
            result[key] = _valid_or_default(value, VALID_FLOWS, "all")
        elif suffix == "fund_scope":
            result[key] = _valid_or_default(value, VALID_SCOPES, "all")
        elif suffix in allowed_dimensions:
            allowed = allowed_dimensions[suffix] | {"all"}
            result[key] = _valid_or_default(value, allowed, "all")
        elif key == "lab-balanced":
            result[key] = _coerce_bool(value, default=True)
        elif key.startswith("lab-adjustment_"):
            try:
                index = int(key.removeprefix("lab-adjustment_"))
                amount = float(value)
            except (TypeError, ValueError):
                continue
            if 1 <= index <= 10 and -1_000_000_000 <= amount <= 1_000_000_000:
                result[key] = amount
        elif key.startswith("lab-department_"):
            try:
                index = int(key.removeprefix("lab-department_"))
            except ValueError:
                continue
            candidate = str(value)
            if 1 <= index <= 10 and candidate in allowed_dimensions["department"]:
                result[key] = candidate

    return result
