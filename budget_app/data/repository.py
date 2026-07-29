"""Async ArcGIS repository with process and last-known-good parquet caching."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from budget_app.config import Settings

from .models import BudgetSnapshot, CacheSource, RepositoryResult, SnapshotMetadata, SnapshotStatus
from .normalize import DataValidationError, normalize_features, normalize_frame
from .prepared import PreparedBundleStore, prepare_bundle

LOG = logging.getLogger(__name__)
PAGE_SIZE = 1000
MAX_PAGES = 100

_MEMORY_CACHE: dict[str, tuple[BudgetSnapshot, float]] = {}
_CACHE_LOCK = asyncio.Lock()


class RepositoryError(RuntimeError):
    """Raised when ArcGIS and the local cache cannot provide a snapshot."""


class SnapshotUnavailableError(RepositoryError):
    """No source response or valid last-known-good cache is available."""


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _last_edit_date(payload: dict[str, Any]) -> int | None:
    candidate = payload.get("lastEditDate")
    if candidate is None and isinstance(payload.get("editingInfo"), dict):
        candidate = payload["editingInfo"].get("lastEditDate")
    try:
        return int(candidate) if candidate is not None else None
    except (TypeError, ValueError):
        return None


class ArcGISBudgetRepository:
    """Fetch and normalize all rows in deterministic ObjectId order."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client
        self._owns_client = client is None
        self._client_started = client is not None
        self.cache_dir = Path(settings.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.bundle_store = PreparedBundleStore(
            self.cache_dir,
            schema_version=settings.prepared_schema_version,
        )

    @property
    def query_url(self) -> str:
        return f"{self.settings.arcgis_url.rstrip('/')}/query"

    @property
    def parquet_path(self) -> Path:
        return self.cache_dir / "approved-budgets.parquet"

    @property
    def metadata_path(self) -> Path:
        return self.cache_dir / "approved-budgets.metadata.json"

    async def _request_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._client is None:
            # Keep one process-level client for metadata and every page in a
            # refresh flight.  Closing is explicit via ``aclose``.
            self._client = httpx.AsyncClient(timeout=45.0)
            self._client_started = True
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RepositoryError("ArcGIS response was not a JSON object")
        if payload.get("error"):
            error = payload["error"]
            message = (
                error.get("message", "ArcGIS returned an error") if isinstance(error, dict) else str(error)
            )
            raise RepositoryError(str(message))
        return payload

    async def aclose(self) -> None:
        """Close the repository-owned HTTP client during process shutdown."""

        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None
            self._client_started = False

    async def _source_metadata(self) -> dict[str, Any]:
        return await self._request_json(self.settings.arcgis_url, {"f": "json"})

    async def _fetch_pages(self) -> pd.DataFrame:
        features: list[dict[str, Any]] = []
        offset = 0
        for _page in range(MAX_PAGES):
            payload = await self._request_json(
                self.query_url,
                {
                    "where": "1=1",
                    "outFields": "*",
                    "f": "json",
                    "resultOffset": offset,
                    "resultRecordCount": PAGE_SIZE,
                    "orderByFields": "ObjectId ASC",
                },
            )
            batch = payload.get("features")
            if not isinstance(batch, list):
                raise RepositoryError("ArcGIS query response did not include a features array")
            if not batch:
                break
            features.extend(batch)
            exceeded = bool(
                payload.get("exceededTransferLimit")
                or (
                    isinstance(payload.get("properties"), dict)
                    and payload["properties"].get("exceededTransferLimit")
                )
            )
            offset += len(batch)
            # A full page without the flag is deliberately followed by an empty
            # or partial probe, protecting against ArcGIS terminal-page quirks.
            if not exceeded and len(batch) < PAGE_SIZE:
                break
        else:
            raise RepositoryError("Approved Budgets API exceeded the 100-page safety cap")
        if not features:
            raise RepositoryError("Approved Budgets API returned no rows")
        return normalize_features(features)

    async def fetch_rows(self) -> pd.DataFrame:
        """Fetch a complete normalized dataframe without consulting caches."""

        return await self._fetch_pages()

    def _read_disk(self) -> tuple[BudgetSnapshot, SnapshotMetadata] | None:
        try:
            bundle = self.bundle_store.load_current()
            if bundle is not None:
                return bundle.snapshot, bundle.metadata
            if not self.parquet_path.exists() or not self.metadata_path.exists():
                return None
            metadata = SnapshotMetadata.from_dict(json.loads(self.metadata_path.read_text(encoding="utf-8")))
            rows = normalize_frame(pd.read_parquet(self.parquet_path))
            # Legacy pair migration is deliberately non-destructive.  A
            # successful migration becomes authoritative for subsequent reads.
            bundle = prepare_bundle(
                rows,
                source_url=metadata.source_url,
                source_last_edit_date=metadata.source_last_edit_date,
                generated_at=metadata.generated_at,
                fetched_at=metadata.fetched_at,
            )
            self.bundle_store.promote(bundle)
            return bundle.snapshot, bundle.metadata
        except (OSError, ValueError, TypeError, DataValidationError, KeyError) as exc:
            LOG.warning("invalid budget cache: %s", exc)
            return None

    def _write_disk(self, snapshot: BudgetSnapshot) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        parquet_tmp: str | None = None
        metadata_tmp: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.cache_dir, suffix=".parquet.tmp", delete=False
            ) as handle:
                parquet_tmp = handle.name
            snapshot.rows.to_parquet(parquet_tmp, index=False)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.cache_dir, suffix=".json.tmp", delete=False
            ) as handle:
                metadata_tmp = handle.name
                json.dump(snapshot.metadata.as_dict(), handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(parquet_tmp, self.parquet_path)
            os.replace(metadata_tmp, self.metadata_path)
        finally:
            for temporary in (parquet_tmp, metadata_tmp):
                if temporary:
                    with suppress(OSError):
                        Path(temporary).unlink(missing_ok=True)

    async def load_result(self, *, force: bool = False) -> RepositoryResult:
        """Return a status-bearing snapshot, falling back to stale disk data."""

        started = time.perf_counter()

        def completed(
            snapshot: BudgetSnapshot,
            status: SnapshotStatus,
            *,
            cache_source: CacheSource,
            message: str | None = None,
        ) -> RepositoryResult:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            LOG.info(
                "budget repository load completed",
                extra={
                    "cache_source": cache_source,
                    "elapsed_ms": elapsed_ms,
                    "force": force,
                    "row_count": snapshot.metadata.row_count,
                    "status": status,
                },
            )
            return RepositoryResult(
                snapshot,
                status,
                message,
                cache_source=cache_source,
                elapsed_ms=elapsed_ms,
            )

        cache_key = self.settings.arcgis_url
        now = _now().timestamp()
        async with _CACHE_LOCK:
            cached = _MEMORY_CACHE.get(cache_key)
        if cached and not force and not cached[0].stale and now - cached[1] < self.settings.cache_ttl_seconds:
            return completed(cached[0], cached[0].status, cache_source="memory")

        # Parquet reconstruction and legacy migration are blocking work.  Do
        # not hold the async lock or event loop while doing either operation.
        disk = await asyncio.to_thread(self._read_disk)
        disk_snapshot = disk[0] if disk else None
        disk_metadata = disk[1] if disk else None
        disk_age = now - _timestamp(disk_metadata.fetched_at) if disk_metadata else float("inf")
        try:
            if (
                disk_snapshot is not None
                and disk_metadata is not None
                and not force
                and disk_age < self.settings.cache_ttl_seconds
            ):
                fresh = replace(disk_snapshot, status="fresh", status_message=None)
                async with _CACHE_LOCK:
                    _MEMORY_CACHE[cache_key] = (fresh, now)
                return completed(fresh, "fresh", cache_source="disk-fresh")
            try:
                source_metadata = await self._source_metadata()
                source_edit = _last_edit_date(source_metadata)
            except Exception as metadata_error:  # noqa: BLE001
                # Metadata is a freshness optimization. A direct page fetch
                # remains useful when a test gateway or ArcGIS edge omits it.
                LOG.warning("budget layer metadata request failed: %s", metadata_error)
                source_edit = None
            if (
                disk_snapshot is not None
                and disk_metadata is not None
                and source_edit is not None
                and source_edit == disk_metadata.source_last_edit_date
            ):
                fresh = replace(disk_snapshot, status="fresh", status_message=None)
                async with _CACHE_LOCK:
                    _MEMORY_CACHE[cache_key] = (fresh, now)
                return completed(fresh, "fresh", cache_source="disk-revalidated")
            rows = await self._fetch_pages()
            bundle = await asyncio.to_thread(
                prepare_bundle,
                rows,
                source_url=self.settings.arcgis_url,
                source_last_edit_date=source_edit,
                checked_at=_now().isoformat(),
                schema_version=self.settings.prepared_schema_version,
            )
            if (
                disk_snapshot is not None
                and disk_snapshot.metadata.content_hash
                and bundle.metadata.content_hash == disk_snapshot.metadata.content_hash
            ):
                fresh = replace(disk_snapshot, status="fresh", status_message=None)
                async with _CACHE_LOCK:
                    _MEMORY_CACHE[cache_key] = (fresh, now)
                return completed(fresh, "fresh", cache_source="disk-revalidated")
            promoted = await asyncio.to_thread(self.bundle_store.promote, bundle)
            # Keep the old pair as a safe migration source for operators and
            # older tools.  It is never used for atomic promotion.
            await asyncio.to_thread(self._write_disk, promoted.snapshot)
            async with _CACHE_LOCK:
                _MEMORY_CACHE[cache_key] = (promoted.snapshot, now)
            return completed(promoted.snapshot, "fresh", cache_source="source")
        except Exception as exc:  # noqa: BLE001, source failures need stale fallback
            LOG.warning("budget source refresh failed: %s", exc)
            if disk_snapshot is not None:
                stale = replace(disk_snapshot, status="stale", status_message=str(exc))
                async with _CACHE_LOCK:
                    _MEMORY_CACHE[cache_key] = (stale, now)
                return completed(stale, "stale", cache_source="stale-disk", message=str(exc))
            raise SnapshotUnavailableError(str(exc)) from exc

    async def load_snapshot(self, *, force: bool = False) -> BudgetSnapshot:
        result = await self.load_result(force=force)
        if result.snapshot is None:
            raise SnapshotUnavailableError(result.message or "Budget snapshot unavailable")
        return result.snapshot

    async def fetch_snapshot(self, *, force: bool = False) -> BudgetSnapshot:
        return await self.load_snapshot(force=force)

    async def load(self, *, force: bool = False) -> BudgetSnapshot:
        return await self.load_snapshot(force=force)


async def fetch_budget_snapshot(settings: Settings, *, force: bool = False) -> BudgetSnapshot:
    return await ArcGISBudgetRepository(settings).load_snapshot(force=force)
