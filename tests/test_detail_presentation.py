from __future__ import annotations

from budget_app.state import OverviewSelectionState
from budget_app.ui.modules.detail_drawer import detail_presentation


def test_authority_presentation_names_flow_year_and_hierarchy_path() -> None:
    presentation = detail_presentation(
        OverviewSelectionState(
            year=2027,
            compare_year=2026,
            flow="expense",
            fund_scope="general_fund",
            department="Police",
            fund="General Fund",
            category="Employee Services",
            selected_record=12345,
        )
    )

    assert presentation.eyebrow == "EXACT RECORD | APPROVED EXPENSES"
    assert presentation.title == "ObjectId 12345"
    assert presentation.context_prefix == "FY2027 | Approved expenses | General Fund"
    assert presentation.breadcrumb == "Citywide / Police / General Fund / Employee Services / ObjectId 12345"
    assert presentation.current_label == "Current approved expenses"
    assert presentation.trend_title == "Historical approved expenses"
    assert presentation.expand_target == "workspace"


def test_net_position_presentation_uses_net_labels_and_record_support() -> None:
    presentation = detail_presentation(OverviewSelectionState(year=2027, compare_year=2026), "net_position")

    assert presentation.eyebrow == "NET POSITION"
    assert presentation.title == "Citywide net position"
    assert presentation.context_prefix == "FY2027 | Net position | All funds total"
    assert presentation.current_label == "Current net position"
    assert presentation.trend_title == "Annual net position"
    assert presentation.exact_section_title == "Supporting records for net position"
    assert presentation.expand_target == "records"


def test_source_records_presentation_leads_with_matching_rows() -> None:
    presentation = detail_presentation(OverviewSelectionState(year=2027), "source_records")

    assert presentation.eyebrow == "SOURCE RECORDS"
    assert presentation.title == "FY2027 approved-budget source records"
    assert presentation.context_prefix == "FY2027 | Matching source records | All funds total"
    assert presentation.current_label == "Matching current-year rows"
    assert presentation.record_label == "Revenue rows"
    assert presentation.trend_value_label == "Matching records"
    assert presentation.exact_section_title == "Matching source records"
