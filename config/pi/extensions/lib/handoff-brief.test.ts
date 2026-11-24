import assert from "node:assert/strict";
import { test } from "node:test";
import {
	BRIEF_HEADINGS,
	BRIEF_MIN_CHARS,
	buildBriefRequestText,
	capConversationText,
	classifyBrief,
	generateBrief,
	prepareConversationText,
	type BriefRejection,
} from "./handoff-brief.ts";

const filler = (label: string, lines = 6) =>
	Array.from({ length: lines }, (_, i) => `- ${label} item ${i + 1}: check the lane status file before acting.`).join("\n");

/** Shape of the replies that were wrongly rejected: complete, but with the model's own headings. */
const OWN_HEADINGS = [
	"# Continue the validation lane",
	"",
	"You are resuming as coordinator. The previous session was cut off mid-command.",
	"",
	"## Start here (read first)",
	filler("start"),
	"",
	"## Where things stand",
	filler("state"),
	"",
	"## Next steps, in order",
	filler("next"),
	"",
	"## Constraints",
	filler("constraint"),
].join("\n");

const FILES_BUT_NO_TASK = [
	"## Files to read first",
	filler("file"),
	"",
	"## Goal",
	filler("goal"),
	"",
	"## Next steps, in order",
	filler("next"),
].join("\n");

const CONFORMING = BRIEF_HEADINGS.map((heading) => `## ${heading}\n- one line`).join("\n\n");

test("a complete prompt with the model's own headings is not a stub", () => {
	assert.ok(OWN_HEADINGS.length > BRIEF_MIN_CHARS);
	assert.deepEqual(classifyBrief(OWN_HEADINGS), { ok: true, conforms: false });
});

test("a complete prompt missing only the Task heading is not a stub", () => {
	assert.deepEqual(classifyBrief(FILES_BUT_NO_TASK), { ok: true, conforms: false });
});

test("the requested headings are accepted at any length", () => {
	const short = "## Files to read first\n- a.md\n\n## Task\nRun the suite.";
	assert.ok(short.length < BRIEF_MIN_CHARS);
	assert.deepEqual(classifyBrief(short), { ok: true, conforms: true });
	assert.deepEqual(classifyBrief(CONFORMING), { ok: true, conforms: true });
});

test("real stubs are still rejected", () => {
	assert.deepEqual(classifyBrief("   \n"), { ok: false, reason: "empty" });
	assert.deepEqual(classifyBrief("I'll draft the handoff prompt now."), { ok: false, reason: "too-short" });
	const longPromise = `I'll write the handoff prompt after I inspect the repository. ${"First I need to gather more state from the running jobs and read the case files. ".repeat(8)}`;
	assert.ok(longPromise.length > BRIEF_MIN_CHARS);
	assert.deepEqual(classifyBrief(longPromise), { ok: false, reason: "meta-promise" });
});

test("promise wording inside a structured prompt does not reject it", () => {
	const quoted = `${OWN_HEADINGS}\n\n## Do not\n- Do not reply "I'll write the handoff prompt later"; do the work.`;
	assert.deepEqual(classifyBrief(quoted), { ok: true, conforms: false });
	const preamble = `Let me write the handoff prompt for the next session.\n\n${OWN_HEADINGS}`;
	assert.deepEqual(classifyBrief(preamble), { ok: true, conforms: false });
});

test("generateBrief keeps an off-format prompt without paying for a retry", async () => {
	const calls: Array<BriefRejection | undefined> = [];
	const result = await generateBrief(async (rejected) => {
		calls.push(rejected);
		return { text: `\n${OWN_HEADINGS}\n`, stopReason: "stop" };
	});
	assert.deepEqual(calls, [undefined]);
	assert.deepEqual(result, { status: "ok", text: OWN_HEADINGS, attempts: 1, conforms: false });
});

test("generateBrief retries a stub once and reports why", async () => {
	const calls: Array<BriefRejection | undefined> = [];
	const result = await generateBrief(async (rejected) => {
		calls.push(rejected);
		return calls.length === 1
			? { text: "I'll draft the handoff prompt now.", stopReason: "stop" }
			: { text: CONFORMING, stopReason: "stop" };
	});
	assert.deepEqual(calls, [undefined, "too-short"]);
	assert.deepEqual(result, { status: "ok", text: CONFORMING, attempts: 2, conforms: true });
});

test("generateBrief fails after two stubs and names the stub", async () => {
	const result = await generateBrief(async () => ({ text: "I'll draft the handoff prompt now.", stopReason: "stop" }));
	assert.equal(result.status, "failed");
	assert.equal(result.status === "failed" && result.attempts, 2);
	assert.match(result.status === "failed" ? result.reason : "", /^stub \(too-short, 34 chars\): I'll draft the handoff prompt now\.$/);
});

test("generateBrief surfaces provider errors for empty replies", async () => {
	const result = await generateBrief(async () => ({ text: "", stopReason: "error", errorMessage: "overloaded" }));
	assert.deepEqual(result, { status: "failed", reason: "no text (stopReason=error: overloaded)", attempts: 2 });
});

test("generateBrief stops when the operator aborts", async () => {
	let calls = 0;
	const result = await generateBrief(async () => {
		calls++;
		return null;
	});
	assert.equal(calls, 1);
	assert.deepEqual(result, { status: "aborted" });
});

test("the request repeats the headings after the history and explains a retry", () => {
	const text = buildBriefRequestText("[User]: build it", "ship the fix");
	assert.ok(text.indexOf("[User]: build it") < text.indexOf("ship the fix"));
	assert.ok(text.indexOf("ship the fix") < text.lastIndexOf("## Files to read first"));
	assert.ok(text.trimEnd().endsWith("## Task"));
	assert.ok(!text.includes("PREVIOUS OUTPUT WAS REJECTED"));
	const retry = buildBriefRequestText("[User]: build it", "ship the fix", "meta-promise");
	assert.match(retry, /PREVIOUS OUTPUT WAS REJECTED because it promised to write the prompt later/);
});

test("conversation text drops thinking and keeps head and tail", () => {
	assert.equal(capConversationText("abcdefghij", 3, 3), "abc\n\n[... 4 characters omitted ...]\n\nhij");
	assert.equal(capConversationText("short", 3, 3), "short");
	const prepared = prepareConversationText("[User]: hi\n\n[Assistant thinking]: secret plan\n\n[Assistant]: done");
	assert.ok(!prepared.includes("secret plan"));
	assert.ok(prepared.startsWith("[User]: hi"));
	assert.ok(prepared.endsWith("[Assistant]: done"));
});
