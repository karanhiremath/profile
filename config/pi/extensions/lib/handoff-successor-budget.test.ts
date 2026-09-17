import { test } from "node:test";
import assert from "node:assert/strict";
import {
	PACKET_BUDGET_PERCENT,
	SUCCESSOR_CEILING_PERCENT,
	SUCCESSOR_FORCE_PERCENT,
	SUCCESSOR_TARGET_PERCENT,
	estimateSuccessorFill,
	successorPromptBudgetLines,
	trimPacketFields,
} from "./handoff-successor-budget.ts";

test("defaults are packet 5 / land 30 / ceiling 60 / force 90", () => {
	assert.equal(PACKET_BUDGET_PERCENT, 5);
	assert.equal(SUCCESSOR_TARGET_PERCENT, 30);
	assert.equal(SUCCESSOR_CEILING_PERCENT, 60);
	assert.equal(SUCCESSOR_FORCE_PERCENT, 90);
});

test("small pointer on thin baseline is ok", () => {
	const fill = estimateSuccessorFill({
		baselineChars: 20_000,
		packetBytes: 4_000,
		promptChars: 800,
	});
	assert.deepEqual(fill.pollution, ["ok"]);
	assert.equal(fill.may_switch, true);
	assert.ok(fill.percent < SUCCESSOR_TARGET_PERCENT);
});

test("transcript or inlined skill is pollution", () => {
	assert.ok(estimateSuccessorFill({ transcriptChars: 100 }).pollution.includes("transcript"));
	assert.ok(estimateSuccessorFill({ inlineSkillChars: 100 }).pollution.includes("inline_skill"));
	assert.ok(estimateSuccessorFill({ fileContentChars: 100 }).pollution.includes("file_contents"));
	assert.equal(estimateSuccessorFill({ transcriptChars: 100 }).may_switch, false);
});

test("fat baseline over ceiling blocks switch", () => {
	const fill = estimateSuccessorFill({
		baselineChars: 800_000,
		packetBytes: 100,
	});
	assert.ok(fill.pollution.includes("over_ceiling"));
	assert.equal(fill.may_switch, false);
});

test("over target but under ceiling may still switch", () => {
	const fill = estimateSuccessorFill({
		baselineChars: 400_000,
		packetBytes: 100,
	});
	assert.ok(fill.pollution.includes("over_target"));
	assert.equal(fill.pollution.includes("over_ceiling"), false);
	assert.equal(fill.may_switch, true);
});

test("prompt lines name the 30/60/90 ladder plus packet", () => {
	const lines = successorPromptBudgetLines();
	assert.match(lines.join("\n"), /packet_budget: 5%/);
	assert.match(lines.join("\n"), /successor_target: 30%/);
	assert.match(lines.join("\n"), /successor_ceiling: 60%/);
	assert.match(lines.join("\n"), /successor_force: 90%/);
});

test("trimPacketFields drops assistant and caps lists", () => {
	const trimmed = trimPacketFields({
		last_assistant: "novel",
		last_user: ["a", "b", "c"],
		files_read: Array.from({ length: 20 }, (_, i) => `f${i}`),
		jobs: ["1", "2", "3", "4"],
	});
	assert.equal(trimmed.last_assistant, undefined);
	assert.deepEqual(trimmed.last_user, ["c"]);
	assert.equal(trimmed.files_read?.length, 8);
	assert.equal(trimmed.jobs?.length, 3);
});
