import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";
import assert from "node:assert/strict";
import {
	HANDOFF_LINEAGE_SCHEMA,
	cursorOwnerSessionId,
	mergeHandoffLineage,
	planCursorHandoffHook,
	planOwnerHandoff,
	shouldSpawnSuccessor,
	writeHandoffLineage,
	readHandoffLineage,
} from "./handoff-lineage.ts";
import { sessionFileHasAssistant, writeMinimalSiblingSession } from "./handoff-sibling-persist.ts";
import { extractTranscriptHints } from "./handoff-successor.ts";

const tmp = mkdtempSync(join(tmpdir(), "handoff-lineage-"));
after(() => {
	rmSync(tmp, { recursive: true, force: true });
});

test("90% owner with fake switched_at still plans switch and successor", () => {
	const plan = planOwnerHandoff({
		percent: 90,
		currentSessionFile: "/tmp/owner.jsonl",
		prep: {
			schema: "pi.handoff-prep.v1",
			source_session_id: "owner",
			snapshot_path: "/tmp/snap.json",
			child_session_file: "/tmp/child.jsonl",
			phase: "switched",
			switched_at: "2026-09-01T06:38:31.508Z",
			prompt_sent_at: "2026-09-01T06:22:42.773Z",
		},
	});
	assert.equal(plan.settled, false);
	assert.deepEqual(plan.actions, ["switch"]);
	assert.equal(plan.spawnSuccessor, true);
});

test("successor lineage settles the owner lane", () => {
	const plan = planOwnerHandoff({
		percent: 90,
		currentSessionFile: "/tmp/owner.jsonl",
		prep: {
			schema: "pi.handoff-prep.v1",
			source_session_id: "owner",
			snapshot_path: "/tmp/snap.json",
			child_session_file: "/tmp/child.jsonl",
			phase: "successor",
			successor_at: "2026-09-01T06:50:00.000Z",
			successor_job_id: "handoff-1",
		},
		lineage: {
			schema: HANDOFF_LINEAGE_SCHEMA,
			owner_session_id: "owner",
			snapshot_path: "/tmp/snap.json",
			child_job_id: "handoff-1",
			generation: 1,
			ancestors: [],
			phase: "successor",
			created_at: "2026-09-01T06:50:00.000Z",
			updated_at: "2026-09-01T06:50:00.000Z",
			successor_at: "2026-09-01T06:50:00.000Z",
		},
	});
	assert.equal(plan.settled, true);
	assert.deepEqual(plan.actions, []);
	assert.equal(plan.spawnSuccessor, false);
});

test("Cursor preCompact 90% without lineage spawns successor", () => {
	const plan = planCursorHandoffHook({
		hook_event_name: "preCompact",
		conversation_id: "agent-test-handoff",
		context_usage_percent: 90,
		context_tokens: 230000,
		context_window_size: 256000,
	});
	assert.equal(plan.ownerId, "cursor-agent-test-handoff");
	assert.equal(plan.estimate.source, "usage");
	assert.equal(plan.estimate.percent, 90);
	assert.ok(plan.actions.includes("switch"));
	assert.equal(plan.spawnSuccessor, true);
});

test("Cursor stop with huge transcript estimates over switch", () => {
	const transcript = join(tmp, "fat.jsonl");
	writeFileSync(transcript, "x".repeat(8 * 200000));
	const plan = planCursorHandoffHook({
		hook_event_name: "stop",
		conversation_id: "agent-fat",
		transcript_path: transcript,
		status: "completed",
		loop_count: 0,
	});
	assert.equal(plan.estimate.source, "transcript");
	assert.ok(plan.estimate.percent >= 75);
	assert.equal(plan.spawnSuccessor, true);
});

test("shouldSpawnSuccessor is switch-only and once", () => {
	assert.equal(shouldSpawnSuccessor({ actions: ["prepare"] }), false);
	assert.equal(shouldSpawnSuccessor({ actions: ["prepare", "switch"] }), true);
	assert.equal(shouldSpawnSuccessor({ actions: ["switch"], settled: true }), false);
	assert.equal(shouldSpawnSuccessor({ actions: ["switch"], successorAt: "t", successorJobId: "j" }), false);
});

test("lineage write/read and cursor owner id", () => {
	const owner = `lineage-test-${Date.now()}`;
	const path = writeHandoffLineage({
		schema: HANDOFF_LINEAGE_SCHEMA,
		owner_session_id: owner,
		snapshot_path: "/tmp/snap.json",
		generation: 1,
		ancestors: ["prev"],
		phase: "prepared",
		created_at: "2026-09-01T00:00:00.000Z",
		updated_at: "2026-09-01T00:00:00.000Z",
	});
	assert.match(path, /lineage/);
	assert.equal(readHandoffLineage(owner)?.phase, "prepared");
	assert.equal(cursorOwnerSessionId({ conversation_id: "abc" }), "cursor-abc");
	const merged = mergeHandoffLineage(readHandoffLineage(owner), {
		owner_session_id: owner,
		snapshot_path: "/tmp/snap2.json",
		phase: "successor",
		child_job_id: "handoff-9",
	});
	assert.equal(merged.phase, "successor");
	assert.equal(merged.generation, 1);
	assert.ok(merged.ancestors.includes("prev"));
});

test("minimal sibling file carries prep and lineage entries", () => {
	const sessionFile = join(tmp, "sib.jsonl");
	writeMinimalSiblingSession({
		sessionFile,
		sessionId: "sib-1",
		cwd: tmp,
		sourceSessionId: "owner-1",
		snapshotPath: "/tmp/snap.json",
		phase: "successor",
	});
	assert.equal(sessionFileHasAssistant(sessionFile), false);
});

test("transcript tail extracts last user without loading novels into the snapshot helper", () => {
	const transcript = join(tmp, "hints.jsonl");
	writeFileSync(
		transcript,
		`${JSON.stringify({ role: "user", content: "older" })}\n${JSON.stringify({ role: "user", content: "latest goal" })}\n${JSON.stringify({ role: "assistant", content: "working" })}\n`,
	);
	const hints = extractTranscriptHints(transcript);
	assert.deepEqual(hints.lastUser, ["older", "latest goal"]);
	assert.equal(hints.lastAssistant, "working");
});
