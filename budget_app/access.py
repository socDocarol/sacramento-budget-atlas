from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AccessContext:
    subject: str
    display_name: str
    authenticated: bool
    groups: tuple[str, ...] = ()


class AccessContextProvider(Protocol):
    def current(self) -> AccessContext: ...


class NetworkAccessContextProvider:
    """V1 access context. It intentionally ignores all forwarded identity headers."""

    def current(self) -> AccessContext:
        return AccessContext(
            subject="network-user",
            display_name="City network user",
            authenticated=False,
        )
