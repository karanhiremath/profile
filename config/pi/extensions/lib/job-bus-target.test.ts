import { test } from "node:test";
import assert from "node:assert/strict";
import {
	classifyDelivery,
	configuredSubscriptions,
	formatPointerBatch,
	formatSteer,
	isCursorSession,
	isInboxPath,
	isTerminalStatus,
	resolveTargetSid,
	shouldSteerSelf,
	unscopedBareLaneWarning,
	type JobRecord,
	type SteerDecisionInput,
} from "./job-bus-target.ts";

test("isCursorSession detects bridge flags, not only CURSOR_AGENT", () => {
	assert.equal(isCursorSession({}), false);
	assert.equal(isCursorSession({ CURSOR_AGENT: "1" }), true);
	assert.equal(isCursorSession({ PI_CURSOR_SDK: "1" }), true);
	assert.equal(isCursorSession({ PI_CURSOR_BRIDGE: "1" }), true);
	assert.equal(isCursorSession({ CURSOR_TRACE_ID: "trace-1" }), true);
	assert.equal(isCursorSession({ CURSOR_CONVERSATION_ID: "conv-1" }), true);
	assert.equal(isCursorSession({ CURSOR_AGENT: "0", PI_CURSOR_SDK: "1" }), true);
	assert.equal(isCursorSession({ CURSOR_AGENT: "0" }), false);
});

test("unscopedBareLaneWarning only fires for bare lanes on unscoped", () => {
	assert.equal(unscopedBareLaneWarning("cartesia-security", ["subagent"]), "");
	assert.equal(unscopedBareLaneWarning("unscoped", []), "");
	assert.equal(unscopedBareLaneWarning("unscoped", ["project:profile/subagent"]), "");
	assert.match(unscopedBareLaneWarning("unscoped", ["subagent"]), /host-wide unscoped dump/);
});

const inbox = "/home/karan/.pi/agent/jobs/sessions/sess-here";
const named = "/home/karan/.pi/agent/jobs/streams/subagent/job-1.status.json";
const own = `${inbox}/job-1.status.json`;

function rec(over: Partial<JobRecord> = {}): JobRecord {
	return { jobId: "job-1", status: "succeeded", stream: "subagent", ...over };
}

test("cursor ignores global file subscriptions", () => {
	assert.deepEqual(
		configuredSubscriptions({
			cursor: true,
			fileSubs: ["subagent", "car1980-il5-sst"],
			runtimeSubs: ["assembler"],
		}),
		["assembler"],
	);
	assert.deepEqual(
		configuredSubscriptions({
			cursor: false,
			fileSubs: ["subagent"],
			runtimeSubs: ["assembler"],
		}),
		["subagent", "assembler"],
	);
});

test("cursor ignores env and scope lane inheritance", () => {
	assert.deepEqual(
		configuredSubscriptions({
			cursor: true,
			fileSubs: ["subagent"],
			envSubs: ["cloudbuild", "assembler"],
			runtimeSubs: [],
			scope: "global",
		}),
		[],
	);
	assert.deepEqual(
		configuredSubscriptions({
			cursor: false,
			envSubs: ["cloudbuild"],
			scope: "global",
		}),
		["cloudbuild", "legacy"],
	);
});

test("targetSid wins over sessionId", () => {
	assert.equal(
		resolveTargetSid(
			rec({ sessionId: "sess-a", extra: { targetSid: "sess-b" } }),
		),
		"sess-b",
	);
});

test("cursor does not auto-steer named lanes", () => {
	assert.equal(
		shouldSteerSelf({
			autoSteer: true,
			cursor: true,
			steerCursor: false,
			boundSid: "sess-here",
			inboxDir: inbox,
			filePath: named,
			record: rec(),
		}),
		false,
	);
});

test("own inbox steers the bound session", () => {
	assert.equal(
		shouldSteerSelf({
			autoSteer: true,
			cursor: false,
			steerCursor: false,
			boundSid: "sess-here",
			inboxDir: inbox,
			filePath: own,
			record: rec(),
		}),
		true,
	);
	assert.equal(isInboxPath(own, inbox), true);
	assert.equal(isInboxPath(named, inbox), false);
});

test("foreign targetSid never steers this session", () => {
	assert.equal(
		shouldSteerSelf({
			autoSteer: true,
			cursor: false,
			steerCursor: true,
			boundSid: "sess-here",
			inboxDir: inbox,
			filePath: own,
			record: rec({ targetSid: "sess-other" }),
		}),
		false,
	);
});

test("named stream with matching targetSid steers that pi session", () => {
	assert.equal(
		shouldSteerSelf({
			autoSteer: true,
			cursor: false,
			steerCursor: false,
			boundSid: "sess-here",
			inboxDir: inbox,
			filePath: named,
			record: rec({ targetSid: "sess-here" }),
		}),
		true,
	);
});

test("pi named-stream without target or owner does not steer", () => {
	assert.equal(
		shouldSteerSelf({
			autoSteer: true,
			cursor: false,
			steerCursor: false,
			boundSid: "sess-here",
			inboxDir: inbox,
			filePath: named,
			record: rec(),
		}),
		false,
	);
});

test("named stream with matching ownerSid steers that pi session", () => {
	assert.equal(
		shouldSteerSelf({
			autoSteer: true,
			cursor: false,
			steerCursor: false,
			boundSid: "sess-here",
			inboxDir: inbox,
			filePath: named,
			record: rec({ ownerSid: "sess-here" }),
		}),
		true,
	);
});

test("cursor named-stream stays off even if steerCursor is on", () => {
	assert.equal(
		shouldSteerSelf({
			autoSteer: true,
			cursor: true,
			steerCursor: true,
			boundSid: "sess-here",
			inboxDir: inbox,
			filePath: named,
			record: rec(),
		}),
		false,
	);
});

test("formatSteer is pointer/delta only", () => {
	const text = formatSteer(
		rec({
			task: "MONITOR ONLY. ".repeat(80),
			message: "0717Z harvested",
			targetSid: "sess-here",
			statusPath: "/tmp/job-1.status.json",
			eventsPath: "/tmp/job-1/events.jsonl",
		}),
	);
	assert.equal(text, "job=job-1 stream=subagent status=succeeded");
	assert.doesNotMatch(text, /MONITOR ONLY/);
	assert.doesNotMatch(text, /0717Z harvested/);
	assert.doesNotMatch(text, /target=/);
	assert.doesNotMatch(text, /events=/);
	assert.doesNotMatch(text, /Continue the implementor/);
});

function decision(over: Partial<SteerDecisionInput> = {}): SteerDecisionInput {
	return {
		autoSteer: true,
		cursor: false,
		steerCursor: false,
		boundSid: "sess-here",
		inboxDir: inbox,
		filePath: own,
		record: rec(),
		...over,
	};
}

test("classifyDelivery: heartbeat is none; running is display; terminal inbox is steer", () => {
	assert.equal(isTerminalStatus("running"), false);
	assert.equal(isTerminalStatus("succeeded"), true);
	assert.equal(
		classifyDelivery(decision({ record: rec({ type: "job.heartbeat", status: "running" }) })).kind,
		"none",
	);
	assert.equal(
		classifyDelivery(decision({ record: rec({ type: "job.started", status: "running" }) })).kind,
		"display",
	);
	assert.equal(classifyDelivery(decision({ record: rec({ status: "succeeded" }) })).kind, "steer");
	assert.equal(
		classifyDelivery(
			decision({
				filePath: named,
				record: rec({ status: "succeeded" }),
			}),
		).kind,
		"display",
	);
	assert.equal(
		classifyDelivery(
			decision({
				filePath: named,
				record: rec({ status: "failed", targetSid: "sess-here" }),
			}),
		).kind,
		"steer",
	);
	assert.equal(
		classifyDelivery({
			...decision({
				filePath: named,
				record: rec({ status: "failed" }),
			}),
			implementorSid: "sess-other",
		}).kind,
		"steer",
	);
});

test("formatSteer includes project when stamped", () => {
	assert.equal(
		formatSteer(rec({ project: "cartesia-security" })),
		"job=job-1 stream=subagent project=cartesia-security status=succeeded",
	);
});

test("classifyDelivery: foreign project named lane is none unless path is that project bus", () => {
	assert.equal(
		classifyDelivery(
			decision({
				filePath: named,
				boundProject: "cartesia-security",
				record: rec({ status: "succeeded", project: "gypsum", targetSid: "sess-here" }),
			}),
		).kind,
		"none",
	);
	assert.equal(
		classifyDelivery(
			decision({
				filePath: "/home/karan/.pi/agent/jobs/projects/gypsum/streams/subagent/job-1.status.json",
				boundProject: "cartesia-security",
				record: rec({ status: "succeeded", project: "gypsum", targetSid: "sess-here" }),
			}),
		).kind,
		"steer",
	);
	assert.equal(
		classifyDelivery(
			decision({
				filePath: own,
				boundProject: "cartesia-security",
				record: rec({ status: "succeeded", project: "gypsum" }),
			}),
		).kind,
		"steer",
	);
});

test("formatPointerBatch coalesces and stays pointer-only", () => {
	const text = formatPointerBatch([
		rec({ jobId: "job-a", status: "succeeded", task: "DUMP".repeat(40) }),
		rec({ jobId: "job-a", status: "succeeded" }),
		rec({ jobId: "job-b", status: "failed", message: "long stderr" }),
	]);
	assert.match(text, /2 terminal updates/);
	assert.match(text, /job=job-a stream=subagent status=succeeded/);
	assert.match(text, /job=job-b stream=subagent status=failed/);
	assert.doesNotMatch(text, /DUMP/);
	assert.doesNotMatch(text, /long stderr/);
});
