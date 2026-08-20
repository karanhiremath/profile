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
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ARGS = None
WORDS = ("def", "reverse", "(", "head", "):", "prev", "=", "None", "while", "head", ":",
         "nxt", "=", "head", ".", "next", "head", ".", "next", "=", "prev")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):  # quiet
        pass

    def _trace(self, label: str, obj) -> None:
        """Dump requests/responses when --log-requests is set. Real harnesses
        send fields a hand-written probe does not, so being able to see the
        actual request is how compat gaps get found."""
        if not ARGS.log_requests:
            return
        print(f"[{label}] {json.dumps(obj)[:1200]}", file=sys.stderr, flush=True)

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
        self._trace("request", {k: v for k, v in req.items() if k != "messages"})
        self._trace("messages", req.get("messages"))
        # Real clients send max_completion_tokens (the current OpenAI field);
        # older ones send max_tokens. A server that honours only one of them
        # silently ignores the caller's limit.
        limit = req.get("max_completion_tokens") or req.get("max_tokens") or 32
        n = max(1, min(int(limit), 512))
        delay = 1.0 / ARGS.speed if ARGS.speed > 0 else 0.0
        want_usage = bool((req.get("stream_options") or {}).get("include_usage"))

        # stream wins over tools. A coding agent sends BOTH on every turn, and
        # answering a streaming request with a non-SSE body is exactly the bug
        # this fixture exists to catch.
        if req.get("stream"):
            self._stream(n, delay, tools=bool(req.get("tools")), want_usage=want_usage)
        elif req.get("tools"):
            self._tool_call(req)
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

    def _sse(self, obj) -> None:
        self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
        self.wfile.flush()

    def _stream(self, n: int, delay: float, *, tools: bool = False,
                want_usage: bool = False) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        base = {"id": "stub-3", "object": "chat.completion.chunk", "model": ARGS.model}
        # Role-only opening delta, as real servers send.
        self._sse({**base, "choices": [{"index": 0, "delta": {"role": "assistant"},
                                        "finish_reason": None}]})
        for i in range(n):
            self._sse({**base, "choices": [
                {"index": 0, "delta": {"content": WORDS[i % len(WORDS)] + " "},
                 "finish_reason": None}]})
            if delay:
                time.sleep(delay)

        # finish_reason must match what was actually emitted. Claiming
        # "tool_calls" without streaming any tool_call deltas makes an agent loop
        # forever waiting for calls that never arrive, so the default is "stop"
        # even when tools were offered — a model declining to call a tool is a
        # normal turn. --stream-tool-calls exercises the streamed-tool-call path
        # deliberately, emitting the deltas AND the matching finish_reason.
        if tools and ARGS.stream_tool_calls:
            self._sse({**base, "choices": [{"index": 0, "finish_reason": None, "delta": {
                "tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                "function": {"name": "read", "arguments": ""}}]}}]})
            self._sse({**base, "choices": [{"index": 0, "finish_reason": None, "delta": {
                "tool_calls": [{"index": 0,
                                "function": {"arguments": '{"path":"README.md"}'}}]}}]})
            self._sse({**base, "choices": [
                {"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
        elif ARGS.broken_stream:
            # Regression fixture: end the stream with no terminal finish_reason,
            # exactly the shape that made pi fail with "Stream ended without
            # finish_reason". `inf probe` must reject this.
            pass
        else:
            self._sse({**base, "choices": [
                {"index": 0, "delta": {}, "finish_reason": "stop"}]})
        if want_usage:
            # stream_options.include_usage asks for a final usage-only chunk with
            # an empty choices array.
            self._sse({**base, "choices": [],
                       "usage": {"prompt_tokens": 12, "completion_tokens": n,
                                 "total_tokens": 12 + n}})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> None:
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8199)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--model", default="stub-model")
    ap.add_argument("--speed", type=float, default=500.0, help="emitted tokens/sec")
    ap.add_argument("--log-requests", action="store_true",
                    help="dump each request to stderr (for harness compat debugging)")
    ap.add_argument("--broken-stream", action="store_true",
                    help="omit the terminal finish_reason chunk (regression fixture)")
    ap.add_argument("--stream-tool-calls", action="store_true",
                    help="emit streamed tool_call deltas + finish_reason=tool_calls "
                         "(off by default so agent loops terminate)")
    ARGS = ap.parse_args()
    srv = ThreadingHTTPServer((ARGS.host, ARGS.port), Handler)
    print(f"stub: {ARGS.model} on http://{ARGS.host}:{ARGS.port} at {ARGS.speed} tok/s", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
