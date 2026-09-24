"""Created: 2026-09-24

Purpose: Composes canonical Wormhole routing with the working Fleet and Gemma runtime.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from threading import RLock
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from easy_agents.fleet.model_profiles import MAC_GEMMA_PROFILE_ID
from easy_agents.fleet.models import GalaxyRoutePlan, MissionRequest
from easy_agents.fleet.runtime import FleetRuntime
from easy_agents.galaxy.enums import EntityKind
from easy_agents.galaxy.identity import Identifier
from easy_agents.galaxy.missions import Mission, Trajectory
from easy_agents.galaxy.registry import GalaxyRegistry
from easy_agents.galaxy.routing import Wormhole


class ChatEntity(BaseModel):
    """Small canonical entity summary rendered in the chat trajectory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Identifier
    display_name: str = Field(min_length=1, max_length=160)


class ChatTurn(BaseModel):
    """One bounded user or Galaxy message retained in local process memory."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class WormholeChatRequest(BaseModel):
    """User message submitted to the Galaxy through the Wormhole."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    message: str = Field(min_length=3, max_length=12_000)
    conversation_id: Identifier | None = None
    reset_conversation: bool = False


class ChatRouteContext(BaseModel):
    """Explains routed and supporting entities without changing route semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    galaxy: ChatEntity
    circles: tuple[ChatEntity, ...]
    planets: tuple[ChatEntity, ...]
    constellations: tuple[ChatEntity, ...] = ()
    available_satellites: tuple[ChatEntity, ...] = ()
    invoked_satellites: tuple[ChatEntity, ...] = ()
    rogue_stars: tuple[ChatEntity, ...] = ()


class WormholeChatResponse(BaseModel):
    """Answer plus canonical trajectory and supporting operational context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: Identifier
    message_id: Identifier
    mission_id: Identifier
    status: str
    answer: str
    trajectory: Trajectory
    route_context: ChatRouteContext
    visualization_route: GalaxyRoutePlan
    used_model: str | None = None
    warnings: tuple[str, ...] = ()
    retained_turns: int = Field(ge=2)


class ConversationStore:
    """Thread-safe bounded in-memory conversation history for the local UI.

    The store is intentionally ephemeral: restarting the Control Room clears
    chat history. Durable personal memory must flow through explicit Vaults,
    retention policy, and deletion/export controls rather than this UI cache.
    """

    def __init__(self, *, max_conversations: int = 128, max_turns: int = 20) -> None:
        """Creates a bounded store with least-recently-used conversation eviction."""

        if max_conversations < 1 or max_turns < 2:
            raise ValueError("Conversation limits must be positive and retain two turns.")
        self.max_conversations = max_conversations
        self.max_turns = max_turns
        self._histories: OrderedDict[str, deque[ChatTurn]] = OrderedDict()
        self._lock = RLock()

    def read(self, conversation_id: str) -> tuple[ChatTurn, ...]:
        """Returns a snapshot and marks the conversation as recently used."""

        with self._lock:
            history = self._histories.get(conversation_id)
            if history is None:
                return ()
            self._histories.move_to_end(conversation_id)
            return tuple(history)

    def append(self, conversation_id: str, *turns: ChatTurn) -> tuple[ChatTurn, ...]:
        """Appends turns and evicts old turns and conversations deterministically."""

        with self._lock:
            history = self._histories.setdefault(
                conversation_id,
                deque(maxlen=self.max_turns),
            )
            history.extend(turns)
            self._histories.move_to_end(conversation_id)
            while len(self._histories) > self.max_conversations:
                self._histories.popitem(last=False)
            return tuple(history)

    def clear(self, conversation_id: str) -> None:
        """Removes one conversation if it exists."""

        with self._lock:
            self._histories.pop(conversation_id, None)


class WormholeChatService:
    """Routes a chat message and executes the selected Planet through Gemma.

    The canonical route remains ``Wormhole → Galaxy → Circle → Planet``.
    Constellations are reported as connected overlays containing the selected
    entities. Satellites are reported as tools available to the Planet; only a
    future tool-execution result may put a Satellite in ``invoked_satellites``.
    """

    def __init__(
        self,
        *,
        registry: GalaxyRegistry,
        fleet_runtime: FleetRuntime,
        history: ConversationStore | None = None,
    ) -> None:
        """Composes canonical routing, Fleet execution, and local chat history."""

        self.registry = registry
        self.fleet_runtime = fleet_runtime
        self.wormhole = Wormhole(registry)
        self.history = history or ConversationStore()

    def chat(self, request: WormholeChatRequest) -> WormholeChatResponse:
        """Routes and answers one user message with bounded prior-turn context."""

        conversation_id = request.conversation_id or f"chat-{uuid4().hex}"
        if request.reset_conversation:
            self.history.clear(conversation_id)
        prior_turns = self.history.read(conversation_id)
        mission = Mission(objective=request.message, team_size=1)
        trajectory = self.wormhole.route(mission)
        planet_id = trajectory.planet_ids[0]
        recent_history = self._format_history(prior_turns)
        fleet_result = self.fleet_runtime.run(
            MissionRequest(
                objective=request.message,
                specialist_id=planet_id,
                requested_effects=["read"],
                allow_network=False,
                team_size=1,
                model_id=MAC_GEMMA_PROFILE_ID,
                advisory_only=True,
                context={"recent_conversation": recent_history}
                if recent_history
                else {},
            )
        )
        trajectory = trajectory.model_copy(
            update={"mission_id": fleet_result.mission_id}
        )
        specialist_name = fleet_result.results[0].specialist_name
        answer = self._clean_answer(
            fleet_result.synthesis,
            specialist_name=specialist_name,
            objective=request.message,
        )
        if not answer:
            raise ValueError("The routed Planet returned an empty answer.")
        retained = self.history.append(
            conversation_id,
            ChatTurn(role="user", content=request.message),
            ChatTurn(role="assistant", content=answer),
        )
        used_model = next(
            (item.used_model for item in fleet_result.results if item.used_model),
            None,
        )
        return WormholeChatResponse(
            conversation_id=conversation_id,
            message_id=f"message-{uuid4().hex}",
            mission_id=fleet_result.mission_id,
            status=fleet_result.status.value,
            answer=answer,
            trajectory=trajectory,
            route_context=self._route_context(trajectory),
            visualization_route=fleet_result.routing,
            used_model=used_model,
            warnings=tuple(fleet_result.warnings),
            retained_turns=len(retained),
        )

    def _route_context(self, trajectory: Trajectory) -> ChatRouteContext:
        """Builds display context for route, overlays, tools, and external models."""

        galaxy = self.registry.get_galaxy(trajectory.galaxy_id)
        circles = tuple(
            ChatEntity(id=item, display_name=self.registry.get_circle(item).display_name)
            for item in trajectory.circle_ids
        )
        planets = tuple(
            ChatEntity(id=item, display_name=self.registry.get_planet(item).display_name)
            for item in trajectory.planet_ids
        )
        selected_circles = set(trajectory.circle_ids)
        selected_planets = set(trajectory.planet_ids)
        constellations = tuple(
            ChatEntity(id=item.id, display_name=item.display_name)
            for item in self.registry.constellations.values()
            if selected_circles.intersection(item.circle_ids)
            and any(
                node.kind is EntityKind.PLANET and node.id in selected_planets
                for node in item.nodes
            )
        )
        satellite_ids = {
            satellite_id
            for planet_id in trajectory.planet_ids
            for satellite_id in self.registry.get_planet(planet_id).charter.satellite_ids
        }
        satellites = tuple(
            ChatEntity(
                id=item,
                display_name=self.registry.satellites[item].display_name,
            )
            for item in sorted(satellite_ids)
            if item in self.registry.satellites
        )
        model_ids = {
            model_id
            for planet_id in trajectory.planet_ids
            for model_id in self.registry.get_planet(planet_id).charter.model_ids
        }
        rogue_stars = tuple(
            ChatEntity(id=item, display_name=self.registry.rogue_stars[item].display_name)
            for item in sorted(model_ids)
            if item in self.registry.rogue_stars
        )
        return ChatRouteContext(
            galaxy=ChatEntity(id=galaxy.id, display_name=galaxy.display_name),
            circles=circles,
            planets=planets,
            constellations=constellations,
            available_satellites=satellites,
            invoked_satellites=(),
            rogue_stars=rogue_stars,
        )

    @staticmethod
    def _format_history(turns: tuple[ChatTurn, ...]) -> str:
        """Formats the newest bounded turns for the completion prompt."""

        lines = [f"{turn.role.title()}: {turn.content}" for turn in turns[-8:]]
        return "\n".join(lines)[-8_000:]

    @staticmethod
    def _clean_answer(value: str, *, specialist_name: str, objective: str) -> str:
        """Removes the continuation prefix and truncates base-model repetition."""

        prefix = f'{specialist_name} assessment of the Mission "{objective}": '
        answer = value.removeprefix(prefix).strip()
        if prefix in answer:
            answer = answer.split(prefix, 1)[0].strip()
        return answer
