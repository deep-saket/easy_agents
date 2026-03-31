"""Created: 2026-03-31

Purpose: Tests the whatsapp interface behavior.
"""

from mailmind.interface.whatsapp import MockWhatsAppInterface


def test_mock_whatsapp_interface_captures_outbound_messages() -> None:
    interface = MockWhatsAppInterface()
    interface.send_message("session-1", "Hello from agent")
    assert interface.outbound_messages == [("session-1", "Hello from agent")]
