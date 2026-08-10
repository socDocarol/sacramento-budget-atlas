from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPLAINER = ROOT / "docs" / "azure-deployment-explainer.html"
REQUIRED_SECTIONS = {
    "identity-overview",
    "two-lanes",
    "oidc",
    "setup-vs-release",
    "measure-u-comparison",
    "approval-map",
    "deploy-walkthrough",
    "next-request",
}


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    luminances = sorted((_relative_luminance(first), _relative_luminance(second)))
    return (luminances[1] + 0.05) / (luminances[0] + 0.05)


class ExplainerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.section_ids: set[str] = set()
        self.evidence_kinds: set[str] = set()
        self.deploy_steps: list[str] = []
        self.tags: list[str] = []
        self.external_references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        values = dict(attrs)
        if tag == "section" and values.get("id"):
            self.section_ids.add(values["id"])
        if values.get("data-evidence"):
            self.evidence_kinds.add(values["data-evidence"])
        if values.get("data-deploy-step"):
            self.deploy_steps.append(values["data-deploy-step"])
        for name in ("href", "src"):
            value = values.get(name, "") or ""
            if value.startswith(("http://", "https://", "//")):
                self.external_references.append(value)


def _page() -> tuple[str, ExplainerParser]:
    html = EXPLAINER.read_text(encoding="utf-8")
    parser = ExplainerParser()
    parser.feed(html)
    return html, parser


def test_explainer_has_every_required_section_and_deployment_step() -> None:
    html, parser = _page()

    assert REQUIRED_SECTIONS <= parser.section_ids  # noqa: SIM300
    assert parser.deploy_steps == [str(step) for step in range(1, 9)]
    assert parser.evidence_kinds == {"direct", "recommended", "inference"}
    assert "People use Microsoft Entra to enter the app" in html
    assert "No reusable Azure password is saved in GitHub" in html
    assert "the exact Measure U workflow YAML was not available" in html


def test_explainer_is_offline_semantic_and_javascript_free() -> None:
    html, parser = _page()

    assert '<html lang="en">' in html
    assert "main" in parser.tags
    assert "nav" in parser.tags
    assert "details" in parser.tags
    assert "table" in parser.tags
    assert "script" not in parser.tags
    assert parser.external_references == []
    assert "@media (max-width: 720px)" in html
    assert "@media print" in html
    assert ":focus-visible" in html


def test_focus_outline_has_three_to_one_contrast_against_adjacent_surfaces() -> None:
    html, _ = _page()
    custom_properties = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", html))
    focus_rule = re.search(
        r"a:focus-visible,\s*summary:focus-visible\s*\{[^}]*outline:[^;]*var\((--[\w-]+)\)",
        html,
        re.DOTALL,
    )

    assert focus_rule is not None
    focus_color = custom_properties[focus_rule.group(1)]
    adjacent_surfaces = {
        "navigation": "#ffffff",
        "details": custom_properties["--panel"],
    }
    for surface, background in adjacent_surfaces.items():
        assert _contrast_ratio(focus_color, background) >= 3, surface


def test_explainer_contains_no_identifiers_secrets_or_unresolved_markers() -> None:
    html, _ = _page()

    forbidden_literals = {
        "AZURE_CLIENT_ID",
        "AZURE_TENANT_ID",
        "AZURE_SUBSCRIPTION_ID",
        "client-secret",
        "PLACE" + "HOLDER",
        "T" + "BD",
        "TO" + "DO",
        chr(0x2014),
    }
    assert forbidden_literals.isdisjoint(html)
    assert (
        re.search(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
            html,
        )
        is None
    )
