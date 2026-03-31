"""Created: 2026-03-30

Purpose: Implements the container module for the shared mailmind platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from memory import (
    ColdMemoryLayer,
    HotMemoryLayer,
    MemoryIndexer,
    MemoryPolicy,
    MemoryRetriever,
    MemoryStore,
    SleepingMemoryQueue,
    WarmMemoryLayer,
)
from llm.function_gemma import FunctionGemmaLLM
from llm.qwen import Qwen3_1_7BLLM
from mailmind.agent.react_agent import ReActAgent
from mailmind.agents.function_planner import FunctionCallingToolPlanner
from mailmind.agents.llm_planner import OptionalLLMToolPlanner
from mailmind.agents.planner import RuleBasedToolPlanner
from mailmind.interface.whatsapp import MockWhatsAppInterface
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
from tools.draft_reply import DraftReplyTool
from tools.email_classifier import EmailClassifierTool
from tools.email_search import EmailSearchTool
from tools.email_summary import EmailSummaryTool
from tools.executor import ToolExecutor
from tools.gmail_fetch import GmailFetchTool
from tools.memory_search import MemorySearchTool
from tools.memory_write import MemoryWriteTool
from tools.notification import NotificationTool
from tools.registry import ToolRegistry
from tools.catalog import write_tool_catalog


@dataclass(slots=True)
class AppContainer:
    settings: AppSettings
    policy_provider: YAMLPolicyProvider
    repository: SQLiteMessageRepository
    audit_log: JSONLAuditLogStore
    source: object
    orchestrator: MailOrchestrator
    memory_store: MemoryStore
    memory_retriever: MemoryRetriever
    sleeping_queue: SleepingMemoryQueue
    tool_registry: ToolRegistry
    tool_executor: ToolExecutor
    planner: RuleBasedToolPlanner | OptionalLLMToolPlanner | FunctionCallingToolPlanner
    agent: ReActAgent
    whatsapp_interface: MockWhatsAppInterface

    @classmethod
    def from_env(cls) -> "AppContainer":
        settings = AppSettings.from_env()
        policy_provider = YAMLPolicyProvider(settings.policy_path)
        repository = SQLiteMessageRepository(settings.db_path)
        audit_log = JSONLAuditLogStore(settings.log_path)
        hot_layer = HotMemoryLayer(max_items=settings.memory.hot_cache_size)
        warm_layer = WarmMemoryLayer(settings.db_path)
        cold_layer = ColdMemoryLayer(settings.memory_cold_path)
        memory_store = MemoryStore(
            hot_layer=hot_layer,
            warm_layer=warm_layer,
            cold_layer=cold_layer,
            indexer=MemoryIndexer(warm_layer=warm_layer),
            archive_after_days=settings.memory.archive_after_days,
        )
        memory_retriever = MemoryRetriever(store=memory_store)
        memory_policy = MemoryPolicy()
        sleeping_queue = SleepingMemoryQueue(settings.sleeping_tasks_path)
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
            memory_store=memory_store,
            memory_policy=memory_policy,
        )
        tool_registry = ToolRegistry()
        tool_registry.register(GmailFetchTool(source=source, orchestrator=orchestrator))
        tool_registry.register(EmailSearchTool(repository=repository))
        tool_registry.register(EmailClassifierTool(repository=repository, classifier=classifier))
        tool_registry.register(DraftReplyTool(repository=repository, drafter=drafter))
        tool_registry.register(NotificationTool(orchestrator=orchestrator))
        tool_registry.register(EmailSummaryTool(repository=repository))
        tool_registry.register(MemorySearchTool(retriever=memory_retriever))
        tool_registry.register(MemoryWriteTool(store=memory_store))
        tool_catalog = write_tool_catalog(tool_registry.list_tools(), settings.tool_catalog_path)
        tool_executor = ToolExecutor(
            registry=tool_registry,
            repository=repository,
            memory_store=memory_store,
            memory_policy=memory_policy,
        )
        rule_planner = RuleBasedToolPlanner()
        planner_llm = None
        if settings.planner.enabled and settings.planner.provider == "function_gemma":
            planner_llm = FunctionGemmaLLM(
                model_name=settings.planner.model_name,
                device_map=settings.planner.device_map,
                torch_dtype=settings.planner.torch_dtype,
                max_new_tokens=settings.planner.max_new_tokens,
            )
        planner = (
            FunctionCallingToolPlanner(
                fallback=rule_planner,
                llm=planner_llm,
                tool_catalog=tool_catalog,
                enabled=settings.planner.enabled,
            )
            if settings.planner.provider == "function_gemma"
            else OptionalLLMToolPlanner(fallback=rule_planner, llm=llm, enabled=settings.llm_enabled)
        )
        agent = ReActAgent(
            planner=planner,
            executor=tool_executor,
            repository=repository,
            memory_retriever=memory_retriever,
        )
        whatsapp_interface = MockWhatsAppInterface()
        return cls(
            settings=settings,
            policy_provider=policy_provider,
            repository=repository,
            audit_log=audit_log,
            source=source,
            orchestrator=orchestrator,
            memory_store=memory_store,
            memory_retriever=memory_retriever,
            sleeping_queue=sleeping_queue,
            tool_registry=tool_registry,
            tool_executor=tool_executor,
            planner=planner,
            agent=agent,
            whatsapp_interface=whatsapp_interface,
        )
