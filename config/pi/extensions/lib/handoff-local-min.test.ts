import { test } from "node:test";
import assert from "node:assert/strict";
import { atHarnessLocalMin, handoffDesignerBrief, planCompactDescent } from "./handoff-local-min.ts";

test("first compact is never local min", () => {
	assert.equal(atHarnessLocalMin({ compactGeneration: 1, percent: 92 }), false);
	assert.equal(atHarnessLocalMin({ compactGeneration: 0, percent: 92 }), false);
});

test("second compact still at align is local min", () => {
	assert.equal(atHarnessLocalMin({ compactGeneration: 2, percent: 71 }), true);
	assert.equal(atHarnessLocalMin({ compactGeneration: 2, percent: 40 }), false);
	assert.equal(atHarnessLocalMin({ compactGeneration: 3, percent: 40 }), true);
});

test("first preCompact drafts and designs, does not switch", () => {
	assert.deepEqual(planCompactDescent({ percent: 40, compactedInsteadOfHandoff: true }).actions, [
		"prepare",
		"design",
	]);
	assert.equal(planCompactDescent({ percent: 90, compactGeneration: 1, compactedInsteadOfHandoff: true }).actions.includes("switch"), false);
});

test("prepared second dump below align aligns only", () => {
	assert.deepEqual(
		planCompactDescent({
			percent: 40,
			compactGeneration: 2,
			prepared: true,
			compactedInsteadOfHandoff: true,
		}).actions,
		["align"],
	);
});

test("prepared second dump still high forces switch", () => {
	const plan = planCompactDescent({
		percent: 72,
		compactGeneration: 2,
		prepared: true,
		aligned: true,
		compactedInsteadOfHandoff: true,
	});
	assert.equal(plan.localMin, true);
	assert.deepEqual(plan.actions, ["switch"]);
});

test("over-ceiling successor stays in design", () => {
	assert.deepEqual(
		planCompactDescent({
			percent: 91,
			prepared: true,
			aligned: true,
			successorMaySwitch: false,
		}).actions,
		["design"],
	);
});

test("percent switch still wins without a dump", () => {
	assert.deepEqual(planCompactDescent({ percent: 91, prepared: true, aligned: true }).actions, ["switch"]);
	assert.deepEqual(planCompactDescent({ percent: 31 }).actions, ["prepare", "design"]);
	assert.deepEqual(planCompactDescent({ percent: 91, switched: true }).actions, []);
});

test("designer brief is bounded", () => {
	const brief = handoffDesignerBrief({
		snapshotPath: "/tmp/snap.json",
		ownerId: "cursor-x",
		percent: 64,
		generation: 1,
	});
	assert.match(brief, /Do not switch/);
	assert.match(brief, /cursor-x/);
});
