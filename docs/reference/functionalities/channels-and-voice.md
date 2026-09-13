# Channels, Sources, and Voice

Status: local contracts verified; live external integrations unverified.

## WhatsApp

`WhatsAppInterface` defines outbound sending and inbound parsing. Implementations:

- `MockWhatsAppInterface` captures messages in memory for tests and local development.
- `TwilioWhatsAppInterface` sends through a Twilio client and parses Twilio webhook payloads.
- `WhatsAppAgentBridge` forwards an inbound message to an agent's `run()` method.
- `WhatsAppNode` sends graph state through either adapter and can mark the graph as waiting.

Use mock mode first:

```python
from src.interfaces.whatsapp import MockWhatsAppInterface

channel = MockWhatsAppInterface()
channel.send_message("session-1", "Hello")
assert channel.outbound_messages[-1] == ("session-1", "Hello")
```

Twilio mode is an external side effect. It requires `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `EASY_AGENT_TWILIO_WHATSAPP_FROM`.

## Gmail

`GmailEmailSource` normalizes Gmail API messages into the framework email schema. `GmailEmailSender` sends replies. MailMind tools then fetch, classify, search, summarize, draft, approve, notify, and send through injected protocols.

The local tests use fake Gmail services, sources, senders, and notifiers with temporary DuckDB databases. No real mailbox was read or changed.

Real Gmail usage requires the `gmail` optional dependencies, OAuth client configuration, token storage, and explicit authorization:

```bash
python -m pip install -e ".[gmail]"
```

## API and CLI Interfaces

The repository contains lightweight shared CLI/API interfaces plus concrete FastAPI endpoints for WhatsApp and the Graph Builder. Concrete agents provide their own entrypoints rather than one platform-wide CLI.

## Pipecat Runtime

`PipecatRunnerConfig` parses transport and media settings. The runtime fails fast with `PipecatNotInstalledError` when optional dependencies are absent. Collection Agent integrates Pipecat for browser WebRTC, Daily, and telephony-oriented paths.

Install only when needed:

```bash
python -m pip install -e ".[voice-realtime]"
```

## Local Voice Processing

The `voice_processing` package includes:

- audio loading and segmentation
- speech-to-text chunking
- speaker embeddings
- speaker clustering
- word-to-speaker alignment
- optional known-user voice matching

Collection voice configuration can select local Whisper STT and SpeechT5 TTS or NVIDIA backends. Local models may require downloads and substantial compute.

## Verification

Twenty-one focused tests passed for WhatsApp endpoints/adapters/nodes, Pipecat configuration and missing-dependency behavior, SpeechT5 configuration, backend selection/fallback, speaker alignment, clustering, embeddings, and a fake-backed processing pipeline.

Gmail normalization and six email tool workflows also passed with fakes and temporary storage.

## Live Checks Not Performed

- Twilio message or call delivery
- Gmail OAuth fetch/send
- NVIDIA STT/TTS
- live WebRTC, Daily, or telephony media
- real microphone/speaker playback
- large speech/model downloads

Use non-production accounts and explicit approval when running these checks.
