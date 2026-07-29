"""Compatibility import for the Sources & Methods module."""

from .methods import methods_server, methods_ui

sources_methods_server = methods_server
sources_methods_ui = methods_ui

__all__ = ["methods_server", "methods_ui", "sources_methods_server", "sources_methods_ui"]
