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
        "APP_ALLOWED_HOSTS",
        "BUDGET_MANUAL_REFRESH_ENABLED",
        "BUDGET_MANUAL_REFRESH_COOLDOWN_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings.from_env(tmp_path)

    assert settings.arcgis_url == DEFAULT_ARCGIS_URL
    assert settings.cache_dir == (tmp_path / ".cache").resolve()
    assert settings.cache_ttl_seconds == 86400
    assert settings.log_level == "INFO"
    assert settings.app_base_path == "/"
    assert settings.allowed_hosts == ("localhost", "127.0.0.1", "testserver")
    assert settings.manual_refresh_enabled is False
    assert settings.manual_refresh_cooldown_seconds == 300


def test_settings_normalize_base_path_and_explicit_controls(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BUDGET_CACHE_TTL_SECONDS", "3600")
    monkeypatch.setenv("APP_BASE_PATH", "internal/budget/")
    monkeypatch.setenv("APP_ALLOWED_HOSTS", "budget.example.gov, *.azurewebsites.net")
    monkeypatch.setenv("BUDGET_MANUAL_REFRESH_ENABLED", "yes")

    settings = Settings.from_env(tmp_path)

    assert settings.cache_ttl_seconds == 3600
    assert settings.app_base_path == "/internal/budget/"
    assert settings.allowed_hosts == ("budget.example.gov", "*.azurewebsites.net")
    assert settings.manual_refresh_enabled is True


def test_settings_fail_fast_on_invalid_production_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BUDGET_CACHE_TTL_SECONDS", "-5")
    try:
        Settings.from_env(tmp_path)
    except ValueError as exc:
        assert "BUDGET_CACHE_TTL_SECONDS" in str(exc)
    else:
        raise AssertionError("invalid production configuration must fail fast")

    monkeypatch.setenv("BUDGET_CACHE_TTL_SECONDS", "60")
    monkeypatch.setenv("BUDGET_ARCGIS_URL", "http://example.com/FeatureServer/0")
    try:
        Settings.from_env(tmp_path)
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("non-TLS source URLs must be rejected")


def test_settings_reject_unsafe_routing_and_logging_values(monkeypatch, tmp_path: Path) -> None:
    invalid_values = (
        ("APP_BASE_PATH", "../admin", "APP_BASE_PATH"),
        ("APP_ALLOWED_HOSTS", "https://budget.example.gov", "APP_ALLOWED_HOSTS"),
        ("LOG_LEVEL", "verbose", "LOG_LEVEL"),
    )
    for variable, value, expected in invalid_values:
        monkeypatch.setenv(variable, value)
        try:
            Settings.from_env(tmp_path)
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"{variable} must fail fast")
        monkeypatch.delenv(variable)


def test_network_access_provider_ignores_identity_headers() -> None:
    context = NetworkAccessContextProvider().current()

    assert context.subject == "network-user"
    assert context.authenticated is False
    assert context.groups == ()
