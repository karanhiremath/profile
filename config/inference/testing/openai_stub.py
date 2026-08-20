#!/usr/bin/env python3
"""Minimal OpenAI-compatible server used to test the harness contract.

`inf probe` asserts a backend does four things: /health, /v1/models,
non-streaming chat, and SSE streaming (plus tool_calls when declared). This stub
does exactly those and nothing else, so CI and a fresh laptop can validate the
registry, the renderers and every harness binding without downloading a 27B
model or owning a GPU.

    python3 openai_stub.py --port 8199 --model stub-model [--speed 200]

--speed is emitted tokens/sec, so `inf bench` can be exercised (and a fake
"speculative" instance can be given a higher speed than its baseline to prove
the speedup math end to end).
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ARGS = None
WORDS = ("def", "reverse", "(", "head", "):", "prev", "=", "None", "while", "head", ":",
         "nxt", "=", "head", ".", "next", "head", ".", "next", "=", "prev")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/health", "/healthz"):
            self._send(200, b'{"status":"ok"}')
        elif self.path.rstrip("/") in ("/v1/models", "/api/tags"):
            self._send(200, json.dumps({"object": "list", "data": [
                {"id": ARGS.model, "object": "model", "owned_by": "stub"}]}).encode())
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self) -> None:
        if not self.path.startswith("/v1/chat/completions"):
            self._send(404, b'{"error":"not found"}')
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, b'{"error":"bad json"}')
            return
        n = min(int(req.get("max_tokens") or 32), 4096)
        delay = 1.0 / ARGS.speed if ARGS.speed > 0 else 0.0

        if req.get("tools"):
            self._tool_call(req)
        elif req.get("stream"):
            self._stream(n, delay)
        else:
            self._blocking(req, n, delay)

    def _blocking(self, req: dict, n: int, delay: float) -> None:
        toks = [WORDS[i % len(WORDS)] for i in range(n)]
        msgs = req.get("messages") or []
        last = (msgs[-1].get("content") if msgs else "") or ""
        # Honour the probe's "Reply with exactly: OK" so `inf probe` chat is meaningful.
        text = "OK" if "exactly: OK" in last else " ".join(toks)
        out_tokens = 1 if text == "OK" else n
        time.sleep(delay * out_tokens)
        self._send(200, json.dumps({
            "id": "stub-1", "object": "chat.completion", "model": ARGS.model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": out_tokens,
                      "total_tokens": 12 + out_tokens},
        }).encode())

    def _tool_call(self, req: dict) -> None:
        fn = ((req["tools"][0] or {}).get("function") or {}).get("name", "tool")
        self._send(200, json.dumps({
            "id": "stub-2", "object": "chat.completion", "model": ARGS.model,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "call_1", "type": "function", "function": {
                    "name": fn, "arguments": json.dumps({"city": "Oakland"})}}]}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
        }).encode())

    def _stream(self, n: int, delay: float) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for i in range(n):
            chunk = {"id": "stub-3", "object": "chat.completion.chunk", "model": ARGS.model,
                     "choices": [{"index": 0, "delta": {"content": WORDS[i % len(WORDS)] + " "}}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
            if delay:
                time.sleep(delay)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> None:
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8199)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--model", default="stub-model")
    ap.add_argument("--speed", type=float, default=500.0, help="emitted tokens/sec")
    ARGS = ap.parse_args()
    srv = ThreadingHTTPServer((ARGS.host, ARGS.port), Handler)
    print(f"stub: {ARGS.model} on http://{ARGS.host}:{ARGS.port} at {ARGS.speed} tok/s", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
