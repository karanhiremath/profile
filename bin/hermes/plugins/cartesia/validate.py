#!/usr/bin/env python3
"""Standalone validation for the Cartesia Hermes plugin.

Exercises the *currently configured* endpoint (public, staging, on-prem, or
in-cluster) end to end without going through Hermes. Reads the same env as the
plugin — set CARTESIA_BASE_URL / CARTESIA_API_KEY / CARTESIA_VOICE_ID in
~/.hermes/.env (or export them) before running. Never prints the API key.

Run with the toolchain venv python:

    ~/.local/share/hermes-toolchain/venv/bin/python \\
        ~/.hermes/plugins/cartesia/validate.py            # config + connectivity
    ... validate.py --tts                                  # synth roundtrip
    ... validate.py --tts --stt                            # synth then transcribe back

Examples of pointing at internal targets (keep hosts in ~/.hermes/.env):
    CARTESIA_BASE_URL=https://staging-api.cartesia.ai
    CARTESIA_BASE_URL=http://localhost:8000      # on-prem docker-compose
    CARTESIA_BASE_URL=http://api:8000            # in-cluster (ClusterIP)
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Import the plugin as a package (its modules use relative imports).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cartesia._common import api_version, base_url, get_env, stt_base_url  # noqa: E402
from cartesia.stt import CartesiaTranscriptionProvider  # noqa: E402
from cartesia.tts import CartesiaTTSProvider  # noqa: E402


def _ok(msg: str) -> None:
    print(f"  ok   {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL {msg}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the Cartesia plugin endpoint.")
    ap.add_argument("--tts", action="store_true", help="synthesize a short phrase")
    ap.add_argument("--stt", action="store_true", help="transcribe the synthesized clip (implies --tts)")
    ap.add_argument("--text", default="Cartesia validation check, one two three.")
    args = ap.parse_args()
    if args.stt:
        args.tts = True

    tts = CartesiaTTSProvider()
    stt = CartesiaTranscriptionProvider()

    print("config")
    print(f"  tts_endpoint   {base_url()}/tts/bytes")
    print(f"  stt_endpoint   {stt_base_url()}/stt")
    print(f"  api_version    {api_version()}")
    print(f"  api_key        {'set' if get_env('CARTESIA_API_KEY') else 'MISSING'}")
    print(f"  tts_model      {tts.default_model()}")
    print(f"  stt_model      {stt.default_model()}")
    print(f"  voice          {get_env('CARTESIA_VOICE_ID') or '(none in env — will use first /voices result)'}")

    failures = 0

    print("connectivity")
    voices = tts.list_voices()
    if voices:
        _ok(f"GET /voices -> {len(voices)} voices (e.g. {voices[0]['id']})")
    else:
        _fail("GET /voices returned nothing (bad key, endpoint, or no voices on this stack)")
        failures += 1

    clip = None
    if args.tts:
        print("tts")
        out = os.path.join(os.environ.get("TMPDIR", "/tmp"), "cartesia_validate.mp3")
        try:
            t0 = time.monotonic()
            tts.synthesize(args.text, out, format="mp3")
            dt = (time.monotonic() - t0) * 1000
            size = os.path.getsize(out)
            _ok(f"synthesize -> {size} bytes in {dt:.0f} ms ({out})")
            clip = out
        except Exception as exc:  # noqa: BLE001
            _fail(f"synthesize raised: {exc}")
            failures += 1

    if args.stt:
        print("stt")
        if not clip:
            _fail("no clip to transcribe (tts step failed)")
            failures += 1
        else:
            t0 = time.monotonic()
            res = stt.transcribe(clip)
            dt = (time.monotonic() - t0) * 1000
            if res.get("success"):
                _ok(f"transcribe -> {res.get('transcript')!r} in {dt:.0f} ms")
            else:
                _fail(f"transcribe: {res.get('error')}")
                failures += 1

    print("PASS" if failures == 0 else f"FAILED ({failures})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
