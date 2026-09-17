import { test } from "node:test";
import assert from "node:assert/strict";
import {
	OVERLAY_TABLE,
	modelFamily,
	parseLauncher,
	resolveHandoffOverlay,
} from "./handoff-overlay.ts";

test("board default when nothing is measured", () => {
	const r = resolveHandoffOverlay({ host: "herm-tui", launcher: "cosw-gpt6" });
	assert.equal(r.budget.successor_target_percent, 30);
	assert.equal(r.budget.successor_ceiling_percent, 60);
	assert.equal(r.budget.successor_force_percent, 90);
	assert.equal(r.source, "board");
	assert.equal(r.family, "gpt-6");
	assert.equal(r.profile, "cosw");
	assert.equal(OVERLAY_TABLE["family:gpt-6"]?.measured, false);
	assert.equal(OVERLAY_TABLE["family:grok"]?.measured, false);
});

test("grok family from model slug still inherits board", () => {
	const r = resolveHandoffOverlay({ host: "cursor", model: "cursor/grok-4.6:fast" });
	assert.equal(r.family, "grok");
	assert.equal(r.source, "board");
	assert.equal(r.budget.successor_target_percent, 30);
});

test("parseLauncher splits cos-gpt6 / cosw-gpt6", () => {
	assert.deepEqual(parseLauncher("cosw-gpt6"), { launcher: "cosw-gpt6", profile: "cosw", family: "gpt-6" });
	assert.deepEqual(parseLauncher("cos-gpt6"), { launcher: "cos-gpt6", profile: "cos", family: "gpt-6" });
	assert.equal(modelFamily("openai-codex/gpt-6-astra"), "gpt-6");
	assert.equal(modelFamily("xai/grok-4.6"), "grok");
});

test("session/explicit measured patches win", () => {
	const session = resolveHandoffOverlay({
		launcher: "cosw-gpt6",
		session: { successor_target_percent: 20, measured: true },
	});
	assert.equal(session.source, "session");
	assert.equal(session.budget.successor_target_percent, 20);
	const explicit = resolveHandoffOverlay({
		launcher: "cosw-gpt6",
		session: { successor_target_percent: 20, measured: true },
		explicit: { successor_target_percent: 15, measured: true },
	});
	assert.equal(explicit.source, "explicit");
	assert.equal(explicit.budget.successor_target_percent, 15);
});

test("all hosts share the same board numbers", () => {
	for (const host of ["pi", "hermes", "herm-tui", "cursor"] as const) {
		assert.equal(resolveHandoffOverlay({ host }).budget.successor_target_percent, 30);
	}
});
