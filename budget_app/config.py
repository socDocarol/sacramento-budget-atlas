from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ARCGIS_URL = (
    "https://services5.arcgis.com/54falWtcpty3V47Z/arcgis/rest/services/"
    "City_of_Sacramento_Approved_Budgets/FeatureServer/0"
)


def _positive_int(value: str, default: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _base_path(value: str) -> str:
    stripped = value.strip()
    if not stripped or stripped == "/":
        return "/"
    return f"/{stripped.strip('/')}/"


@dataclass(frozen=True, slots=True)
class Settings:
    arcgis_url: str
    cache_dir: Path
    cache_ttl_seconds: int
    log_level: str
    app_base_path: str
    prepared_schema_version: int = 1

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> Settings:
        root = project_root or Path(__file__).resolve().parents[1]
        return cls(
            arcgis_url=os.getenv("BUDGET_ARCGIS_URL", DEFAULT_ARCGIS_URL).rstrip("/"),
            cache_dir=Path(os.getenv("BUDGET_CACHE_DIR", str(root / ".cache"))).resolve(),
            cache_ttl_seconds=_positive_int(
                os.getenv("BUDGET_CACHE_TTL_SECONDS", "86400"),
                86400,
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            app_base_path=_base_path(os.getenv("APP_BASE_PATH", "/")),
            prepared_schema_version=_positive_int(
                os.getenv("BUDGET_PREPARED_SCHEMA_VERSION", "1"),
                1,
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
