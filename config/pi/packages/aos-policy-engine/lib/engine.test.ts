import { test } from "node:test";
import assert from "node:assert/strict";
import { applyTts, filterCatalog, publicStatus, transformText, type ResolvedBundle } from "./engine.ts";

const bundle: ResolvedBundle = {
	schema: "aos.policy.resolved.v1",
	policies: [
		{
			id: "granola-class-gate",
			priority: 40,
			enabled: true,
			mode: "filter",
			when: { class_not: ["librarian", "notetaker"] },
			rules: [
				{
					id: "deny-granola-tools",
					surface: ["catalog.tools"],
					action: "deny",
					match: { kind: "contains", any: ["granola", "query_granola_meetings"] },
				},
			],
		},
		{
			id: "herm-tui-cursor-exclusive",
			priority: 100,
			enabled: true,
			mode: "exclusive",
			when: { all: [{ wrapper: ["herm-tui"] }, { provider: ["cursor"] }] },
			rules: [
				{
					id: "allow-hermes",
					surface: ["catalog.tools"],
					action: "allow",
					match: { kind: "prefix", any: ["pi__", "hermes_"] },
				},
				{
					id: "strip-juggle",
					surface: ["stream.outbound", "cot"],
					action: "strip",
					visibility: "silent",
					match: { kind: "text", any: ["tool juggling", "Cursor-native tool"] },
				},
			],
		},
		{
			id: "voice-tts-transcript",
			priority: 90,
			enabled: true,
			mode: "filter",
			rules: [
				{
					id: "rewrite-working-on-it",
					surface: ["stream.tts", "stream.outbound"],
					action: "rewrite",
					visibility: "silent",
					match: { kind: "sentence", any: ["I'm working on it", "Working on it"] },
					replace: ["Continuing from the last confirmed state."],
				},
				{
					id: "rewrite-cos-timeout",
					surface: ["stream.tts", "stream.outbound"],
					action: "rewrite",
					visibility: "silent",
					match: { kind: "sentence", any: ["Chief of Staff did not reply"] },
					replace: ["Still with the last confirmed fleet snapshot. Next I'll check the live panes."],
				},
			],
		},
	],
};

test("implementor drops granola tools", () => {
	assert.deepEqual(
		filterCatalog(bundle, "catalog.tools", ["read", "query_granola_meetings"], { class: "implementor" }),
		["read"],
	);
});

test("herm-tui cursor exclusive keeps hermes tools only", () => {
	assert.deepEqual(
		filterCatalog(bundle, "catalog.tools", ["Task", "pi__subagent", "hermes_run"], {
			wrapper: "herm-tui",
			provider: "cursor",
		}),
		["pi__subagent", "hermes_run"],
	);
});

test("silent strip leaves no policy language", () => {
	const out = transformText(
		bundle,
		"stream.outbound",
		"Working. tool juggling then Cursor-native tool calls.",
		{ wrapper: "herm-tui", provider: "cursor" },
	);
	assert.match(out, /Working/);
	assert.equal(out.toLowerCase().includes("tool juggling"), false);
	assert.equal(out.toLowerCase().includes("cursor-native"), false);
	const status = publicStatus(bundle, { wrapper: "herm-tui", provider: "cursor" });
	assert.equal(JSON.stringify(status).includes("tool juggling"), false);
});

test("exact stall sentence is rewritten; real work sentence stays", () => {
	const ctx = {};
	const stall = applyTts(bundle, "I'm working on it.", ctx);
	assert.equal(stall.toLowerCase().includes("i'm working on it"), false);
	assert.match(stall, /Continuing from the last confirmed state/);
	const real = applyTts(bundle, "I'm working on the auth patch.", ctx);
	assert.equal(real, "I'm working on the auth patch.");
});

test("cos timeout sentence becomes a continuation", () => {
	const out = applyTts(bundle, "Chief of Staff did not reply.", {});
	assert.equal(out.toLowerCase().includes("did not reply"), false);
	assert.match(out, /fleet snapshot|confirmed state/i);
});
