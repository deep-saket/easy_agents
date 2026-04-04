"""Created: 2026-04-03

Purpose: Tests the shared WhatsApp graph node behavior.
"""

from src.nodes.whatsapp_node import WhatsAppNode
from src.interfaces.whatsapp import MockWhatsAppInterface
from src.memory import WorkingMemory


def test_whatsapp_node_sends_response_text() -> None:
    interface = MockWhatsAppInterface()
    node = WhatsAppNode(interface=interface)

    update = node.execute({
        "session_id": "whatsapp:+919999999999",
        "user_input": "hello",
        "response": "Hi there",
    })

    assert interface.outbound_messages == [("whatsapp:+919999999999", "Hi there")]
    assert update["channel_result"]["message"] == "Hi there"
    assert update["channel_result"]["send_result"]["provider"] == "mock"
    assert update["channel_result"]["send_result"]["status"] == "captured"
    assert update["waiting"] is False
    assert update["route"] == "continue"


def test_whatsapp_node_can_pause_for_reply() -> None:
    interface = MockWhatsAppInterface()
    memory = WorkingMemory(session_id="whatsapp:+919999999999")
    node = WhatsAppNode(interface=interface, wait_for_reply=True)

    update = node.execute({
        "memory": memory,
        "user_input": "approve this?",
        "response": "Reply YES or NO",
    })

    assert interface.outbound_messages == [("whatsapp:+919999999999", "Reply YES or NO")]
    assert update["channel_result"]["send_result"]["provider"] == "mock"
    assert update["waiting"] is True
    assert update["final"] is True
    assert node.route(update) == "wait"
    assert memory.state["awaiting_whatsapp_reply"] is True
