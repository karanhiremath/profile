#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from compile import compile_adapter, write_compiled  # noqa: E402
from engine import (  # noqa: E402
    StreamState,
    apply_edge,
    apply_introspect,
    apply_stream,
    apply_tts,
    context_from_env,
    filter_catalog,
    public_status,
    transform_text,
)
from schema import load_bundle, load_yaml  # noqa: E402


def bundle():
    return load_bundle(ROOT / "config" / "aos" / "policy", Path(tempfile.mkdtemp()))


class YamlTests(unittest.TestCase):
    def test_nested_when(self):
        data = load_yaml(
            "when:\n  all:\n    - wrapper:\n        - herm-tui\n    - provider:\n        - cursor\n"
        )
        self.assertEqual(data["when"]["all"][0]["wrapper"], ["herm-tui"])
        self.assertEqual(data["when"]["all"][1]["provider"], ["cursor"])

    def test_folded_description(self):
        data = load_yaml("description: >\n  one line\n  two line\n")
        self.assertIn("one line", data["description"])
        self.assertIn("two line", data["description"])


class CatalogTests(unittest.TestCase):
    def test_granola_denied_for_implementor(self):
        ctx = {"class": "implementor", "wrapper": "pi", "provider": "openai"}
        kept = filter_catalog(
            bundle(),
            "catalog.tools",
            ["read", "query_granola_meetings", "list_meetings", "bash"],
            ctx,
        )
        self.assertEqual(kept, ["read", "bash"])

    def test_granola_allowed_for_librarian(self):
        ctx = {"class": "librarian", "wrapper": "pi"}
        kept = filter_catalog(
            bundle(),
            "catalog.tools",
            ["read", "query_granola_meetings"],
            ctx,
        )
        self.assertEqual(kept, ["read", "query_granola_meetings"])

    def test_pi_bridge_denies_task(self):
        ctx = {"wrapper": "pi", "bridge_tools": ["pi__subagent"], "class": "implementor"}
        kept = filter_catalog(bundle(), "catalog.tools", ["Read", "Task", "pi__subagent"], ctx)
        self.assertEqual(kept, ["Read", "pi__subagent"])

    def test_herm_tui_cursor_exclusive(self):
        ctx = {"wrapper": "herm-tui", "provider": "cursor", "class": "implementor"}
        kept = filter_catalog(
            bundle(),
            "catalog.tools",
            ["Task", "Shell", "Read", "pi__subagent", "hermes_run", "profile_manifest"],
            ctx,
        )
        self.assertEqual(kept, ["pi__subagent", "hermes_run", "profile_manifest"])


class SilentTextTests(unittest.TestCase):
    def test_strip_never_mentions_policy(self):
        ctx = {"wrapper": "herm-tui", "provider": "cursor"}
        text = "Working on the patch. tool juggling is required. Cursor-native tool calls follow."
        out = transform_text(bundle(), "stream.outbound", text, ctx)
        self.assertIn("Working on the patch.", out)
        self.assertNotIn("tool juggling", out.lower())
        self.assertNotIn("cursor-native tool", out.lower())
        self.assertNotIn("policy", out.lower())
        self.assertNotIn("remap", out.lower())

    def test_cot_and_moa_same_strip(self):
        ctx = {"wrapper": "hermes", "provider": "cursor"}
        leaked = "I need to use Hermes tools instead of Cursor because of remapping Cursor tools."
        for surface in ("cot", "moa"):
            out = transform_text(bundle(), surface, leaked, ctx)
            self.assertNotIn("hermes tools instead", out.lower())
            self.assertNotIn("remapping cursor", out.lower())

    def test_graph_edge_wrap(self):
        ctx = {"wrapper": "herm-tui", "provider": "cursor"}
        payload = json.dumps({"note": "do not call Cursor-native Task here"})
        out = apply_edge(bundle(), payload, ctx, src="cosw", dst="worker")
        self.assertNotIn("Cursor-native", out)
        self.assertNotIn("Task here", out)

    def test_introspect_wrap(self):
        ctx = {"wrapper": "herm", "provider": "cursor"}
        view = "node tools: Task, pi__subagent; block all tool calls on the cursor side"
        out = apply_introspect(bundle(), view, ctx, node="worker")
        self.assertNotIn("block all tool calls", out.lower())

    def test_status_omits_rule_bodies(self):
        ctx = {"wrapper": "herm-tui", "provider": "cursor"}
        status = public_status(bundle(), ctx)
        blob = json.dumps(status)
        self.assertNotIn("tool juggling", blob)
        self.assertIn("herm-tui-cursor-exclusive", status["ids"])
        self.assertGreaterEqual(status["silent"], 1)


class VoiceTtsTests(unittest.TestCase):
    def test_exact_stall_rewritten(self):
        ctx = {"wrapper": "hermes"}
        out = apply_tts(bundle(), "I'm working on it.", ctx)
        self.assertNotIn("i'm working on it", out.lower())
        self.assertNotIn("i am working on it", out.lower())
        self.assertTrue(out.strip())
        self.assertNotIn("did not reply", out.lower())

    def test_real_work_sentence_stays(self):
        ctx = {"wrapper": "hermes"}
        text = "I'm working on the auth patch."
        self.assertEqual(apply_tts(bundle(), text, ctx), text)

    def test_cos_timeout_rewritten(self):
        ctx = {"wrapper": "cosw"}
        out = apply_tts(bundle(), "Chief of Staff did not reply.", ctx)
        self.assertNotIn("did not reply", out.lower())
        self.assertNotIn("chief of staff did not", out.lower())
        self.assertTrue(out.strip())

    def test_empty_becomes_continuation(self):
        out = apply_tts(bundle(), "", {"wrapper": "hermes"})
        self.assertTrue(out.strip())
        self.assertNotIn("did not reply", out.lower())
        self.assertNotIn("i'm working on it", out.lower())

    def test_stream_holds_partial_sentence(self):
        ctx = {"wrapper": "hermes"}
        state = StreamState()
        first = apply_stream(bundle(), "stream.tts", "I'm work", ctx, state)
        self.assertEqual(first.emit, "")
        done = apply_stream(bundle(), "stream.tts", "ing on it.", ctx, state, final=True)
        spoken = first.emit + done.emit
        self.assertNotIn("i'm working on it", spoken.lower())


class StreamTests(unittest.TestCase):
    def test_chunk_boundary(self):
        ctx = {"wrapper": "herm-tui", "provider": "cursor"}
        phrase = "tool juggling"
        left, right = phrase[:6], phrase[6:]
        state = StreamState()
        result1 = apply_stream(bundle(), "stream.outbound", "Hello " + left, ctx, state)
        result2 = apply_stream(bundle(), "stream.outbound", right + " done", ctx, state, final=True)
        out = result1.emit + result2.emit
        self.assertNotIn("tool juggling", out.lower())
        self.assertIn("Hello", out)
        self.assertIn("done", out)


class CompileTests(unittest.TestCase):
    def test_cursor_adapter_denies_native(self):
        ctx = {"wrapper": "herm-tui", "provider": "cursor"}
        payload = compile_adapter(bundle(), "cursor", ctx)
        self.assertEqual(payload["approvalMode"], "allowlist")
        self.assertIn("Task", payload["permissions"]["deny"])
        self.assertIn("pi__subagent", payload["permissions"]["allow"])
        self.assertTrue(payload["silent"])

    def test_write_compiled(self):
        ctx = {"wrapper": "herm-tui", "provider": "cursor"}
        dest = write_compiled(bundle(), ctx, dest=Path(tempfile.mkdtemp()) / "compiled")
        self.assertTrue((dest / "cursor.json").exists())
        self.assertTrue((dest / "codex.toml").exists())
        self.assertTrue((dest / "graph-edge.json").exists())
        graph = json.loads((dest / "graph-edge.json").read_text())
        self.assertTrue(graph["wrap"]["edges"])


class EnvContextTests(unittest.TestCase):
    def test_context_from_env(self):
        ctx = context_from_env(
            {
                "HERMES_TUI": "1",
                "AOS_PROVIDER": "cursor",
                "PI_PROFILE_CLASS": "implementor",
                "PI_BRIDGE_TOOLS": "pi__subagent,pi__atop_plan",
            }
        )
        self.assertEqual(ctx["wrapper"], "herm-tui")
        self.assertEqual(ctx["provider"], "cursor")
        self.assertIn("pi__subagent", ctx["bridge_tools"])


if __name__ == "__main__":
    unittest.main()
