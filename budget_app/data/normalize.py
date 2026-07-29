"""ArcGIS response parsing and strict normalization."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from .models import NORMALIZED_COLUMNS, Flow


class DataValidationError(ValueError):
    """Raised when the source violates the documented eight-field contract."""


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return " ".join(str(value).split())


def finite_number(value: Any, field: str, row_number: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DataValidationError(f"Approved Budgets row {row_number} has invalid {field}") from exc
    if not math.isfinite(number):
        raise DataValidationError(f"Approved Budgets row {row_number} has invalid {field}")
    return number


def normalize_flow(value: Any, row_number: int) -> Flow:
    normalized = clean_text(value).lower()
    if normalized in {"r", "revenue", "revenues"}:
        return "Revenues"
    if normalized in {"e", "expense", "expenses"}:
        return "Expenses"
    raise DataValidationError(
        f"Approved Budgets row {row_number} has unknown ExpenseRevenue value: {normalized or 'blank'}"
    )


def _attributes(feature: Mapping[str, Any]) -> Mapping[str, Any]:
    attributes = feature.get("attributes")
    if isinstance(attributes, Mapping):
        return attributes
    properties = feature.get("properties")
    if isinstance(properties, Mapping):
        return properties
    raise DataValidationError("Approved Budgets response row has no attributes")


def normalize_feature(feature: Mapping[str, Any], row_number: int = 1) -> dict[str, object]:
    """Convert one ArcGIS feature to the canonical eight fields.

    String cleanup and flow-code normalization happen only here, at the source
    boundary, so downstream transforms never need to guess at source variants.
    """

    attributes = _attributes(feature)
    object_id = attributes.get("ObjectId", attributes.get("OBJECTID", feature.get("id")))
    category = attributes.get("CATEGORY", attributes.get("Category"))
    return {
        "fiscal_year": int(finite_number(attributes.get("Fiscal_Year"), "Fiscal_Year", row_number)),
        "department": clean_text(attributes.get("Department")),
        "fund": clean_text(attributes.get("Fund")),
        "category": clean_text(category),
        "amount": finite_number(attributes.get("Amount"), "Amount", row_number),
        "expense_revenue": normalize_flow(attributes.get("ExpenseRevenue"), row_number),
        "fund_category": clean_text(attributes.get("Fund_Category")),
        "object_id": int(finite_number(object_id, "ObjectId", row_number)),
    }


def normalize_features(features: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    rows = [normalize_feature(feature, index) for index, feature in enumerate(features, start=1)]
    frame = pd.DataFrame.from_records(rows, columns=NORMALIZED_COLUMNS)
    if frame.empty:
        return pd.DataFrame(
            {
                "fiscal_year": pd.Series(dtype="int64"),
                "department": pd.Series(dtype="string"),
                "fund": pd.Series(dtype="string"),
                "category": pd.Series(dtype="string"),
                "amount": pd.Series(dtype="float64"),
                "expense_revenue": pd.Series(dtype="string"),
                "fund_category": pd.Series(dtype="string"),
                "object_id": pd.Series(dtype="int64"),
            },
            columns=NORMALIZED_COLUMNS,
        )
    frame["fiscal_year"] = frame["fiscal_year"].astype("int64")
    frame["object_id"] = frame["object_id"].astype("int64")
    frame["amount"] = frame["amount"].astype("float64")
    for column in ("department", "fund", "category", "expense_revenue", "fund_category"):
        frame[column] = frame[column].astype("string")
    return frame.loc[:, NORMALIZED_COLUMNS]


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize an already canonical dataframe when loading a parquet cache."""

    missing = set(NORMALIZED_COLUMNS).difference(frame.columns)
    if missing:
        raise DataValidationError(f"Cached snapshot is missing fields: {', '.join(sorted(missing))}")
    records = frame.loc[:, NORMALIZED_COLUMNS].to_dict(orient="records")
    features = [
        {
            "attributes": {
                "Fiscal_Year": row["fiscal_year"],
                "Department": row["department"],
                "Fund": row["fund"],
                "CATEGORY": row["category"],
                "Amount": row["amount"],
                "ExpenseRevenue": row["expense_revenue"],
                "Fund_Category": row["fund_category"],
                "ObjectId": row["object_id"],
            }
        }
        for row in records
    ]
    return normalize_features(features)
