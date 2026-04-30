from __future__ import annotations

from src.tools.base import BaseTool

from agents.connections_agent.tools.case_fetch_tool import CaseFetchTool
from agents.connections_agent.tools.case_prioritize_tool import CasePrioritizeTool
from agents.connections_agent.tools.contact_attempt_tool import ContactAttemptTool
from agents.connections_agent.tools.customer_verify_tool import CustomerVerifyTool
from agents.connections_agent.tools.data_store import ConnectionsDataStore
from agents.connections_agent.tools.disposition_update_tool import DispositionUpdateTool
from agents.connections_agent.tools.dues_explain_build_tool import DuesExplainBuildTool
from agents.connections_agent.tools.followup_schedule_tool import FollowupScheduleTool
from agents.connections_agent.tools.human_escalation_tool import HumanEscalationTool
from agents.connections_agent.tools.loan_policy_lookup_tool import LoanPolicyLookupTool
from agents.connections_agent.tools.offer_eligibility_tool import OfferEligibilityTool
from agents.connections_agent.tools.payment_link_create_tool import PaymentLinkCreateTool
from agents.connections_agent.tools.payment_status_check_tool import PaymentStatusCheckTool
from agents.connections_agent.tools.promise_capture_tool import PromiseCaptureTool


def build_offline_toolset(store: ConnectionsDataStore) -> list[BaseTool]:
    return [
        CaseFetchTool(store=store),
        CasePrioritizeTool(store=store),
        ContactAttemptTool(store=store),
        CustomerVerifyTool(store=store),
        LoanPolicyLookupTool(store=store),
        DuesExplainBuildTool(store=store),
        OfferEligibilityTool(store=store),
        PaymentLinkCreateTool(store=store),
        PaymentStatusCheckTool(store=store),
        PromiseCaptureTool(store=store),
        FollowupScheduleTool(store=store),
        DispositionUpdateTool(store=store),
        HumanEscalationTool(store=store),
    ]
