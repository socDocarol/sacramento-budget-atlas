from __future__ import annotations

import pytest

from budget_app.config import Settings
from budget_app.data import NORMALIZED_COLUMNS, ArcGISBudgetRepository


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_arcgis_contract() -> None:
    snapshot = await ArcGISBudgetRepository(Settings.from_env()).load_snapshot(force=True)

    assert tuple(snapshot.rows.columns) == (*NORMALIZED_COLUMNS, "fund_scope")
    assert snapshot.years
    assert snapshot.latest_year == max(snapshot.years)
    assert snapshot.rows["object_id"].is_unique
    assert snapshot.rows["object_id"].is_monotonic_increasing
    assert snapshot.metadata.duplicate_object_ids == 0
    assert snapshot.metadata.expense_reconciliation_delta == pytest.approx(0)
    assert snapshot.metadata.revenue_reconciliation_delta == pytest.approx(0)
