"""Shiny Core application assembly and cross-module state flow."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from collections.abc import Mapping
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shiny.testmode import export_test_values, snapshot_preprocess_input
from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from budget_app.access import NetworkAccessContextProvider
from budget_app.config import Settings, configure_logging
from budget_app.data import (
    ArcGISBudgetRepository,
    PreparedBudgetBundle,
    RefreshStatus,
    SnapshotStore,
)
from budget_app.state import (
    VALID_VIEWS,
    OverviewPresentationState,
    OverviewSelectionState,
    compose_overview_bookmark_value,
    sanitize_overview_presentation,
    sanitize_overview_selection,
    sanitize_restored_inputs,
)
from budget_app.ui.modules import (
    budget_101_server,
    budget_101_ui,
    detail_drawer_server,
    detail_drawer_ui,
    explorer_server,
    explorer_ui,
    lab_server,
    lab_ui,
    methods_server,
    methods_ui,
    overview_server,
    overview_ui,
    what_changed_server,
    what_changed_ui,
)
from budget_app.ui.shell import city_footer_ui, city_header_ui

SETTINGS = Settings.from_env()
configure_logging(SETTINGS.log_level)
LOG = logging.getLogger("budget_app")
REPOSITORY = ArcGISBudgetRepository(SETTINGS)
SNAPSHOT_STORE = SnapshotStore(SETTINGS, repository=REPOSITORY)
ACCESS_PROVIDER = NetworkAccessContextProvider()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACIFIC = ZoneInfo("America/Los_Angeles")
_PROCESS_REFRESH_TASK: asyncio.Task[Any] | None = None
_STATUS_SUBSCRIBERS: set[Any] = set()
_LAST_MANUAL_REFRESH_AT = 0.0
MANUAL_REFRESH_ENABLED = SETTINGS.manual_refresh_enabled or os.getenv("SHINY_TESTMODE") == "1"


class SecurityHeadersMiddleware:
    """Apply a conservative same-origin browser policy to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("x-content-type-options", "nosniff")
                headers.setdefault("referrer-policy", "no-referrer")
                headers.setdefault("x-robots-tag", "noindex, nofollow")
                headers.setdefault("permissions-policy", "camera=(), microphone=(), geolocation=()")
                headers.setdefault("strict-transport-security", "max-age=31536000; includeSubDomains")
                headers.setdefault(
                    "content-security-policy",
                    "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
                    "form-action 'self'; img-src 'self' data: blob:; "
                    "font-src 'self' data: https://unpkg.com; "
                    "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; "
                    "connect-src 'self' ws: wss:; worker-src 'self' blob:",
                )
                if str(scope.get("path", "")).startswith("/health/"):
                    headers["cache-control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _format_pacific_timestamp(value: str | None) -> str:
    """Format the successful source timestamp for the persistent status shell."""

    if not value:
        return ""
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(PACIFIC)
    except (TypeError, ValueError):
        return ""
    date_part = timestamp.strftime("%B %d, %Y").replace(" 0", " ")
    return f"{date_part} at {timestamp.strftime('%I:%M %p')} PT"


def _format_pacific_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(PACIFIC)
    except (TypeError, ValueError):
        return ""
    return timestamp.strftime("%B %d, %Y").replace(" 0", " ")


def _store_status() -> RefreshStatus:
    return SNAPSHOT_STORE.status


def _broadcast_status() -> None:
    status = _store_status()
    for callback in tuple(_STATUS_SUBSCRIBERS):
        try:
            callback(status)
        except Exception:  # noqa: BLE001
            LOG.exception("refresh status subscriber failed")


async def _process_refresh_schedule() -> None:
    """Run one process-wide refresh and then repeat on the configured TTL."""

    consecutive_failures = 0
    while True:
        await _run_refresh_background(force=True)
        if _store_status().state == "error":
            consecutive_failures += 1
            base_delay = min(3600, 60 * (2 ** min(consecutive_failures - 1, 6)))
            delay = min(SETTINGS.cache_ttl_seconds, base_delay) * random.uniform(0.8, 1.2)
        else:
            consecutive_failures = 0
            delay = SETTINGS.cache_ttl_seconds
        await asyncio.sleep(max(1, delay))


def _ensure_process_refresh() -> asyncio.Task[Any]:
    global _PROCESS_REFRESH_TASK
    if os.getenv("BUDGET_BACKGROUND_REFRESH_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return asyncio.create_task(asyncio.sleep(0))
    if _PROCESS_REFRESH_TASK is None or _PROCESS_REFRESH_TASK.done():
        _PROCESS_REFRESH_TASK = asyncio.create_task(_process_refresh_schedule())
    return _PROCESS_REFRESH_TASK


def _start_coordinated_refresh(*, force: bool) -> asyncio.Task[Any]:
    """Start or join the process-wide single-flight refresh without awaiting it."""

    return asyncio.create_task(_run_refresh_background(force=force))


async def _run_refresh_background(*, force: bool) -> None:
    task = SNAPSHOT_STORE.start_background_refresh(force=force)
    # Let the coordinator enter _refresh_once so its running status is visible
    # before the first status payload is sent to sessions.
    await asyncio.sleep(0)
    _broadcast_status()
    try:
        await task
    except Exception:  # noqa: BLE001
        LOG.exception("process-wide budget refresh failed")
    finally:
        _broadcast_status()


def _status_payload(
    *,
    bundle: PreparedBudgetBundle | None,
    status: RefreshStatus,
    source_error: str | None = None,
) -> dict[str, Any]:
    """Build truthful status text while keeping the last good timestamp visible."""

    timestamp = _format_pacific_timestamp(bundle.data_updated_at if bundle else None)
    running = status.state == "running"
    failed = status.state == "error" or bool(source_error)
    if bundle is None:
        if running:
            message = "Loading the approved budget snapshot"
            detail = ""
            status_class = "loading"
            icon = ""
        else:
            message = "Unable to load the approved budget snapshot"
            detail = "No valid snapshot is cached. Retry the source or contact the data team."
            status_class = "error"
            icon = "!"
    elif running:
        message = "Updating data in the background"
        detail = "Showing data last updated"
        status_class = "warning"
        icon = ""
    elif failed or bundle.snapshot.stale:
        message = "Unable to check for updates"
        detail = "Showing data last updated"
        status_class = "warning"
        icon = "!"
    elif status.state == "success":
        message = "Data updated"
        detail = ""
        status_class = "fresh"
        icon = "✓"
    else:
        message = "Data last updated"
        detail = ""
        status_class = "fresh"
        icon = "✓"
    if timestamp:
        if message == "Data last updated":
            message = f"Data last updated {timestamp}"
            timestamp = ""
        elif message == "Data updated":
            message = f"Data updated {timestamp}"
            timestamp = ""
        elif running:
            detail = f"Showing data last updated {timestamp}"
            timestamp = ""
        elif failed:
            detail = f"Showing data last updated {timestamp}. Serving the last successful snapshot."
            timestamp = ""
        else:
            timestamp = f"{timestamp}"
    return {
        "state": status.state if status.state != "idle" else ("loading" if bundle is None else "fresh"),
        "status_class": status_class,
        "message": message,
        "detail": detail,
        "timestamp": timestamp,
        "icon": icon,
        "aria_busy": running or bundle is None,
        "button_disabled": running or not MANUAL_REFRESH_ENABLED,
        "button_label": (
            "Refresh managed automatically"
            if not MANUAL_REFRESH_ENABLED
            else ("Retry source" if failed or (bundle is None and not running) else "Refresh source")
        ),
    }


_DATA_FRAME_INPUT_SUFFIXES = (
    "cell_selection",
    "sort",
    "column_sort",
    "filter",
    "column_filter",
    "data_view_rows",
    "data_view_indices",
    "selected_rows",
)
_DATA_FRAME_OUTPUT_IDS = (
    "overview-workspace_table",
    "changed-table",
    "explorer-table",
    "lab-scenario_table",
)
BOOKMARK_EXCLUDED_INPUTS = (
    "share_state",
    "retry_source",
    "changed-reset",
    "explorer-reset",
    "explorer-copy_state",
    "overview-year",
    "overview-compare",
    "overview-flow",
    "overview-fund_scope",
    "overview-workspace_department",
    "overview-workspace_fund",
    "overview-workspace_category",
    "overview-selection_request",
    "detail_reopen_request",
    "overview-legacy_drilldown",
    "overview-reset",
    "overview-workspace_back",
    "overview-workspace_clear",
    "overview-workspace_collapse",
    "detail-backdrop",
    "detail-back",
    "detail-close",
    "detail-close_footer",
    "detail-expand",
    "detail-inspect",
    "detail-copy",
    "detail-clear",
    "shinywidgets_comm_send",
    *(
        f"{output_id}_{suffix}"
        for output_id in _DATA_FRAME_OUTPUT_IDS
        for suffix in _DATA_FRAME_INPUT_SUFFIXES
    ),
)
LOG.info(
    "application configured",
    extra={
        "cache_dir": str(SETTINGS.cache_dir),
        "cache_ttl_seconds": SETTINGS.cache_ttl_seconds,
        "base_path": SETTINGS.app_base_path,
    },
)


def _application_ui(_request: Any) -> Any:
    """Return callable UI, as required by Shiny URL bookmarking."""

    return ui.page_bootstrap(
        ui.tags.meta(name="robots", content="noindex, nofollow"),
        ui.tags.meta(name="viewport", content="width=device-width, initial-scale=1"),
        ui.tags.link(rel="icon", href="assets/COStreatmentBLUE.png"),
        ui.tags.link(rel="stylesheet", href="city.css?v=20260811-overview-density"),
        ui.tags.script(src="app.js?v=20260811-overview-density", defer=True),
        ui.div(
            city_header_ui(nav_input_id="app_view", app_home=SETTINGS.app_base_path),
            ui.tags.main(
                ui.div(
                    ui.div(
                        ui.span(
                            "",
                            class_="city-status__icon city-status__dot city-status__icon--loading",
                            aria_hidden="true",
                            data_source_status_icon="true",
                        ),
                        ui.div(
                            ui.span(
                                "Loading the approved budget snapshot",
                                class_="city-source-status__message",
                                data_source_status_message="true",
                            ),
                            ui.span(
                                "",
                                class_="city-source-status__detail",
                                data_source_status_detail="true",
                            ),
                            ui.span(
                                "",
                                class_="city-source-status__timestamp",
                                data_source_status_timestamp="true",
                            ),
                            class_="city-source-status__text",
                        ),
                        id="source_status_shell",
                        class_="city-source-status city-source-status--loading",
                        role="status",
                        aria_live="polite",
                        aria_busy="true",
                        data_source_state="loading",
                    ),
                    ui.div(
                        ui.input_action_button(
                            "share_state",
                            "Copy shareable view",
                            class_="city-button city-button--secondary",
                        ),
                        ui.input_action_button(
                            "retry_source",
                            "Refresh source",
                            class_="city-button city-button--quiet",
                            disabled=True,
                        ),
                        ui.span(
                            "The URL contains view settings only. No user information is stored.",
                            class_="city-share-note",
                        ),
                        ui.span("", class_="sr-only", aria_live="polite", data_copy_status="true"),
                        class_="city-utility-actions",
                    ),
                    class_="city-container city-container--wide city-app-toolbar",
                ),
                ui.navset_hidden(
                    ui.nav_panel(
                        "Overview",
                        overview_ui("overview"),
                        value="overview",
                    ),
                    ui.nav_panel("What Changed", what_changed_ui("changed"), value="changed"),
                    ui.nav_panel("Explorer", explorer_ui("explorer"), value="explorer"),
                    ui.nav_panel("Lab", lab_ui("lab"), value="lab"),
                    ui.nav_panel("Budget 101", budget_101_ui("budget101"), value="budget101"),
                    ui.nav_panel("Sources & Methods", methods_ui("methods"), value="methods"),
                    id="app_view",
                    selected="overview",
                ),
                detail_drawer_ui("detail"),
                id="main",
                tabindex="-1",
            ),
            city_footer_ui(source_url=SETTINGS.arcgis_url),
            class_="city-app",
        ),
        title="Sacramento Approved Budget",
        lang="en",
    )


def _server(input: Inputs, output: Outputs, session: Session) -> None:
    active_bundle = SNAPSHOT_STORE.active_bundle
    snapshot = reactive.Value[PreparedBudgetBundle | None](active_bundle)
    source_error = reactive.Value[str | None](None)
    source_loading = reactive.Value(active_bundle is None)
    refresh_state = reactive.Value[dict[str, Any]](
        {
            "status": "fresh" if active_bundle is not None else "loading",
            "cache_source": "disk-fresh" if active_bundle is not None else None,
            "row_count": active_bundle.metadata.row_count if active_bundle is not None else 0,
            "latest_year": active_bundle.latest_year if active_bundle is not None else None,
            "version": active_bundle.version if active_bundle is not None else None,
        }
    )
    overview_selection = reactive.Value(OverviewSelectionState())
    detail_selection = reactive.Value(OverviewSelectionState())
    drawer_desired_open = reactive.Value(False)
    workspace_desired_open = reactive.Value(False)
    presentation_lens = reactive.Value("authority")
    detail_close_generation = reactive.Value(0)
    restored_inputs: dict[str, Any] = {}
    restored_overview_state: dict[str, Any] = {}
    access = ACCESS_PROVIDER.current()

    @output
    @render.text
    def footer_snapshot_meta() -> str:
        current = snapshot()
        snapshot_date = _format_pacific_date(current.data_updated_at if current is not None else None)
        return f"DATA SNAPSHOT · {snapshot_date}" if snapshot_date else "DATA SNAPSHOT · UNAVAILABLE"

    @output
    @render.text
    def footer_refresh_meta() -> str:
        state = str(refresh_state().get("status") or "")
        if state == "running":
            return "CHECKING FOR UPDATES"
        if state in {"error", "stale"}:
            return "LAST UPDATE CHECK FAILED"
        hours = SETTINGS.cache_ttl_seconds / 3600
        interval = f"{hours:g} HOURS" if hours != 1 else "1 HOUR"
        return f"UPDATE CHECK EVERY {interval}"

    def _send_status_message(payload: dict[str, Any]) -> None:
        try:
            asyncio.create_task(session.send_custom_message("budget-source-status", payload))
        except RuntimeError:
            # The session can close between a process refresh completion and its
            # final status broadcast. The reactive state remains authoritative.
            LOG.debug("status message skipped for closed session")

    async def _apply_status_async(
        status: RefreshStatus,
        promoted: PreparedBudgetBundle | None = None,
    ) -> None:
        async with reactive.lock():
            with reactive.isolate():
                current = snapshot.get()
            if promoted is not None and (current is None or current.version != promoted.version):
                snapshot.set(promoted)
                current = promoted
            running = status.state == "running"
            display_status = "stale" if current is not None and status.state == "error" else status.state
            source_loading.set(running or current is None)
            source_error.set(status.message if status.state == "error" else None)
            refresh_state.set(
                {
                    "status": display_status if current is not None else ("loading" if running else "error"),
                    "cache_source": (
                        "stale-disk"
                        if current is not None and status.state == "error"
                        else ("memory" if current is not None else None)
                    ),
                    "row_count": current.metadata.row_count if current is not None else 0,
                    "latest_year": current.latest_year if current is not None else None,
                    "version": current.version if current is not None else None,
                }
            )
            payload = _status_payload(bundle=current, status=status, source_error=status.message)
        await reactive.flush()
        _send_status_message(payload)

    async def _show_normal_after_success() -> None:
        await asyncio.sleep(5)
        with reactive.isolate():
            current = snapshot.get()
        if current is not None:
            _send_status_message(
                _status_payload(
                    bundle=current,
                    status=RefreshStatus(state="idle", active_version=current.version),
                )
            )

    async def _on_bundle(promoted: PreparedBudgetBundle) -> None:
        with reactive.isolate():
            current = snapshot.get()
        if current is not None and current.version == promoted.version:
            return
        await _apply_status_async(_store_status(), promoted=promoted)
        session.on_flushed(_apply_restored_inputs, once=True)

    def _on_status(status: RefreshStatus) -> asyncio.Task[Any]:
        task = asyncio.create_task(_apply_status_async(status))
        if status.state == "success":
            asyncio.create_task(_show_normal_after_success())
        return task

    unsubscribe_bundle = SNAPSHOT_STORE.subscribe(_on_bundle)
    _STATUS_SUBSCRIBERS.add(_on_status)
    session.on_ended(unsubscribe_bundle)
    session.on_ended(lambda: _STATUS_SUBSCRIBERS.discard(_on_status))

    async def _send_initial_status() -> None:
        with reactive.isolate():
            current = snapshot.get()
            error = source_error.get()
        _send_status_message(_status_payload(bundle=current, status=_store_status(), source_error=error))

    session.on_flushed(_send_initial_status, once=True)
    _ensure_process_refresh()
    # The initial state is seeded synchronously from the active bundle. This
    # first payload is sent after the first flush so the persistent shell is
    # mounted before its text and attributes are updated.

    def _scrub_action_count(_value: Any) -> str:
        return "<action-count>"

    snapshot_preprocess_input("share_state", _scrub_action_count)
    snapshot_preprocess_input("retry_source", _scrub_action_count)

    LOG.info(
        "application session started",
        extra={"subject": access.subject, "authenticated": access.authenticated},
    )

    session.bookmark.exclude.extend(BOOKMARK_EXCLUDED_INPUTS)

    @session.bookmark.on_restore
    def _capture_restore(state: Any) -> None:
        # The query itself is intentionally never logged.
        restored_inputs.clear()
        restored_inputs.update(dict(state.input))
        restored_overview_state.clear()
        candidate = state.values.get("overview_selection")
        if isinstance(candidate, Mapping):
            restored_overview_state.update(dict(candidate))
        # A prepared bundle can now be active before the session starts, so no
        # later bundle notification is guaranteed to trigger restoration.
        # Apply the captured state after the first flush, once module
        # controllers and their persistent shells are mounted.
        session.on_flushed(_apply_restored_inputs, once=True)

    def _apply_restored_inputs() -> None:
        if not restored_inputs and not restored_overview_state:
            return
        with reactive.isolate():
            current = snapshot.get()
        if current is None:
            return
        rows = current.rows
        safe = sanitize_restored_inputs(
            restored_inputs,
            years=current.years,
            departments=tuple(rows["department"].dropna().astype(str).unique()),
            funds=tuple(rows["fund"].dropna().astype(str).unique()),
            categories=tuple(rows["category"].dropna().astype(str).unique()),
        )
        for input_id, value in safe.items():
            if input_id == "app_view":
                ui.update_navset("app_view", selected=str(value), session=session)
            elif input_id.startswith("drilldown-"):
                continue
            elif input_id == "lab-balanced":
                ui.update_checkbox(input_id, value=bool(value), session=session)
            elif input_id.startswith("lab-adjustment_"):
                ui.update_numeric(input_id, value=float(value), session=session)
            else:
                ui.update_select(input_id, selected=str(value), session=session)

        restored_state: Mapping[str, Any] | None = restored_overview_state or None
        legacy_drilldown = str(restored_inputs.get("app_view") or "") == "drilldown"
        if legacy_drilldown and restored_state is None:
            restored_state = {
                "year": restored_inputs.get("drilldown-year"),
                "compare_year": restored_inputs.get("drilldown-compare"),
                "flow": restored_inputs.get("drilldown-flow", "all"),
                "fund_scope": restored_inputs.get("drilldown-fund_scope", "all_funds"),
                "department": restored_inputs.get("drilldown-department"),
                "fund": restored_inputs.get("drilldown-fund"),
                "category": restored_inputs.get("drilldown-category"),
                "drawer_open": False,
                "workspace_open": True,
            }
        if restored_state is not None:
            safe_overview = sanitize_overview_selection(
                restored_state,
                years=current.years,
                departments=tuple(rows["department"].dropna().astype(str).unique()),
                funds=tuple(rows["fund"].dropna().astype(str).unique()),
                categories=tuple(rows["category"].dropna().astype(str).unique()),
                records=tuple(rows["object_id"].dropna().astype(int).unique()),
            )
            overview_controller.restore(
                safe_overview,
                sanitize_overview_presentation(restored_state),
            )
        restored_inputs.clear()
        restored_overview_state.clear()

    @session.bookmark.on_bookmark
    def _save_overview_state(state: Any) -> None:
        with reactive.isolate():
            selection = detail_selection.get() if drawer_desired_open.get() else overview_selection.get()
            presentation = OverviewPresentationState(
                drawer_open=drawer_desired_open.get(),
                workspace_open=workspace_desired_open.get(),
                lens=presentation_lens.get(),
            )
        state.values["overview_selection"] = compose_overview_bookmark_value(selection, presentation)

    @reactive.effect
    @reactive.event(input.retry_source)
    def _manual_refresh() -> None:
        global _LAST_MANUAL_REFRESH_AT
        if not MANUAL_REFRESH_ENABLED:
            LOG.warning("manual source refresh ignored because it is disabled")
            return
        now = time.monotonic()
        if now - _LAST_MANUAL_REFRESH_AT < SETTINGS.manual_refresh_cooldown_seconds:
            LOG.warning("manual source refresh ignored during cooldown")
            return
        _LAST_MANUAL_REFRESH_AT = now
        _start_coordinated_refresh(force=True)

    @reactive.effect
    @reactive.event(input.app_view)
    async def _sync_view() -> None:
        requested = str(input.app_view() or "overview")
        selected = requested if requested in VALID_VIEWS else "overview"
        await session.send_custom_message("budget-view-selected", {"view": selected})

    @reactive.effect
    @reactive.event(input.share_state)
    async def _share_state() -> None:
        await session.bookmark.do_bookmark()

    @reactive.effect
    @reactive.event(input.detail_reopen_request)
    def _reopen_last_detail_context() -> None:
        """Let row and chart reactivation supersede a still-settling close."""

        if detail_close_generation.get() > 0 and not drawer_desired_open.get():
            drawer_desired_open.set(True)

    @session.bookmark.on_bookmarked
    async def _bookmark_ready(url: str) -> None:
        await session.send_custom_message("budget-bookmarked", {"url": url})

    def _update_detail_context(value: OverviewSelectionState) -> None:
        if detail_selection.get() != value:
            detail_selection.set(value)

    overview_controller = overview_server(
        "overview",
        snapshot=snapshot,
        selection=overview_selection,
        detail_selection=detail_selection,
        drawer_desired_open=drawer_desired_open,
        workspace_desired_open=workspace_desired_open,
        presentation_lens=presentation_lens,
        defer_context_callback=_update_detail_context,
        detail_close_signal=detail_close_generation,
    )

    def _open_integrated_detail(value: Mapping[str, Any] | str) -> None:
        if isinstance(value, str):
            payload: dict[str, Any]
            if value.startswith("__year__:"):
                payload = {"year": value.removeprefix("__year__:"), "department": ""}
            else:
                payload = {"department": value}
        else:
            payload = dict(value)
        overview_controller.open_selection(payload)

    async def _expand_integrated_detail(target: str) -> None:
        with reactive.isolate():
            detail_context = detail_selection.get()
            overview_context = overview_selection.get()
            workspace_was_open = workspace_desired_open.get()
        context_changed = overview_context != detail_context
        if context_changed:
            overview_selection.set(detail_context)
            if workspace_was_open:
                workspace_desired_open.set(False)

        async def _focus_workspace() -> None:
            await session.send_custom_message(
                "budget-workspace-focus",
                {"id": ("overview-records" if target == "records" else "overview-analysis-workspace")},
            )

        def _show_workspace() -> None:
            workspace_desired_open.set(True)
            session.on_flushed(_focus_workspace, once=True)

        if context_changed and workspace_was_open:
            session.on_flushed(_show_workspace, once=True)
        else:
            workspace_desired_open.set(True)
            session.on_flushed(_focus_workspace, once=True)
        ui.update_navset("app_view", selected="overview", session=session)

    def _detail_closed() -> None:
        detail_close_generation.set(detail_close_generation.get() + 1)

    detail_drawer_server(
        "detail",
        snapshot=snapshot,
        selection=detail_selection,
        drawer_desired_open=drawer_desired_open,
        presentation_lens=presentation_lens,
        context_callback=_update_detail_context,
        expand_callback=_expand_integrated_detail,
        close_callback=_detail_closed,
    )
    budget_101_server(
        "budget101",
        snapshot=snapshot,
        navigation_callback=_open_integrated_detail,
    )
    what_changed_server(
        "changed",
        snapshot=snapshot,
        navigation_callback=_open_integrated_detail,
        detail_close_signal=detail_close_generation,
        active=lambda: str(input.app_view()) == "changed",
    )
    explorer_server(
        "explorer",
        snapshot=snapshot,
        navigation_callback=_open_integrated_detail,
        detail_close_signal=detail_close_generation,
        active=lambda: str(input.app_view()) == "explorer",
    )

    def _application_test_state() -> dict[str, Any]:
        current = snapshot()
        return {
            "source": dict(refresh_state()),
            "source_loading": source_loading(),
            "overview_selection": overview_selection().as_bookmark_value(),
            "detail_selection": detail_selection().as_bookmark_value(),
            "drawer_desired_open": drawer_desired_open(),
            "workspace_desired_open": workspace_desired_open(),
            "presentation_lens": presentation_lens(),
            "detail_close_generation": detail_close_generation(),
            "snapshot_stale": (current.snapshot.stale if current is not None else None)
            or (refresh_state().get("status") == "stale"),
            "snapshot_version": current.version if current is not None else None,
        }

    export_test_values(application_state=_application_test_state)
    methods_server(
        "methods",
        snapshot=snapshot,
        navigation_callback=_open_integrated_detail,
    )
    lab_server(
        "lab",
        snapshot=snapshot,
        navigation_callback=_open_integrated_detail,
    )


app = App(
    _application_ui,
    _server,
    static_assets={
        "/favicon.ico": PROJECT_ROOT / "www" / "assets" / "COStreatmentBLUE.png",
        "/": PROJECT_ROOT / "www",
    },
    bookmark_store="url",
)


async def _health_live(_request: Any) -> JSONResponse:
    return JSONResponse({"status": "live"}, headers={"cache-control": "no-store"})


async def _health_ready(_request: Any) -> JSONResponse:
    bundle = SNAPSHOT_STORE.active_bundle
    cache_writable = SETTINGS.cache_dir.exists() and os.access(SETTINGS.cache_dir, os.W_OK)
    ready = bundle is not None and cache_writable
    return JSONResponse(
        {
            "status": "ready" if ready else "not-ready",
            "snapshot": "available" if bundle is not None else "unavailable",
            "cache": "writable" if cache_writable else "unavailable",
        },
        status_code=200 if ready else 503,
        headers={"cache-control": "no-store"},
    )


async def _robots_txt(_request: Any) -> PlainTextResponse:
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@asynccontextmanager
async def _platform_lifespan(_platform: Starlette) -> Any:
    # Starlette does not automatically run the lifespan of a mounted ASGI app.
    # Preserve Shiny's lifecycle before starting Atlas background work.
    async with _shiny_routes.router.lifespan_context(_shiny_routes):
        startup_task = _ensure_process_refresh()
        try:
            yield
        finally:
            scheduled = _PROCESS_REFRESH_TASK
            if scheduled is not None and not scheduled.done():
                scheduled.cancel()
                with suppress(asyncio.CancelledError):
                    await scheduled
            if startup_task is not scheduled and not startup_task.done():
                startup_task.cancel()
            await SNAPSHOT_STORE.aclose()


_shiny_routes = app.starlette_app
_base_mount = SETTINGS.app_base_path.rstrip("/") or "/"
_platform_routes: list[Any] = [
    Route("/robots.txt", _robots_txt, methods=["GET"]),
    Route("/health/live", _health_live, methods=["GET"]),
    Route("/health/ready", _health_ready, methods=["GET"]),
]
if _base_mount != "/":
    _platform_routes.append(
        Route("/", lambda _request: RedirectResponse(SETTINGS.app_base_path, status_code=307))
    )
_platform_routes.append(Mount(_base_mount, app=_shiny_routes))
app.starlette_app = Starlette(
    routes=_platform_routes,
    middleware=[
        Middleware(TrustedHostMiddleware, allowed_hosts=list(SETTINGS.allowed_hosts)),
        Middleware(GZipMiddleware, minimum_size=1000),
        Middleware(SecurityHeadersMiddleware),
    ],
    lifespan=_platform_lifespan,
)
