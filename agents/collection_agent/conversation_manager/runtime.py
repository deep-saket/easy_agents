"""Runtime wrapper that places ConversationManagerAgent around CollectionDebugRuntime."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.collection_agent.conversation_manager.ConversationManagerAgent import ConversationManagerAgent
from agents.collection_agent.conversation_manager.ConversationManagerConfig import ConversationManagerConfig


@dataclass(slots=True)
class VoiceProcessState:
    """Tracks active conversation-manager Pipecat metadata."""

    process: subprocess.Popen[Any]
    user_code: str
    session_id: str
    transport: str
    port: int
    client_url: str
    log_path: str
    started_at: float
    log_handle: Any


class ConversationManagerVoiceProcessManager:
    """Starts/stops the conversation-manager Pipecat bot."""

    def __init__(self, *, repo_root: Path, base_dir: Path) -> None:
        self._repo_root = repo_root
        self._base_dir = base_dir
        self._lock = threading.Lock()
        self._state: VoiceProcessState | None = None
        self._log_dir = self._base_dir / "runtime" / "voice"
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def start(
        self,
        *,
        user_code: str,
        session_id: str,
        greeting: str,
        port: int = 8788,
        transport: str = "webrtc",
    ) -> dict[str, Any]:
        with self._lock:
            self._stop_locked(force=True)
            safe_session = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in session_id)
            log_path = self._log_dir / f"conversation_manager_pipecat_{safe_session}.log"
            log_handle = log_path.open("a", encoding="utf-8")

            env = os.environ.copy()
            env["COLLECTION_VOICE_SESSION_ID"] = session_id
            env["COLLECTION_VOICE_USER_CODE"] = user_code
            env["COLLECTION_VOICE_GREETING"] = greeting
            cmd = [
                sys.executable,
                "-m",
                "agents.collection_agent.conversation_manager.pipecat_bot",
                "-t",
                transport,
                "--port",
                str(port),
            ]
            process = subprocess.Popen(
                cmd,
                cwd=str(self._repo_root),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            client_url = f"http://127.0.0.1:{port}/client/"
            self._state = VoiceProcessState(
                process=process,
                user_code=user_code,
                session_id=session_id,
                transport=transport,
                port=port,
                client_url=client_url,
                log_path=str(log_path),
                started_at=time.time(),
                log_handle=log_handle,
            )
            return self._status_payload_locked()

    def stop(self, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            self._stop_locked(force=force)
            return self._status_payload_locked()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_payload_locked()

    def _stop_locked(self, *, force: bool) -> None:
        state = self._state
        if state is None:
            return
        process = state.process
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3.0 if force else 8.0)
            except Exception:
                process.kill()
                process.wait(timeout=3.0)
        try:
            state.log_handle.close()
        except Exception:
            pass
        self._state = None

    def _status_payload_locked(self) -> dict[str, Any]:
        state = self._state
        if state is None:
            return {
                "active": False,
                "session_id": None,
                "user_code": None,
                "transport": None,
                "port": None,
                "client_url": None,
                "log_path": None,
                "pid": None,
            }
        running = state.process.poll() is None
        return {
            "active": running,
            "session_id": state.session_id,
            "user_code": state.user_code,
            "transport": state.transport,
            "port": state.port,
            "client_url": state.client_url,
            "log_path": state.log_path,
            "pid": state.process.pid,
            "started_at": state.started_at,
            "exit_code": state.process.poll(),
        }


class ConversationManagedRuntime:
    """Wraps CollectionDebugRuntime and adds filler/latency behavior externally."""

    def __init__(
        self,
        *,
        base_dir: Path,
        collection_base_dir: Path,
        downstream_runtime: CollectionDebugRuntime,
        manager: ConversationManagerAgent,
        voice_manager: ConversationManagerVoiceProcessManager,
    ) -> None:
        self.base_dir = base_dir
        self.collection_base_dir = collection_base_dir
        self.downstream_runtime = downstream_runtime
        self.manager = manager
        self.voice_manager = voice_manager

    @classmethod
    def create(
        cls,
        base_dir: Path | None = None,
        *,
        collection_base_dir: Path | None = None,
        config: ConversationManagerConfig | None = None,
    ) -> "ConversationManagedRuntime":
        wrapper_dir = Path(__file__).resolve().parent
        resolved_base_dir = (base_dir or wrapper_dir).resolve()
        if not (resolved_base_dir / "filler_library.json").exists():
            resolved_base_dir = wrapper_dir.resolve()
        resolved_collection_base_dir = (collection_base_dir or Path(__file__).resolve().parents[1]).resolve()
        from agents.collection_agent.ui.server import CollectionDebugRuntime

        downstream_runtime = CollectionDebugRuntime.create(resolved_collection_base_dir)
        config = config or ConversationManagerConfig.default(base_dir=resolved_base_dir)
        manager = ConversationManagerAgent(config=config, downstream_runtime=downstream_runtime)
        repo_root = Path(__file__).resolve().parents[3]
        voice_manager = ConversationManagerVoiceProcessManager(repo_root=repo_root, base_dir=resolved_base_dir)
        return cls(
            base_dir=resolved_base_dir,
            collection_base_dir=resolved_collection_base_dir,
            downstream_runtime=downstream_runtime,
            manager=manager,
            voice_manager=voice_manager,
        )

    def start_conversation(self, request: Any) -> Any:
        return self.manager.start_conversation(request)

    def reset_conversation(self, request: Any) -> Any:
        return self.manager.reset_conversation(request)

    def run_turn(self, request: Any, *, event_callback: Any | None = None) -> Any:
        return self.manager.run_turn(request, event_callback=event_callback)

    def run_turn_stream(self, request: Any) -> Any:
        return self.manager.run_turn_stream(request)

    def session_state(self, session_id: str) -> Any:
        return self.manager.session_state(session_id)

    def list_demo_users(self) -> Any:
        return self.manager.list_demo_users()

    def conversation_messages(self, session_id: str, *, limit: int = 120) -> Any:
        return self.manager.conversation_messages(session_id, limit=limit)

    def latest_trace_for_session(self, session_id: str) -> Any:
        return self.manager.latest_trace_for_session(session_id)

    def start_voice_call(self, request: Any) -> dict[str, Any]:
        from agents.collection_agent.ui.server import StartConversationRequest

        user_code = request.user_code.strip().lower()
        matched = next((item for item in self.list_demo_users() if item.get("user_code") == user_code), None)
        if matched is None:
            raise ValueError(f"Unknown user_code={user_code}. Use one of: user_a, user_b, user_c")
        requested_session = request.session_id.strip() if isinstance(request.session_id, str) else ""
        session_id = requested_session or f"collection-{user_code}"

        start_payload = self.start_conversation(
            StartConversationRequest(
                user_code=user_code,
                session_id=session_id,
                soft_cap=request.soft_cap,
                hard_cap=request.hard_cap,
            )
        )
        opener = str(((start_payload.get("turn") or {}).get("final_response")) or "").strip()
        greeting = opener or "Hello. This is Alex from the collections team. How can I help you today?"
        voice = self.voice_manager.start(
            user_code=user_code,
            session_id=session_id,
            greeting=greeting,
            port=int(request.port),
            transport=str(request.transport).strip().lower() or "webrtc",
        )
        return {
            "session_id": session_id,
            "user": matched,
            "turn": start_payload.get("turn"),
            "voice": voice,
        }

    def stop_voice_call(self, *, force: bool = False) -> dict[str, Any]:
        return self.voice_manager.stop(force=force)

    def voice_status(self) -> dict[str, Any]:
        return self.voice_manager.status()
