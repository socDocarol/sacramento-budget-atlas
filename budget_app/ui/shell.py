"""City of Sacramento branded application shell for Shiny Core."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from shiny import ui

CITY_SOURCE_URL = (
    "https://services5.arcgis.com/54falWtcpty3V47Z/arcgis/rest/services/"
    "City_of_Sacramento_Approved_Budgets/FeatureServer/0"
)

PRIMARY_NAVIGATION: tuple[tuple[str, str, str], ...] = (
    ("overview", "Overview", "Overview of approved revenue and expenses"),
    ("changed", "What Changed", "Compare fiscal years and movements"),
    ("explorer", "Explorer", "Filter and inspect supporting records"),
    ("lab", "Lab", "Exploratory scenario and statistical review tools"),
)

RESOURCE_NAVIGATION: tuple[tuple[str, str, str], ...] = (
    ("budget101", "Budget 101", "Plain-language guide to the budget"),
    ("methods", "Sources & Methods", "Data source, checks, and limitations"),
)

# Compatibility for callers that enumerate shell destinations, without exposing
# the retired drilldown route in the public navigation.
NAVIGATION = PRIMARY_NAVIGATION + RESOURCE_NAVIGATION


def city_head_ui() -> Any:
    """Head tags for the internal pilot, including the no-index contract."""
    return ui.tags.head(
        ui.tags.meta(name="robots", content="noindex, nofollow"),
        ui.tags.meta(name="description", content="Internal Sacramento approved budget data story."),
        ui.tags.link(rel="stylesheet", href="city.css"),
        ui.tags.script(src="app.js"),
    )


def _nav_href(name: str) -> str:
    return f"#{name}"


def city_header_ui(
    *,
    active: str = "overview",
    latest_year: str | None = None,
    nav_input_id: str = "app_view",
) -> Any:
    """Render only the header. The integration layer owns the one ``main`` landmark."""
    valid_navigation = {key for key, _, _ in PRIMARY_NAVIGATION + RESOURCE_NAVIGATION}
    selected = active if active in valid_navigation else "overview"
    desktop_links = [
        ui.a(
            label,
            href=_nav_href(key),
            aria_current="page" if selected == key else None,
            data_nav_value=key,
            data_nav_input=nav_input_id,
            class_=f"city-nav__link{' is-active' if selected == key else ''}",
        )
        for key, label, _ in PRIMARY_NAVIGATION
    ]
    desktop_resource_links = [
        ui.a(
            label,
            href=_nav_href(key),
            aria_current="page" if selected == key else None,
            data_nav_value=key,
            data_nav_input=nav_input_id,
            class_=f"city-resources__link{' is-active' if selected == key else ''}",
        )
        for key, label, _ in RESOURCE_NAVIGATION
    ]
    mobile_primary_links = [
        ui.a(
            label,
            href=_nav_href(key),
            aria_current="page" if selected == key else None,
            data_nav_value=key,
            data_nav_input=nav_input_id,
            class_=f"city-mobile-nav__link{' is-active' if selected == key else ''}",
            data_menu_link="true",
        )
        for key, label, _ in PRIMARY_NAVIGATION
    ]
    mobile_resource_links = [
        ui.a(
            label,
            href=_nav_href(key),
            aria_current="page" if selected == key else None,
            data_nav_value=key,
            data_nav_input=nav_input_id,
            class_=f"city-mobile-nav__link{' is-active' if selected == key else ''}",
            data_menu_link="true",
        )
        for key, label, _ in RESOURCE_NAVIGATION
    ]
    return ui.tags.header(
        ui.a(
            "Skip to content",
            href="#main",
            class_="skip-link",
        ),
        ui.div(
            ui.a(
                ui.tags.span("↖", aria_hidden="true", class_="portal-link__icon"),
                ui.tags.span("Portal", class_="portal-link__label"),
                href="/",
                aria_label="Return to portal",
                class_="portal-link",
            ),
            ui.div(
                ui.a(
                    ui.tags.img(
                        src="assets/footer-icon.png",
                        width="210",
                        height="51",
                        alt="City of Sacramento",
                        class_="city-brand-logo",
                    ),
                    ui.tags.span("", aria_hidden="true", class_="city-brand-separator"),
                    ui.tags.span("Budget Dashboard", class_="city-app-identity"),
                    href="/",
                    aria_label="City of Sacramento Budget Dashboard home",
                    class_="city-brand-link",
                ),
                ui.tags.nav(
                    *desktop_links,
                    ui.tags.details(
                        ui.tags.summary("Resources", class_="city-resources__summary"),
                        ui.tags.nav(
                            *desktop_resource_links,
                            aria_label="Budget resources",
                            class_="city-resources__menu",
                        ),
                        class_="city-resources",
                    ),
                    aria_label="Budget story sections",
                    class_="city-nav",
                ),
                ui.tags.details(
                    ui.tags.summary(
                        ui.tags.span("☰", aria_hidden="true"),
                        ui.tags.span("Open page menu", class_="sr-only"),
                        class_="city-mobile-nav__summary",
                    ),
                    ui.tags.nav(
                        *mobile_primary_links,
                        ui.tags.div("Resources", class_="city-mobile-nav__label"),
                        *mobile_resource_links,
                        aria_label="Budget story sections",
                        class_="city-mobile-nav",
                    ),
                    class_="city-mobile-nav__details",
                ),
                class_="city-header__main",
            ),
            class_="city-header__inner",
        ),
        class_="city-header",
    )


def city_footer_ui(*, snapshot_label: str | None = None, source_url: str = CITY_SOURCE_URL) -> Any:
    snapshot = snapshot_label or date.today().strftime("%B %d, %Y")
    return ui.tags.footer(
        ui.div(
            ui.div(
                ui.tags.img(
                    src="assets/footer-icon.png",
                    width="210",
                    height="51",
                    alt="City of Sacramento",
                    class_="city-footer-logo",
                ),
                class_="city-footer__logo-panel",
            ),
            ui.p(
                "Independent visualisation of the City of Sacramento's public ",
                ui.a("Approved Budgets dataset", href=source_url, target="_blank", rel="noreferrer"),
                " on the ArcGIS Open Data portal. See the ",
                ui.a(
                    "methodology",
                    href="#methods",
                    data_nav_value="methods",
                    data_nav_input="app_view",
                ),
                " for aggregation notes.",
                class_="city-footer__source",
            ),
            ui.div(
                ui.span(f"DATA SNAPSHOT · {snapshot}"),
                ui.span("REFRESHED EVERY 24 HOURS"),
                class_="city-footer__meta",
            ),
            class_="city-container city-container--wide city-footer__inner",
        ),
        class_="city-footer",
    )


def city_shell_ui(
    content: Any,
    *,
    active: str = "overview",
    latest_year: str | None = None,
    nav_input_id: str = "app_view",
) -> Any:
    """Convenience chrome wrapper.

    ``content`` is expected to be a ``main`` tag owned by the caller. This helper
    does not create a second main landmark.
    """
    return ui.div(
        city_header_ui(active=active, latest_year=latest_year, nav_input_id=nav_input_id),
        content,
        city_footer_ui(),
        class_="city-app",
    )


def page_section(
    *children: Any,
    section_id: str,
    tone: str = "default",
    width: str = "wide",
    class_: str = "",
) -> Any:
    from .components import page_container

    return ui.tags.section(
        page_container(
            ui.div(*children, class_="city-page-flow"),
            width=width,
        ),
        id=f"view-{section_id}",
        data_view_section=section_id,
        class_=f"city-section city-section--{tone} {class_}".strip(),
    )


def page_intro(title: str, lede: str, *, eyebrow_text: str = "Approved budget") -> Any:
    from .components import eyebrow

    return ui.div(
        eyebrow(eyebrow_text),
        ui.h1(title, class_="city-page-title"),
        ui.p(lede, class_="city-page-lede"),
        class_="city-page-intro",
    )


def on_this_page(items: Iterable[tuple[str, str]]) -> Any:
    links = [ui.a(label, href=f"#{section_id}") for section_id, label in items]
    return ui.tags.details(
        ui.tags.summary("On this page: Overview", class_="city-outline__summary"),
        ui.nav(*links, aria_label="On this page", class_="city-outline__links"),
        class_="city-outline city-outline--mobile",
    )
