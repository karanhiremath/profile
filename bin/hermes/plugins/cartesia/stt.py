"""Cartesia speech-to-text provider (Ink / ink-whisper).

Routes ``transcribe_audio`` calls when ``stt.provider: cartesia``. The
dispatcher passes ``model`` (from ``stt.cartesia.model``) and ``language``
(from ``stt.cartesia.language`` / ``stt.language``); both fall back to
provider defaults. Returns the standard ``{success, transcript, provider}``
envelope and never raises (per the TranscriptionProvider contract).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from agent.transcription_provider import TranscriptionProvider

from ._common import auth_headers, get_env, stt_base_url

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "ink-2"  # latest; override via stt.cartesia.model / CARTESIA_STT_MODEL
DEFAULT_LANGUAGE = "en"
HTTP_TIMEOUT = 300.0


class CartesiaTranscriptionProvider(TranscriptionProvider):
    @property
    def name(self) -> str:
        return "cartesia"

    @property
    def display_name(self) -> str:
        return "Cartesia"

    def is_available(self) -> bool:
        return bool(get_env("CARTESIA_API_KEY"))

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Cartesia",
            "badge": "paid",
            "tag": "Ink — streaming STT (ink-whisper)",
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
            {"id": "ink-2", "display": "Ink 2 (latest)"},
            {"id": "ink-whisper", "display": "Ink Whisper"},
        ]

    def default_model(self) -> Optional[str]:
        return get_env("CARTESIA_STT_MODEL") or DEFAULT_MODEL

    def transcribe(
        self,
        file_path: str,
        *,
        model: Optional[str] = None,
        language: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        if not os.path.isfile(file_path):
            return {
                "success": False,
                "transcript": "",
                "error": f"audio file not found: {file_path}",
                "provider": self.name,
            }

        model_id = model or self.default_model()
        lang = language or get_env("CARTESIA_LANGUAGE") or DEFAULT_LANGUAGE
        data = {"model": model_id, "language": lang}

        try:
            with open(file_path, "rb") as fh:
                files = {"file": (os.path.basename(file_path), fh, "application/octet-stream")}
                with httpx.Client(timeout=HTTP_TIMEOUT) as client:
                    resp = client.post(
                        f"{stt_base_url()}/stt",
                        headers=auth_headers(),
                        data=data,
                        files=files,
                    )
            if resp.status_code >= 400:
                return {
                    "success": False,
                    "transcript": "",
                    "error": f"Cartesia STT HTTP {resp.status_code}: {resp.text[:500]}",
                    "provider": self.name,
                }
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001 — contract: never raise
            return {
                "success": False,
                "transcript": "",
                "error": f"Cartesia STT request failed: {exc}",
                "provider": self.name,
            }

        transcript = payload.get("text", "") if isinstance(payload, dict) else ""
        return {
            "success": True,
            "transcript": transcript or "",
            "provider": self.name,
        }
