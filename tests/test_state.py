from __future__ import annotations

import pytest

from budget_app.state import (
    VALID_VIEWS,
    compose_overview_bookmark_value,
    sanitize_overview_presentation,
    sanitize_overview_selection,
    sanitize_restored_inputs,
)


def test_public_views_keep_legacy_drilldown_out_of_navigation() -> None:
    assert "drilldown" not in VALID_VIEWS

    restored = sanitize_restored_inputs(
        {"app_view": "drilldown"},
        years=(2026, 2027),
    )

    assert restored == {"app_view": "overview"}


def test_legacy_drawer_flags_are_separated_from_context_and_composed_for_bookmarks() -> None:
    legacy_bookmark = {
        "year": 2027,
        "compare_year": 2026,
        "flow": "expense",
        "fund_scope": "all_funds",
        "department": "Police",
        "fund": "General Fund",
        "category": "Employee Services",
        "drawer_open": False,
        "workspace_open": True,
    }
    selection = sanitize_overview_selection(
        legacy_bookmark,
        years=(2026, 2027),
        departments=("Police",),
        funds=("General Fund",),
        categories=("Employee Services",),
    )
    presentation = sanitize_overview_presentation(legacy_bookmark)

    assert selection.department == "Police"
    assert selection.fund == "General Fund"
    assert selection.category == "Employee Services"
    assert selection.as_bookmark_value() == {
        "year": 2027,
        "compare_year": 2026,
        "flow": "expense",
        "fund_scope": "all_funds",
        "department": "Police",
        "fund": "General Fund",
        "category": "Employee Services",
        "selected_record": None,
    }
    assert presentation.drawer_open is False
    assert presentation.workspace_open is True
    assert presentation.lens == "authority"
    assert compose_overview_bookmark_value(selection, presentation) == {
        **selection.as_bookmark_value(),
        "drawer_open": False,
        "workspace_open": True,
        "lens": "authority",
    }


def test_url_restoration_sanitizes_outdated_and_unbounded_values() -> None:
    restored = {
        "app_view": "unknown",
        "overview-year": "2027",
        "overview-flow": "garbage",
        "explorer-department": "Police",
        "explorer-fund": "Retired Fund",
        "lab-adjustment_1": 2500,
        "lab-adjustment_11": 5,
        "lab-adjustment_2": "not a number",
        "lab-department_1": "Parks",
        "lab-department_2": "Old Department",
        "unrelated-secret": "drop me",
    }

    result = sanitize_restored_inputs(
        restored,
        years=(2026, 2027),
        departments=("Police", "Parks"),
        funds=("General Fund",),
    )

    assert result == {
        "app_view": "overview",
        "overview-year": "2027",
        "overview-flow": "all",
        "explorer-department": "Police",
        "explorer-fund": "all",
        "lab-adjustment_1": 2500.0,
        "lab-department_1": "Parks",
    }


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [("false", False), ("true", True), (False, False), (True, True)],
)
def test_bookmark_boolean_values_are_coerced_without_truthy_strings(
    raw_value: object, expected: bool
) -> None:
    selection = sanitize_overview_selection(
        {"drawer_open": raw_value, "workspace_open": raw_value},
        years=(2026,),
    )
    presentation = sanitize_overview_presentation({"drawer_open": raw_value, "workspace_open": raw_value})
    restored = sanitize_restored_inputs({"lab-balanced": raw_value}, years=(2026,))

    assert "drawer_open" not in selection.as_bookmark_value()
    assert "workspace_open" not in selection.as_bookmark_value()
    assert presentation.drawer_open is expected
    assert presentation.workspace_open is expected
    assert presentation.lens == "authority"
    assert compose_overview_bookmark_value(selection, presentation)["drawer_open"] is expected
    assert compose_overview_bookmark_value(selection, presentation)["workspace_open"] is expected
    assert compose_overview_bookmark_value(selection, presentation)["lens"] == "authority"
    assert restored == {"lab-balanced": expected}


@pytest.mark.parametrize(
    ("raw_lens", "expected"),
    [("net_position", "net_position"), ("source_records", "source_records"), ("unknown", "authority"), (None, "authority")],
)
def test_presentation_lens_is_bounded_and_legacy_bookmarks_default_to_authority(
    raw_lens: object, expected: str
) -> None:
    presentation = sanitize_overview_presentation({"lens": raw_lens})

    assert presentation.lens == expected
