"""Created: 2026-03-30

Purpose: Implements the container module for the shared mailmind platform layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory import (
    ColdMemoryLayer,
    HotMemoryLayer,
    MemoryIndexer,
    MemoryPolicy,
    MemoryRetriever,
    MemoryRouter,
    MemoryService,
    MemoryStore,
    SleepingMemoryQueue,
    WarmMemoryLayer,
)
from src.llm.function_gemma import FunctionGemmaLLM
from src.llm.qwen import Qwen3_1_7BLLM
from src.mailmind.agent.react_agent import ReActAgent
from src.mailmind.agents.function_planner import FunctionCallingToolPlanner
from src.mailmind.agents.llm_planner import OptionalLLMToolPlanner
from src.mailmind.agents.planner import RuleBasedToolPlanner
from src.mailmind.interface.whatsapp import MockWhatsAppInterface
from src.mailmind.approvals.queue import LocalApprovalQueue
from src.mailmind.classifiers.llm import OptionalLLMClassifierAdapter
from src.mailmind.classifiers.rules import RulesBasedClassifier
from src.mailmind.config import AppSettings
from src.mailmind.core.orchestrator import MailOrchestrator
from src.mailmind.core.policies import YAMLPolicyProvider
from src.mailmind.drafters.simple import SimpleReplyDrafter
from src.mailmind.logs.jsonl import JSONLAuditLogStore
from src.mailmind.notifiers.whatsapp import FakeWhatsAppNotifier, WhatsAppNotifier
from src.mailmind.sources.gmail import FakeGmailEmailSource, GmailEmailSource
from src.mailmind.storage.repository import DuckDBMessageRepository
from src.tools.gmail.draft_reply import DraftReplyTool
from src.tools.gmail.email_classifier import EmailClassifierTool
from src.tools.gmail.email_search import EmailSearchTool
from src.tools.gmail.email_summary import EmailSummaryTool
from src.tools.executor import ToolExecutor
from src.tools.gmail.gmail_fetch import GmailFetchTool
from src.tools.memory_search import MemorySearchTool
from src.tools.memory_write import MemoryWriteTool
from src.tools.gmail.notification import NotificationTool
from src.tools.registry import ToolRegistry
from src.tools.catalog import write_tool_catalog


@dataclass(slots=True)
class AppContainer:
    settings: AppSettings
    policy_provider: YAMLPolicyProvider
    repository: DuckDBMessageRepository
    audit_log: JSONLAuditLogStore
    source: object
    orchestrator: MailOrchestrator
    memory_store: MemoryStore
    memory_retriever: object
    memory_service: MemoryService
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
        repository = DuckDBMessageRepository(settings.db_path)
        audit_log = JSONLAuditLogStore(settings.log_path)
        hot_layer = HotMemoryLayer(max_items=settings.memory.hot_cache_size)
        warm_layer = WarmMemoryLayer(settings.db_path, settings.memory_tables_path)
        cold_layer = ColdMemoryLayer(settings.memory_cold_path)
        memory_policy = MemoryPolicy(settings.memory_policies_path)
        local_memory_store = MemoryStore(
            hot_layer=hot_layer,
            warm_layer=warm_layer,
            cold_layer=cold_layer,
            indexer=MemoryIndexer(warm_layer=warm_layer),
            archive_after_days=memory_policy.archive_after_days("agent_local"),
            default_scope="agent_local",
            agent_id="mailmind",
        )
        global_memory_store = MemoryStore(
            hot_layer=HotMemoryLayer(max_items=max(32, settings.memory.hot_cache_size // 2)),
            warm_layer=warm_layer,
            cold_layer=cold_layer,
            indexer=MemoryIndexer(warm_layer=warm_layer),
            archive_after_days=memory_policy.archive_after_days("global"),
            default_scope="global",
            agent_id=None,
        )
        local_memory_retriever = MemoryRetriever(store=local_memory_store)
        global_memory_retriever = MemoryRetriever(store=global_memory_store)
        memory_router = MemoryRouter(
            local_retriever=local_memory_retriever,
            global_retriever=global_memory_retriever,
            escalation_step_count=settings.memory.escalation_step_count,
            confidence_threshold=settings.memory.confidence_threshold,
        )
        memory_service = MemoryService(
            local_store=local_memory_store,
            global_store=global_memory_store,
            router=memory_router,
        )
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
            memory_store=local_memory_store,
            memory_policy=memory_policy,
        )
        tool_registry = ToolRegistry()
        tool_registry.register(GmailFetchTool(source=source, orchestrator=orchestrator))
        tool_registry.register(EmailSearchTool(repository=repository))
        tool_registry.register(EmailClassifierTool(repository=repository, classifier=classifier))
        tool_registry.register(DraftReplyTool(repository=repository, drafter=drafter))
        tool_registry.register(NotificationTool(orchestrator=orchestrator))
        tool_registry.register(EmailSummaryTool(repository=repository))
        tool_registry.register(MemorySearchTool(retriever=memory_router))
        tool_registry.register(MemoryWriteTool(store=local_memory_store))
        tool_catalog = write_tool_catalog(tool_registry.list_tools(), settings.tool_catalog_path)
        tool_executor = ToolExecutor(
            registry=tool_registry,
            repository=repository,
            memory_store=local_memory_store,
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
            memory_retriever=memory_router,
            memory_store=local_memory_store,
        )
        whatsapp_interface = MockWhatsAppInterface()
        return cls(
            settings=settings,
            policy_provider=policy_provider,
            repository=repository,
            audit_log=audit_log,
            source=source,
            orchestrator=orchestrator,
            memory_store=local_memory_store,
            memory_retriever=memory_router,
            memory_service=memory_service,
            sleeping_queue=sleeping_queue,
            tool_registry=tool_registry,
            tool_executor=tool_executor,
            planner=planner,
            agent=agent,
            whatsapp_interface=whatsapp_interface,
        )
