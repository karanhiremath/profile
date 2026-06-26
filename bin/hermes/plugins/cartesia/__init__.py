"""Cartesia backend plugin: registers Sonic TTS + Ink STT providers.

Enable per Hermes plugin gating (``plugins.enabled``), then select in
config.yaml:

    tts:
      provider: cartesia
      voice: <cartesia-voice-id>     # or set CARTESIA_VOICE_ID in ~/.hermes/.env
      model: sonic-3.5               # optional; defaults to latest (sonic-3.5)
    stt:
      enabled: true
      provider: cartesia
      cartesia:
        model: ink-2                 # optional; defaults to latest (ink-2)
        language: en                 # optional

Requires CARTESIA_API_KEY in ~/.hermes/.env.

Endpoint (prod / staging / on-prem / in-cluster) is switched via
CARTESIA_BASE_URL — the same env var the bifrost stack uses
(default https://api.cartesia.ai). Same paths and key auth across
environments. Internal hostnames belong in ~/.hermes/.env, never in this
source (data boundary). See validate.py for an end-to-end endpoint check.
"""

from __future__ import annotations

from .stt import CartesiaTranscriptionProvider
from .tts import CartesiaTTSProvider


def register(ctx) -> None:
    ctx.register_tts_provider(CartesiaTTSProvider())
    ctx.register_transcription_provider(CartesiaTranscriptionProvider())
