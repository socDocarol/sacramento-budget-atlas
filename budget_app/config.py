from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_ARCGIS_URL = (
    "https://services5.arcgis.com/54falWtcpty3V47Z/arcgis/rest/services/"
    "City_of_Sacramento_Approved_Budgets/FeatureServer/0"
)


def _positive_int(value: str | None, default: int, *, name: str) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _boolean(value: str | None, default: bool, *, name: str) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _allowed_hosts(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ("localhost", "127.0.0.1", "testserver")
    hosts = tuple(dict.fromkeys(item.strip().lower() for item in value.split(",") if item.strip()))
    if not hosts:
        raise ValueError("APP_ALLOWED_HOSTS must contain at least one host")
    hostname = re.compile(
        r"(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    )
    if any(host != "*" and hostname.fullmatch(host) is None for host in hosts):
        raise ValueError("APP_ALLOWED_HOSTS entries must be hostnames without schemes, ports, or paths")
    return hosts


def _arcgis_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    loopback_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not loopback_http:
        raise ValueError("BUDGET_ARCGIS_URL must use HTTPS except for a loopback test endpoint")
    if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("BUDGET_ARCGIS_URL must be an absolute layer URL without credentials or query data")
    return candidate


def _base_path(value: str) -> str:
    stripped = value.strip()
    if not stripped or stripped == "/":
        return "/"
    normalized = stripped.strip("/")
    segments = normalized.split("/")
    if any(
        segment in {"", ".", ".."} or re.fullmatch(r"[A-Za-z0-9._~-]+", segment) is None
        for segment in segments
    ):
        raise ValueError("APP_BASE_PATH must contain only safe URL path segments")
    return f"/{normalized}/"


def _log_level(value: str) -> str:
    level = value.strip().upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
    return level


@dataclass(frozen=True, slots=True)
class Settings:
    arcgis_url: str
    cache_dir: Path
    cache_ttl_seconds: int
    log_level: str
    app_base_path: str
    allowed_hosts: tuple[str, ...]
    manual_refresh_enabled: bool
    manual_refresh_cooldown_seconds: int
    prepared_schema_version: int = 1

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> Settings:
        root = project_root or Path(__file__).resolve().parents[1]
        return cls(
            arcgis_url=_arcgis_url(os.getenv("BUDGET_ARCGIS_URL", DEFAULT_ARCGIS_URL)),
            cache_dir=Path(os.getenv("BUDGET_CACHE_DIR", str(root / ".cache"))).resolve(),
            cache_ttl_seconds=_positive_int(
                os.getenv("BUDGET_CACHE_TTL_SECONDS"),
                86400,
                name="BUDGET_CACHE_TTL_SECONDS",
            ),
            log_level=_log_level(os.getenv("LOG_LEVEL", "INFO")),
            app_base_path=_base_path(os.getenv("APP_BASE_PATH", "/")),
            allowed_hosts=_allowed_hosts(os.getenv("APP_ALLOWED_HOSTS")),
            manual_refresh_enabled=_boolean(
                os.getenv("BUDGET_MANUAL_REFRESH_ENABLED"),
                False,
                name="BUDGET_MANUAL_REFRESH_ENABLED",
            ),
            manual_refresh_cooldown_seconds=_positive_int(
                os.getenv("BUDGET_MANUAL_REFRESH_COOLDOWN_SECONDS"),
                300,
                name="BUDGET_MANUAL_REFRESH_COOLDOWN_SECONDS",
            ),
            prepared_schema_version=_positive_int(
                os.getenv("BUDGET_PREPARED_SCHEMA_VERSION"),
                1,
                name="BUDGET_PREPARED_SCHEMA_VERSION",
            ),
        )


def configure_logging(level: str) -> None:
    class JsonFormatter(logging.Formatter):
        _standard = frozenset(
            {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "taskName",
            }
        )

        def format(self, record: logging.LogRecord) -> str:
            payload: dict[str, object] = {
                "time": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            payload.update(
                {
                    key: value
                    for key, value in record.__dict__.items()
                    if key not in self._standard and not key.startswith("_")
                }
            )
            if record.exc_info:
                payload["exception"] = self.formatException(record.exc_info)
            return json.dumps(payload, default=str, ensure_ascii=True)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        handlers=[handler],
        force=True,
    )
