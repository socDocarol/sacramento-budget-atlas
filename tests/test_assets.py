from hashlib import sha256
from pathlib import Path

from budget_app.application import (
    _DATA_FRAME_INPUT_SUFFIXES,
    _DATA_FRAME_OUTPUT_IDS,
    BOOKMARK_EXCLUDED_INPUTS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _digest(relative_path: str) -> str:
    return sha256((PROJECT_ROOT / relative_path).read_bytes()).hexdigest()


def test_city_assets_match_verified_reconstruction_bundle() -> None:
    assert _digest("www/assets/COStreatmentBLUE.png") == (
        "4dc476977e05d38d7894dcae2fcc6f5fdae323ffeb8b1b5254fef3319fd386f6"
    )
    assert _digest("www/assets/fonts/JosefinSans-latin-400-700.woff2") == (
        "444f5c461acc0dd1f5c4636c7e27c976a08ca62818717855bbe709b3ae04d086"
    )
    assert _digest("www/assets/fonts/Inter-latin-variable.woff2") == (
        "c940764593d0fe5d596be327ca7558855e018039fb78509aa21921fd3644c3e4"
    )


def test_bookmark_excludes_action_inputs_and_all_data_frame_state() -> None:
    excluded = set(BOOKMARK_EXCLUDED_INPUTS)
    action_inputs = {
        "share_state",
        "retry_source",
        "changed-reset",
        "explorer-reset",
        "explorer-copy_state",
        "overview-reset",
        "overview-year",
        "overview-compare",
        "overview-flow",
        "overview-fund_scope",
        "overview-workspace_department",
        "overview-workspace_fund",
        "overview-workspace_category",
        "detail-close",
        "detail-back",
        "detail-expand",
        "detail-copy",
    }

    assert action_inputs <= excluded
    for output_id in _DATA_FRAME_OUTPUT_IDS:
        for suffix in _DATA_FRAME_INPUT_SUFFIXES:
            assert f"{output_id}_{suffix}" in excluded
