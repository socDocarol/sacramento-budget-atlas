"""Story Studio opening composition for the Sacramento budget experience.

The opening is intentionally a normal document section. It introduces the
dataset, gives users an immediate way into the live overview, and leaves the
existing Shiny navigation and analysis modules authoritative below it.
"""

from __future__ import annotations

from typing import Any

from shiny import ui

CITY_HALL_IMAGE = "assets/atlas/historic-city-hall.jpg"
COUNCIL_IMAGE = "assets/atlas/council-chambers.jpg"


def _jump_link(label: str, href: str, *, detail: str) -> Any:
    nav_value = href.removeprefix("#view-")
    return ui.a(
        ui.span(label, class_="city-story-studio__jump-label"),
        ui.span(detail, class_="city-story-studio__jump-detail"),
        ui.span("→", aria_hidden="true", class_="city-story-studio__jump-arrow"),
        href=href,
        data_nav_value=nav_value,
        data_nav_input="app_view",
        class_="city-story-studio__jump-link",
    )


def story_studio_ui(
    *,
    analysis_slot: Any | None = None,
) -> Any:
    """Build the visible opening section that precedes the live overview.

    Snapshot facts are server-rendered from the active validated bundle. The
    opening never substitutes reference-snapshot values while data is missing.
    """

    live_slot = analysis_slot or ui.p(
        "The prepared budget snapshot will appear here when the live analysis is ready.",
        class_="city-story-studio__live-empty",
    )
    return ui.tags.section(
        ui.div(
            ui.div(
                ui.div("Approved Budget Context", class_="city-story-studio__eyebrow"),
                ui.h1(
                    "Sacramento Budget Dashboard",
                    class_="city-story-studio__title",
                ),
                ui.p(
                    ui.output_text("story_lede", inline=True),
                    class_="city-story-studio__lede",
                ),
                ui.div(
                    ui.div(
                        ui.output_text("story_authority_label", inline=True),
                        class_="city-story-studio__value-label",
                    ),
                    ui.div(
                        ui.output_text("story_authority_value", inline=True),
                        class_="city-story-studio__value tabular",
                    ),
                    ui.div(
                        ui.output_text("story_snapshot_note", inline=True),
                        class_="city-story-studio__value-note",
                    ),
                    class_="city-story-studio__value-block",
                ),
                ui.tags.figure(
                    ui.tags.img(
                        src=CITY_HALL_IMAGE,
                        width="1080",
                        height="720",
                        loading="eager",
                        decoding="async",
                        alt="Exterior of Sacramento Historic City Hall framed by trees and blue sky",
                        class_="city-story-studio__hero-image",
                    ),
                    ui.tags.figcaption(
                        "Sacramento Historic City Hall, an architectural landmark in the city center.",
                        class_="city-story-studio__caption",
                    ),
                    class_="city-story-studio__hero-figure",
                ),
                class_="city-story-studio__narrative",
            ),
            ui.div(
                ui.div(
                    ui.div("Citywide context", class_="city-story-studio__live-eyebrow"),
                    ui.div(
                        ui.span(
                            ui.output_text("story_live_year", inline=True),
                            class_="city-story-studio__live-year",
                        ),
                        ui.span("Approved authority", class_="city-story-studio__live-meaning"),
                        class_="city-story-studio__live-meta",
                    ),
                    class_="city-story-studio__live-head",
                ),
                live_slot,
                class_="city-story-studio__live",
            ),
            class_="city-story-studio__stage",
        ),
        ui.div(
            ui.div(
                ui.div("Related views", class_="city-story-studio__jump-eyebrow"),
                ui.tags.nav(
                    _jump_link("Overview", "#view-overview", detail="Citywide totals and movements"),
                    _jump_link("What changed", "#view-changed", detail="Fiscal-year movements"),
                    _jump_link("Explorer", "#view-explorer", detail="Exact supporting records"),
                    aria_label="Related budget views",
                    class_="city-story-studio__jump-list",
                ),
                class_="city-story-studio__jump-panel",
            ),
            ui.tags.figure(
                ui.tags.img(
                    src=COUNCIL_IMAGE,
                    width="1200",
                    height="800",
                    loading="lazy",
                    decoding="async",
                    alt="Sacramento City Council chambers with the dais and projection screens",
                    class_="city-story-studio__secondary-image",
                ),
                ui.tags.figcaption(
                    "Sacramento City Council chambers, where public decisions are considered.",
                    class_="city-story-studio__caption",
                ),
                class_="city-story-studio__secondary-figure",
            ),
            class_="city-story-studio__support",
        ),
        id="story-studio",
        data_story_studio="opening",
        class_="city-story-studio",
        aria_label="Approved Budget Context opening",
    )


__all__ = ["story_studio_ui"]
