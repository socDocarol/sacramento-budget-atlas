"""Composable page modules for the Sacramento Budget Shiny pilot."""

from .budget_101 import budget_101_server, budget_101_ui
from .detail_drawer import detail_drawer_server, detail_drawer_ui
from .explorer import explorer_server, explorer_ui
from .lab import lab_server, lab_ui
from .methods import methods_server, methods_ui
from .overview import overview_server, overview_ui
from .what_changed import what_changed_server, what_changed_ui

__all__ = [
    "budget_101_server",
    "budget_101_ui",
    "detail_drawer_server",
    "detail_drawer_ui",
    "explorer_server",
    "explorer_ui",
    "lab_server",
    "lab_ui",
    "methods_server",
    "methods_ui",
    "overview_server",
    "overview_ui",
    "what_changed_server",
    "what_changed_ui",
]
