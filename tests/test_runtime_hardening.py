from __future__ import annotations

import httpx
import pytest

from app import asgi_app
from budget_app.application import app


@pytest.mark.asyncio
async def test_health_routes_and_security_headers() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "live"}
    assert ready.status_code in {200, 503}
    assert ready.json()["status"] in {"ready", "not-ready"}
    assert live.headers["cache-control"] == "no-store"
    assert live.headers["x-content-type-options"] == "nosniff"
    assert live.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in live.headers["content-security-policy"]
    assert live.headers["strict-transport-security"].startswith("max-age=31536000")
    assert live.headers["x-robots-tag"] == "noindex, nofollow"


@pytest.mark.asyncio
async def test_public_pilot_excludes_cooperative_crawlers() -> None:
    """Removing either robots control could invite indexing of the temporary public URL."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        robots = await client.get("/robots.txt")

    assert robots.status_code == 200
    assert robots.headers["content-type"].startswith("text/plain")
    assert robots.headers["x-robots-tag"] == "noindex, nofollow"
    assert robots.text == "User-agent: *\nDisallow: /\n"


@pytest.mark.asyncio
async def test_untrusted_host_is_rejected() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://evil.example") as client:
        response = await client.get("/health/live")

    assert response.status_code == 400


def test_production_asgi_export_is_the_hardened_platform_boundary() -> None:
    assert asgi_app is app.starlette_app
