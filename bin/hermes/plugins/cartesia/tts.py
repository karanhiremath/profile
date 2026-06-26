"""Cartesia text-to-speech provider (Sonic models).

Routes ``text_to_speech`` tool calls when ``tts.provider: cartesia``. The
dispatcher (``tools.tts_tool._dispatch_to_plugin_provider``) reads
``tts.voice`` / ``tts.model`` / ``tts.speed`` / ``tts.output_format`` from
config.yaml and passes them here; anything omitted falls back to env defaults
(``CARTESIA_VOICE_ID`` / ``CARTESIA_TTS_MODEL``) then to provider defaults.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from agent.tts_provider import TTSProvider

from ._common import auth_headers, base_url, get_env

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "sonic-3.5"  # latest stable (rolling); override via tts.model / CARTESIA_TTS_MODEL
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_BIT_RATE = 128000
HTTP_TIMEOUT = 60.0


def _output_format(fmt: str, sample_rate: int) -> Dict[str, Any]:
    """Map a Hermes format token to a Cartesia ``output_format`` object.

    Cartesia containers are mp3 / wav / raw. mp3 and wav are produced
    natively; ogg/opus/flac aren't Cartesia containers, so we emit mp3 and
    let the gateway's ffmpeg voice-bubble pass re-encode if needed.
    """
    f = (fmt or "mp3").lower()
    if f == "wav":
        return {
            "container": "wav",
            "encoding": "pcm_s16le",
            "sample_rate": sample_rate,
        }
    return {
        "container": "mp3",
        "sample_rate": sample_rate,
        "bit_rate": DEFAULT_BIT_RATE,
    }


class CartesiaTTSProvider(TTSProvider):
    @property
    def name(self) -> str:
        return "cartesia"

    @property
    def display_name(self) -> str:
        return "Cartesia"

    def is_available(self) -> bool:
        return bool(get_env("CARTESIA_API_KEY"))

    @property
    def voice_compatible(self) -> bool:
        # mp3/wav output re-encodes cleanly to Opus for voice bubbles.
        return True

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Cartesia",
            "badge": "paid",
            "tag": "Sonic — ultra-low-latency TTS",
            "env_vars": [
                {
                    "key": "CARTESIA_API_KEY",
                    "prompt": "Cartesia API key",
                    "url": "https://play.cartesia.ai/console",
                },
            ],
        }

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"id": "sonic-3.5", "display": "Sonic 3.5 (latest)"},
            {"id": "sonic-3", "display": "Sonic 3"},
            {"id": "sonic-latest", "display": "Sonic (rolling latest alias)"},
        ]

    def default_model(self) -> Optional[str]:
        return get_env("CARTESIA_TTS_MODEL") or DEFAULT_MODEL

    def list_voices(self) -> List[Dict[str, Any]]:
        """Best-effort voice catalog via GET /voices. Empty on any error."""
        try:
            headers = auth_headers()
        except Exception:
            return []
        out: List[Dict[str, Any]] = []
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT) as client:
                resp = client.get(
                    f"{base_url()}/voices",
                    headers=headers,
                    params={"limit": 100},
                )
                resp.raise_for_status()
                payload = resp.json()
            rows = payload.get("data", payload) if isinstance(payload, dict) else payload
            for v in rows or []:
                if not isinstance(v, dict) or not v.get("id"):
                    continue
                out.append(
                    {
                        "id": v["id"],
                        "display": v.get("name") or v["id"],
                        "language": v.get("language"),
                    }
                )
        except Exception as exc:  # noqa: BLE001 — catalog is advisory
            logger.debug("Cartesia list_voices failed: %s", exc)
        return out

    def default_voice(self) -> Optional[str]:
        env_voice = get_env("CARTESIA_VOICE_ID")
        if env_voice:
            return env_voice
        voices = self.list_voices()
        return voices[0]["id"] if voices else None

    def synthesize(
        self,
        text: str,
        output_path: str,
        *,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        format: str = "mp3",
        **extra: Any,
    ) -> str:
        if not get_env("CARTESIA_API_KEY"):
            raise RuntimeError(
                "CARTESIA_API_KEY is not set. Add it to ~/.hermes/.env "
                "(get a key at https://play.cartesia.ai/console)."
            )
        voice_id = voice or self.default_voice()
        if not voice_id:
            raise RuntimeError(
                "No Cartesia voice configured. Set tts.voice in config.yaml "
                "or CARTESIA_VOICE_ID in ~/.hermes/.env (list ids with the "
                "Cartesia console / GET /voices)."
            )
        model_id = model or self.default_model()
        try:
            sample_rate = int(get_env("CARTESIA_SAMPLE_RATE") or DEFAULT_SAMPLE_RATE)
        except ValueError:
            sample_rate = DEFAULT_SAMPLE_RATE

        body: Dict[str, Any] = {
            "model_id": model_id,
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "output_format": _output_format(format, sample_rate),
        }
        language = get_env("CARTESIA_LANGUAGE")
        if language:
            body["language"] = language
        if isinstance(speed, (int, float)):
            # Cartesia generation_config.speed is clamped to [0.6, 1.5].
            body["generation_config"] = {"speed": max(0.6, min(1.5, float(speed)))}

        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.post(
                f"{base_url()}/tts/bytes",
                headers={**auth_headers(), "Content-Type": "application/json"},
                json=body,
            )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Cartesia TTS HTTP {resp.status_code}: {resp.text[:500]}"
                )
            audio = resp.content

        if not audio:
            raise RuntimeError("Cartesia TTS returned empty audio.")
        with open(output_path, "wb") as fh:
            fh.write(audio)
        return output_path
