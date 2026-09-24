"""Created: 2026-09-24

Purpose: Defines stable discriminators used by the canonical Galaxy domain.
"""

from __future__ import annotations

from enum import Enum


class EntityKind(str, Enum):
    """Identifies the canonical kind represented by an :class:`EntityRef`.

    The values are persisted in version-2 snapshots. They therefore change only
    through a versioned migration, never as a display-label cleanup.
    """

    GALAXY = "galaxy"
    CIRCLE = "circle"
    PLANET = "planet"
    COMPONENT = "component"
    SATELLITE = "satellite"
    CONSTELLATION = "constellation"
    ROGUE_STAR = "rogue_star"
    WORMHOLE = "wormhole"


class MemberKind(str, Enum):
    """Distinguishes agent members from non-agent members of a Circle."""

    PLANET = "planet"
    COMPONENT = "component"


class PlanetClass(str, Enum):
    """Defines the only supported Planet specializations."""

    ROCKY = "rocky"
    GIANT = "giant"


class LifecycleStatus(str, Enum):
    """Represents the reviewed lifecycle of a Planet or Component."""

    PROPOSED = "proposed"
    SCAFFOLDED = "scaffolded"
    SANDBOXED = "sandboxed"
    EVALUATED = "evaluated"
    APPROVED = "approved"
    ACTIVE = "active"
    QUARANTINED = "quarantined"
    RETIRED = "retired"


class ComponentKind(str, Enum):
    """Classifies non-agent Circle Members by their responsibility."""

    CAPABILITY = "capability"
    SATELLITE = "satellite"
    VAULT = "vault"
    PLAYBOOK = "playbook"
    GATE = "gate"
    MODEL = "model"
    SERVICE = "service"


class ResourceKind(str, Enum):
    """Classifies a Rogue Star without implying Galaxy ownership."""

    MODEL = "model"
    SERVICE = "service"
    API = "api"
    DATA = "data"


class OrbitKind(str, Enum):
    """Defines canonical directed relationships between domain entities."""

    CONTAINS = "contains"
    MEMBER_OF = "member_of"
    CAN_USE = "can_use"
    READS = "reads"
    WRITES = "writes"
    GOVERNS = "governs"
    DELEGATES_TO = "delegates_to"
    ACCESSES_EXTERNAL = "accesses_external"
    CONNECTS = "connects"


class MissionStatus(str, Enum):
    """Represents the lifecycle of a canonical Mission."""

    CREATED = "created"
    ROUTED = "routed"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
