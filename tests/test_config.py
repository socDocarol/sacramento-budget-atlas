from pathlib import Path

from budget_app.access import NetworkAccessContextProvider
from budget_app.config import DEFAULT_ARCGIS_URL, Settings


def test_settings_defaults_are_internal_pilot_safe(monkeypatch, tmp_path: Path) -> None:
    for key in (
        "BUDGET_ARCGIS_URL",
        "BUDGET_CACHE_DIR",
        "BUDGET_CACHE_TTL_SECONDS",
        "LOG_LEVEL",
        "APP_BASE_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings.from_env(tmp_path)

    assert settings.arcgis_url == DEFAULT_ARCGIS_URL
    assert settings.cache_dir == (tmp_path / ".cache").resolve()
    assert settings.cache_ttl_seconds == 86400
    assert settings.log_level == "INFO"
    assert settings.app_base_path == "/"


def test_settings_sanitize_invalid_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BUDGET_CACHE_TTL_SECONDS", "-5")
    monkeypatch.setenv("APP_BASE_PATH", "internal/budget/")

    settings = Settings.from_env(tmp_path)

    assert settings.cache_ttl_seconds == 86400
    assert settings.app_base_path == "/internal/budget/"


def test_network_access_provider_ignores_identity_headers() -> None:
    context = NetworkAccessContextProvider().current()

    assert context.subject == "network-user"
    assert context.authenticated is False
    assert context.groups == ()
