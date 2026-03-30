from __future__ import annotations

from dataclasses import dataclass

from mailmind.LLM.qwen import Qwen3_1_7BLLM
from mailmind.agents.agent import Agent
from mailmind.agents.llm_planner import OptionalLLMToolPlanner
from mailmind.agents.planner import RuleBasedToolPlanner
from mailmind.approvals.queue import LocalApprovalQueue
from mailmind.classifiers.llm import OptionalLLMClassifierAdapter
from mailmind.classifiers.rules import RulesBasedClassifier
from mailmind.config import AppSettings
from mailmind.core.orchestrator import MailOrchestrator
from mailmind.core.policies import YAMLPolicyProvider
from mailmind.drafters.simple import SimpleReplyDrafter
from mailmind.logs.jsonl import JSONLAuditLogStore
from mailmind.notifiers.whatsapp import FakeWhatsAppNotifier, WhatsAppNotifier
from mailmind.sources.gmail import FakeGmailEmailSource, GmailEmailSource
from mailmind.storage.repository import SQLiteMessageRepository
from mailmind.tools.draft_reply import DraftReplyTool
from mailmind.tools.email_classifier import EmailClassifierTool
from mailmind.tools.email_search import EmailSearchTool
from mailmind.tools.email_summary import EmailSummaryTool
from mailmind.tools.executor import ToolExecutor
from mailmind.tools.gmail_fetch import GmailFetchTool
from mailmind.tools.notification import NotificationTool
from mailmind.tools.registry import ToolRegistry


@dataclass(slots=True)
class AppContainer:
    settings: AppSettings
    policy_provider: YAMLPolicyProvider
    repository: SQLiteMessageRepository
    audit_log: JSONLAuditLogStore
    source: object
    orchestrator: MailOrchestrator
    tool_registry: ToolRegistry
    tool_executor: ToolExecutor
    planner: RuleBasedToolPlanner | OptionalLLMToolPlanner
    agent: Agent

    @classmethod
    def from_env(cls) -> "AppContainer":
        settings = AppSettings.from_env()
        policy_provider = YAMLPolicyProvider(settings.policy_path)
        repository = SQLiteMessageRepository(settings.db_path)
        audit_log = JSONLAuditLogStore(settings.log_path)
        llm = None
        if settings.llm_enabled and settings.llm.provider == "huggingface":
            llm = Qwen3_1_7BLLM(
                model_name=settings.llm.model_name,
                device_map=settings.llm.device_map,
                torch_dtype=settings.llm.torch_dtype,
                max_new_tokens=settings.llm.max_new_tokens,
                enable_thinking=settings.llm.enable_thinking,
            )
        classifier = OptionalLLMClassifierAdapter(
            fallback=RulesBasedClassifier(policy_provider=policy_provider),
            llm=llm,
            enabled=settings.llm_enabled,
        )
        drafter = SimpleReplyDrafter()
        notifier = (
            FakeWhatsAppNotifier(settings.whatsapp_allowlist)
            if settings.whatsapp_mode == "fake"
            else WhatsAppNotifier(settings.whatsapp_allowlist)
        )
        approval_queue = LocalApprovalQueue(repository=repository)
        source = FakeGmailEmailSource(settings.gmail_seed_path) if settings.source_mode == "fake" else GmailEmailSource()
        orchestrator = MailOrchestrator(
            repository=repository,
            classifier=classifier,
            drafter=drafter,
            notifier=notifier,
            approval_queue=approval_queue,
            audit_log=audit_log,
            notification_destination=settings.notification_destination,
        )
        tool_registry = ToolRegistry()
        tool_registry.register(GmailFetchTool(source=source, orchestrator=orchestrator))
        tool_registry.register(EmailSearchTool(repository=repository))
        tool_registry.register(EmailClassifierTool(repository=repository, classifier=classifier))
        tool_registry.register(DraftReplyTool(repository=repository, drafter=drafter))
        tool_registry.register(NotificationTool(orchestrator=orchestrator))
        tool_registry.register(EmailSummaryTool(repository=repository))
        tool_executor = ToolExecutor(registry=tool_registry, repository=repository)
        rule_planner = RuleBasedToolPlanner()
        planner = OptionalLLMToolPlanner(fallback=rule_planner, llm=llm, enabled=settings.llm_enabled)
        agent = Agent(planner=planner, executor=tool_executor)
        return cls(
            settings=settings,
            policy_provider=policy_provider,
            repository=repository,
            audit_log=audit_log,
            source=source,
            orchestrator=orchestrator,
            tool_registry=tool_registry,
            tool_executor=tool_executor,
            planner=planner,
            agent=agent,
        )
