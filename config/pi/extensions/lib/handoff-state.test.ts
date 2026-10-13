import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { buildSnapshot, writeSnapshot, readSnapshot, readHandoffState, snapshotJson,
	formatHandoffPrompt, formatPointerSummary, formatHandoffPreparePrompt, formatHandoffAlignPrompt,
	formatContinueWorkerTask, handoffPrepInFlight, SNAPSHOT_MAX_BYTES } from "./compact-snapshot.ts";

test("complete selected fields survive caps, list limits, Unicode and paginated reads", () => {
	const root = mkdtempSync(join(tmpdir(), "handoff-state-"));
	try {
		const goal = "🛰️ critical requirement ".repeat(8000) + "DO NOT LOSE THIS TAIL";
		const next = Array.from({ length: 30 }, (_, i) => `- next ${i}: ${"detail ".repeat(100)}`);
		const paths = Array.from({ length: 50 }, (_, i) => `${"nested/".repeat(45)}file-${i}.ts`);
		const lastAssistant = next.join("\n") + "\n## Blocked\n- " + "constraint ".repeat(1000);
		const snapshot = buildSnapshot({ sessionId: "state-test", goal, branch: [
			{ type: "message", message: { role: "user", content: goal } },
			{ type: "message", message: { role: "assistant", content: lastAssistant } },
		], fileOps: { read: paths, written: paths } });
		snapshot.snapshot_path = join(root, "snapshot.json");
		writeSnapshot(snapshot);
		const disk = readSnapshot(snapshot.snapshot_path)!;
		const state = readHandoffState(disk)!;
		assert.equal(state.objective, goal);
		assert.deepEqual(state.last_user, [goal]);
		assert.equal(state.last_assistant, lastAssistant);
		assert.deepEqual(state.files_modified, paths);
		assert.equal(state.next.length, 31);
		assert.ok(Buffer.byteLength(snapshotJson(snapshot)) <= SNAPSHOT_MAX_BYTES);
		assert.doesNotMatch(snapshotJson(snapshot), /\[truncated\]/);
		const manifest = JSON.parse(readFileSync(disk.state_path!, "utf8"));
		const lines = readFileSync(manifest.data_path, "utf8").trimEnd().split("\n");
		assert.ok(lines.every((line: string) => Buffer.byteLength(line) < 8192));
		const index = manifest.fields.objective;
		// Emulate read(offset, limit) in small pages, without needing the whole artifact in context.
		const chunks: string[] = [];
		for (let cursor = index.first_line - 1; cursor < index.first_line - 1 + index.lines; cursor += 7) {
			const page = lines.slice(cursor, Math.min(cursor + 7, index.first_line - 1 + index.lines));
			chunks.push(...page.map((line: string) => JSON.parse(line).text));
		}
		assert.equal(JSON.parse(chunks.join("")), goal);
		for (const path of [disk.snapshot_path, disk.state_path!, manifest.data_path]) {
			assert.equal(statSync(path).mode & 0o777, 0o600);
		}
		const prompt = formatHandoffPrompt(disk, goal);
		assert.ok(prompt.length <= 800);
		assert.match(prompt, /Execute Goal\/next now/);
		assert.match(prompt, /state_path/);
		assert.doesNotMatch(prompt, /\[truncated\]/);
		assert.match(formatPointerSummary(disk), /Execute next now/);
		assert.match(formatContinueWorkerTask(disk), /Do not ask/);
		for (const format of [formatHandoffPreparePrompt, formatHandoffAlignPrompt]) {
			assert.ok(format(disk, goal).length <= 800);
			assert.doesNotMatch(format(disk, goal), /\[truncated\]/);
		}
		for (const format of [formatHandoffPrompt, formatHandoffPreparePrompt]) {
			const child = buildSnapshot({ sessionId: "child", branch: [
				{ type: "message", message: { role: "user", content: format(disk, goal) } },
			] });
			child.snapshot_path = join(root, "child.json");
			writeSnapshot(child);
			assert.equal(readHandoffState(readSnapshot(child.snapshot_path)!)!.objective, goal);
			assert.equal(child.previous_snapshot, disk.snapshot_path);
		}
		// Corruption must fail explicitly, never silently supply a shortened objective.
		writeFileSync(manifest.data_path, lines.slice(1).join("\n"));
		assert.throws(() => readHandoffState(disk), /chunk|checksum/);
	} finally { rmSync(root, { recursive: true, force: true }); }
});

test("missing sibling/job references expire instead of holding handoff forever", () => {
	const now = Date.now();
	assert.equal(handoffPrepInFlight({ childFile: "missing", childJobId: "old-job", fileExists: false,
		preparedAt: new Date(now - 6000).toISOString(), now }), false);
	assert.equal(handoffPrepInFlight({ childFile: "pending", fileExists: false,
		preparedAt: new Date(now - 100).toISOString(), now }), true);
});
