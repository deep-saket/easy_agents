"""Created: 2026-09-24

Purpose: Models shared external Rogue Stars and bounded Galaxy access Orbits.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from easy_agents.galaxy.enums import ResourceKind
from easy_agents.galaxy.identity import GalaxyId, RogueStarId


class RogueStar(BaseModel):
    """Describes an external resource owned by no Galaxy.

    A Rogue Star may be a model, API, data service, or other dependency shared
    by several Galaxies. Merely registering it grants no access; each Galaxy
    needs a separate :class:`AccessOrbit` evaluated by policy.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: RogueStarId
    display_name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4_000)
    resource_kind: ResourceKind
    endpoint: AnyHttpUrl
    model_name: str | None = Field(default=None, max_length=256)
    tags: tuple[str, ...] = ()
    legacy_ids: tuple[str, ...] = ()


class AccessOrbit(BaseModel):
    """Grants one Galaxy bounded access to one external Rogue Star.

    The Orbit is an authorization record, never an ownership edge. ``allows``
    performs deterministic host, effect, and network checks before a caller
    contacts the resource.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    galaxy_id: GalaxyId
    rogue_star_id: RogueStarId
    allowed_effects: tuple[str, ...] = ("inference",)
    allowed_hosts: tuple[str, ...] = ()
    allow_network: bool = False
    requires_approval: bool = False

    @model_validator(mode="after")
    def validate_policy(self) -> "AccessOrbit":
        """Rejects duplicate and unsafe access-policy declarations."""

        if len(self.allowed_effects) != len(set(self.allowed_effects)):
            raise ValueError("AccessOrbit contains duplicate allowed effects.")
        normalized_hosts = tuple(item.lower() for item in self.allowed_hosts)
        if len(normalized_hosts) != len(set(normalized_hosts)):
            raise ValueError("AccessOrbit contains duplicate allowed hosts.")
        if self.allow_network and not self.allowed_hosts:
            raise ValueError("Network-enabled AccessOrbit requires an explicit host allowlist.")
        return self

    def allows(self, *, endpoint: str, effect: str, approved: bool = False) -> bool:
        """Checks whether this Orbit authorizes one external operation.

        Args:
            endpoint: Fully qualified HTTP(S) endpoint about to be contacted.
            effect: Requested external effect, such as ``inference``.
            approved: Whether the required human approval has been verified.

        Returns:
            ``True`` only when effect, host, network policy, and approval pass.
        """

        if effect not in self.allowed_effects:
            return False
        if self.requires_approval and not approved:
            return False
        parsed = urlparse(endpoint)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            return False
        if host not in {item.lower() for item in self.allowed_hosts}:
            return False
        if self.allow_network:
            return True
        return _is_loopback(host)


def _is_loopback(host: str) -> bool:
    """Returns whether a hostname is an explicit loopback address."""

    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
