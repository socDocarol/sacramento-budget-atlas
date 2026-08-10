"""ASGI entry point for the Sacramento Budget Shiny pilot."""

from budget_app.application import app

# Keep ``app`` for the Shiny CLI and expose the concrete platform boundary for
# production ASGI servers. This avoids relying on Shiny's wrapper delegation
# when Uvicorn resolves the module attribute.
asgi_app = app.starlette_app

__all__ = ["app", "asgi_app"]
