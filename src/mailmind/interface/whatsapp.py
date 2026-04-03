"""Created: 2026-04-03

Purpose: Re-exports the shared WhatsApp interface for MailMind compatibility.
"""

from src.interfaces.whatsapp import IncomingMessage, MockWhatsAppInterface, TwilioWhatsAppInterface, WhatsAppInterface

__all__ = [
    "IncomingMessage",
    "MockWhatsAppInterface",
    "TwilioWhatsAppInterface",
    "WhatsAppInterface",
]
