"""Created: 2026-04-13

Purpose: Runs the MailMind agent from the command line.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.mailmind import MailMindAgent, MailMindEmailClassifier
from src.interfaces.whatsapp import MockWhatsAppInterface, TwilioWhatsAppInterface, WhatsAppInterface
from src.llm import LLMFactory
from src.sources import GmailEmailSender, GmailEmailSource
from src.storage.duckdb_store import DuckDBMessageRepository
from src.utils.config import AppSettings

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")


def load_mailmind_config(config_path: Path) -> dict[str, object]:
    """Loads the merged MailMind runtime config from YAML."""
    if not config_path.exists():
        return {}
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"MailMind config file {config_path} must contain a mapping at the top level.")
    return payload


def build_arg_parser(defaults: dict[str, object]) -> argparse.ArgumentParser:
    """Builds the CLI for running MailMind from a terminal."""
    parser = argparse.ArgumentParser(description="Run the MailMind agent.")
    parser.add_argument(
        "message",
        nargs="?",
        default=defaults.get("message"),
        help="User message for a single-turn run.",
    )
    parser.add_argument(
        "--config",
        default=str(defaults.get("config_path", DEFAULT_CONFIG_PATH)),
        help="Path to the merged MailMind config file.",
    )
    parser.add_argument(
        "--session-id",
        default=defaults.get("session_id"),
        help="Conversation session id.",
    )
    parser.add_argument(
        "--entry-mode",
        default=str(defaults.get("entry_mode", "cli")),
        choices=["cli", "webhook"],
        help="Run MailMind as a CLI session or WhatsApp webhook server.",
    )
    parser.add_argument(
        "--trigger-type",
        default=str(defaults.get("trigger_type", "query")),
        choices=["query", "approval", "poll", "maintenance"],
        help="Turn trigger type for the MailMind graph.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        default=bool(defaults.get("interactive", False)),
        help="Start a simple interactive loop instead of running a single message.",
    )
    parser.add_argument(
        "--webhook-host",
        default=str(defaults.get("webhook_host", "127.0.0.1")),
        help="Host for the WhatsApp webhook server.",
    )
    parser.add_argument(
        "--webhook-port",
        type=int,
        default=int(defaults.get("webhook_port", 8000)),
        help="Port for the WhatsApp webhook server.",
    )
    return parser


def load_settings(config_path: str) -> AppSettings:
    """Loads app settings using the provided config path."""
    os.environ.setdefault("EASY_AGENT_CONFIG_PATH", config_path)
    return AppSettings.from_env()


def build_llm(settings: AppSettings):
    """Builds the configured LLM adapter for MailMind."""
    provider = settings.llm.provider.strip().lower()
    if provider == "huggingface":
        return LLMFactory.build_default_local_llm(
            model_name=settings.llm.model_name,
            device_map=settings.llm.device_map,
            torch_dtype=settings.llm.torch_dtype,
            max_new_tokens=settings.llm.max_new_tokens,
            enable_thinking=settings.llm.enable_thinking,
        )
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when llm.provider=openai.")
        return LLMFactory.build_openai_llm(
            model_name=settings.llm.model_name,
            api_key=api_key,
            max_new_tokens=settings.llm.max_new_tokens,
        )
    if provider == "nvidia":
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            raise ValueError("NVIDIA_API_KEY is required when llm.provider=nvidia.")
        base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com")
        return LLMFactory.build_nvidia_llm(
            model_name=settings.llm.model_name,
            api_key=api_key,
            base_url=base_url,
            max_new_tokens=settings.llm.max_new_tokens,
        )
    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is required when llm.provider=groq.")
        return LLMFactory.build_groq_llm(
            model_name=settings.llm.model_name,
            api_key=api_key,
            max_new_tokens=settings.llm.max_new_tokens,
        )
    if provider == "endpoint":
        endpoint_url = os.getenv("EASY_AGENT_LLM_ENDPOINT_URL")
        if not endpoint_url:
            raise ValueError("EASY_AGENT_LLM_ENDPOINT_URL is required when llm.provider=endpoint.")
        return LLMFactory.build_endpoint_llm(
            endpoint_url=endpoint_url,
            model_name=settings.llm.model_name,
            api_key=os.getenv("EASY_AGENT_LLM_API_KEY"),
            max_new_tokens=settings.llm.max_new_tokens,
        )
    if provider == "openai_compatible":
        base_url = os.getenv("EASY_AGENT_LLM_BASE_URL")
        if not base_url:
            raise ValueError("EASY_AGENT_LLM_BASE_URL is required when llm.provider=openai_compatible.")
        return LLMFactory.build_openai_compatible_llm(
            base_url=base_url,
            model_name=settings.llm.model_name,
            api_key=os.getenv("EASY_AGENT_LLM_API_KEY"),
            max_new_tokens=settings.llm.max_new_tokens,
        )
    raise ValueError(f"Unsupported llm.provider: {settings.llm.provider}")


def build_whatsapp_interface(settings: AppSettings) -> WhatsAppInterface:
    """Builds the configured WhatsApp interface."""
    if settings.notifications.whatsapp_mode == "fake":
        return MockWhatsAppInterface()
    return TwilioWhatsAppInterface(
        account_sid=settings.integrations.twilio_account_sid,
        auth_token=settings.integrations.twilio_auth_token,
        whatsapp_from=settings.integrations.twilio_whatsapp_from,
    )


def _gmail_credentials_path() -> Path | None:
    """Returns an optional Gmail credentials path if present."""
    env_path = os.getenv("EASY_AGENT_GMAIL_CREDENTIALS_PATH")
    if env_path:
        return Path(env_path)
    default = Path("data/gmail_credentials.json")
    return default if default.exists() else None


def _gmail_token_path() -> Path:
    """Returns the Gmail token path."""
    env_path = os.getenv("EASY_AGENT_GMAIL_TOKEN_PATH")
    if env_path:
        return Path(env_path)
    return Path("data/gmail_token.json")


def build_optional_gmail_source(settings: AppSettings) -> GmailEmailSource | None:
    """Builds the Gmail source when the runtime is configured for Gmail."""
    if settings.runtime.source_mode.strip().lower() != "gmail":
        return None
    return GmailEmailSource(
        credentials_path=_gmail_credentials_path(),
        token_path=_gmail_token_path(),
        client_id=settings.integrations.gmail_client_id or None,
        client_secret=settings.integrations.gmail_client_secret or None,
    )


def build_optional_gmail_sender(settings: AppSettings) -> GmailEmailSender | None:
    """Builds the Gmail sender when Gmail credentials are available."""
    token_path = _gmail_token_path()
    credentials_path = _gmail_credentials_path()
    if not token_path.exists() and credentials_path is None and not settings.integrations.gmail_client_id:
        return None
    return GmailEmailSender(
        credentials_path=credentials_path,
        token_path=token_path,
        client_id=settings.integrations.gmail_client_id or None,
        client_secret=settings.integrations.gmail_client_secret or None,
    )


def build_agent(settings: AppSettings) -> tuple[MailMindAgent, WhatsAppInterface]:
    """Builds the MailMind agent and its channel adapter from settings."""
    repository = DuckDBMessageRepository(settings.paths.db_path)
    repository.init_db()
    llm = build_llm(settings)
    whatsapp = build_whatsapp_interface(settings)
    source = build_optional_gmail_source(settings)
    sender = build_optional_gmail_sender(settings)
    classifier = MailMindEmailClassifier(llm=llm)
    agent = MailMindAgent(
        llm=llm,
        repository=repository,
        whatsapp=whatsapp,
        source=source,
        sender=sender,
        classifier=classifier,
    )
    return agent, whatsapp


def run_single_turn(agent: MailMindAgent, *, user_input: str, session_id: str, trigger_type: str, whatsapp: WhatsAppInterface) -> None:
    """Runs one MailMind turn and prints the response."""
    response = agent.run(user_input, session_id=session_id, trigger_type=trigger_type)
    print(response)
    if isinstance(whatsapp, MockWhatsAppInterface) and whatsapp.outbound_messages:
        print("\n[mock_whatsapp]")
        print(whatsapp.outbound_messages[-1][1])


def run_interactive(agent: MailMindAgent, *, session_id: str, trigger_type: str, whatsapp: WhatsAppInterface) -> None:
    """Runs a basic interactive terminal loop for MailMind."""
    print("MailMind interactive mode. Type 'exit' to stop.")
    while True:
        try:
            user_input = input("> ").strip()
        except EOFError:
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break
        run_single_turn(
            agent,
            user_input=user_input,
            session_id=session_id,
            trigger_type=trigger_type,
            whatsapp=whatsapp,
        )


def run_webhook_server(agent: MailMindAgent, *, host: str, port: int) -> None:
    """Runs the FastAPI WhatsApp webhook app backed by the MailMind agent."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is required to run MailMind in webhook mode.") from exc

    try:
        from endpoints.whatsapp import create_app
    except ImportError as exc:
        raise RuntimeError(
            "Webhook mode requires FastAPI endpoint dependencies. Install the web stack to use endpoints.whatsapp."
        ) from exc

    app = create_app(agent=agent)
    uvicorn.run(app, host=host, port=port)


def main() -> int:
    """CLI entrypoint for running MailMind."""
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    bootstrap_args, _ = bootstrap.parse_known_args()
    config_path = Path(bootstrap_args.config)
    merged_config = load_mailmind_config(config_path)
    merged_config["config_path"] = str(config_path)

    parser = build_arg_parser(merged_config)
    args = parser.parse_args()
    settings = load_settings(args.config)
    agent, whatsapp = build_agent(settings)
    session_id = args.session_id or settings.notifications.notification_destination or "mailmind-cli"

    if args.entry_mode == "webhook":
        run_webhook_server(agent, host=args.webhook_host, port=args.webhook_port)
        return 0

    if args.interactive or not args.message:
        run_interactive(agent, session_id=session_id, trigger_type=args.trigger_type, whatsapp=whatsapp)
        return 0

    run_single_turn(
        agent,
        user_input=args.message,
        session_id=session_id,
        trigger_type=args.trigger_type,
        whatsapp=whatsapp,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
