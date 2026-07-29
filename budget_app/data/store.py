"""Process-wide immutable snapshot store and single-flight refresh coordinator."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from budget_app.config import Settings

from .models import BudgetSnapshot, PreparedBudgetBundle, RefreshStatus
from .prepared import PreparedBundleStore
from .repository import ArcGISBudgetRepository, SnapshotUnavailableError

LOG = logging.getLogger(__name__)
Subscriber = Callable[[PreparedBudgetBundle], Any]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SnapshotStore:
    """Hold one active bundle while coordinating one process-wide refresh.

    ``active_bundle`` and ``active_snapshot`` are synchronous reads and remain
    available while a refresh is fetching or preparing a replacement.  The
    coordinator is intended for a single Shiny process.  Multi-process use
    requires shared bundle storage plus a cross-process lease.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        repository: ArcGISBudgetRepository | None = None,
        bundle_store: PreparedBundleStore | None = None,
    ) -> None:
        self.settings = settings or (repository.settings if repository else Settings.from_env())
        self.repository = repository or ArcGISBudgetRepository(self.settings)
        self.bundle_store = bundle_store or PreparedBundleStore(self.settings.cache_dir)
        self._active: PreparedBudgetBundle | None = None
        self._status = RefreshStatus()
        self._flight: asyncio.Task[PreparedBudgetBundle | None] | None = None
        self._flight_lock = asyncio.Lock()
        self._subscribers: list[Subscriber] = []
        # Disk reconstruction is synchronous by contract for startup callers,
        # but happens once and never in the reactive graph.
        self._active = self.bundle_store.load_current()

    @property
    def active_bundle(self) -> PreparedBudgetBundle | None:
        """Current immutable bundle, synchronously readable by every session."""

        return self._active

    @property
    def bundle(self) -> PreparedBudgetBundle | None:
        return self._active

    @property
    def active_snapshot(self) -> BudgetSnapshot | None:
        return self._active.snapshot if self._active else None

    @property
    def snapshot(self) -> BudgetSnapshot | None:
        return self.active_snapshot

    @property
    def status(self) -> RefreshStatus:
        return self._status

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        """Subscribe to promoted version changes and return an unsubscribe function."""

        self._subscribers.append(callback)

        def unsubscribe() -> None:
            with suppress(ValueError):
                self._subscribers.remove(callback)

        return unsubscribe

    def _set_status(self, **changes: Any) -> None:
        values = {
            "state": self._status.state,
            "started_at": self._status.started_at,
            "completed_at": self._status.completed_at,
            "active_version": self._active.version if self._active else None,
            "message": self._status.message,
            "stage_timings_ms": self._status.stage_timings_ms,
        }
        values.update(changes)
        self._status = RefreshStatus(**values)

    async def _notify(self, bundle: PreparedBudgetBundle) -> None:
        for callback in tuple(self._subscribers):
            try:
                result = callback(bundle)
                if inspect.isawaitable(result):
                    await result
            except Exception:  # noqa: BLE001
                LOG.exception("prepared bundle subscriber failed")

    async def _refresh_once(self, force: bool) -> PreparedBudgetBundle | None:
        started = time.perf_counter()
        self._set_status(state="running", started_at=_now(), message=None)
        try:
            result = await self.repository.load_result(force=force)
            if result.snapshot is None or result.status == "stale":
                raise SnapshotUnavailableError(result.message or "No complete prepared snapshot available")
            # Repository promotion is complete before the pointer is read.  A
            # disk read is isolated from the event loop and validates every
            # written artifact before becoming active.
            bundle = await asyncio.to_thread(self.bundle_store.load_current)
            if bundle is None:
                raise SnapshotUnavailableError("Source refresh produced no prepared bundle")
            previous_version = self._active.version if self._active else None
            changed = previous_version != bundle.version
            if changed:
                self._active = bundle
                await self._notify(bundle)
                state = "success"
            else:
                # Keep object identity and version stable so no reactive graph
                # invalidation occurs for unchanged source data.
                state = "unchanged"
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            self._set_status(
                state=state,
                completed_at=_now(),
                active_version=self._active.version if self._active else None,
                stage_timings_ms={"refresh": elapsed},
            )
            return self._active
        except Exception as exc:  # noqa: BLE001
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            self._set_status(
                state="error",
                completed_at=_now(),
                active_version=self._active.version if self._active else None,
                message=str(exc),
                stage_timings_ms={"refresh": elapsed},
            )
            if self._active is not None:
                LOG.warning("refresh failed, retaining active budget bundle: %s", exc)
                return self._active
            raise

    async def refresh(self, *, force: bool = False) -> PreparedBudgetBundle | None:
        """Run or join one refresh flight; concurrent callers share its result."""

        async with self._flight_lock:
            if self._flight is None or self._flight.done():
                self._flight = asyncio.create_task(self._refresh_once(force))
            flight = self._flight
        try:
            return await flight
        finally:
            async with self._flight_lock:
                if self._flight is flight and flight.done():
                    self._flight = None

    async def ensure_loaded(self) -> PreparedBudgetBundle | None:
        """Return disk data immediately, refreshing only when no active bundle exists."""

        if self._active is not None:
            return self._active
        return await self.refresh(force=False)

    def start_background_refresh(self, *, force: bool = False) -> asyncio.Task[PreparedBudgetBundle | None]:
        """Schedule a refresh without blocking the caller's reactive flush."""

        return asyncio.create_task(self.refresh(force=force))

    async def aclose(self) -> None:
        await self.repository.aclose()


# Name used by integration code that wants to emphasize coordination.
RefreshCoordinator = SnapshotStore
