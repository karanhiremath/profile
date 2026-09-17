import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";
import assert from "node:assert/strict";
import {
	applyHandoffPacketPatch,
	isRateLimited,
	maybeMoaPatch,
	NEXT_MAX,
	sanitizeHandoffPacketPatch,
} from "./handoff-moa.ts";
import {
	DEFAULT_TUNE,
	HANDOFF_MOA_FLAG,
	registerHandoffMoaFlag,
	sessionMoaEnabled,
} from "./handoff-session-tune.ts";
import { persistReadySnapshot } from "./handoff-moa-wire.ts";
import { persistFromContextReadySync } from "./handoff-persist.ts";
import { switchComplete } from "./handoff-pointer-schema.ts";
import { persistSessionTune, loadSessionTune, tuneSidecarPath } from "./handoff-session-tune.ts";

const tmp = mkdtempSync(join(tmpdir(), "handoff-moa-"));
after(() => {
	rmSync(tmp, { recursive: true, force: true });
});

const base = {
	objective: "keep going",
	next: ["write stubs"],
	blockers: ["inventory yes"],
};

test("moa off is identity and does not call", async () => {
	let called = 0;
	const result = await maybeMoaPatch({
		moa: false,
		snapshot: base,
		call: async () => {
			called += 1;
			return { objective: "nope" };
		},
	});
	assert.equal(result.moa, "off");
	assert.equal(called, 0);
	assert.deepEqual(result.snapshot, base);
});

test("patch keeps only objective / next / blockers", () => {
	const patch = sanitizeHandoffPacketPatch({
		objective: "ship stubs",
		next: ["a", "b"],
		blockers: ["gpt-6 spawn"],
		novel: "dump the transcript",
		files_read: ["/etc/passwd"],
	});
	assert.deepEqual(patch, {
		objective: "ship stubs",
		next: ["a", "b"],
		blockers: ["gpt-6 spawn"],
	});
	assert.deepEqual(applyHandoffPacketPatch(base, patch), {
		objective: "ship stubs",
		next: ["a", "b"],
		blockers: ["gpt-6 spawn"],
	});
});

test("novel-only payload is discarded", async () => {
	const result = await maybeMoaPatch({
		moa: true,
		snapshot: base,
		call: async () => ({ transcript: "full dump", essay: "…" }),
	});
	assert.equal(result.moa, "discarded");
	assert.deepEqual(result.snapshot, base);
});

test("429 stops and keeps the deterministic snapshot", async () => {
	const result = await maybeMoaPatch({
		moa: true,
		snapshot: base,
		call: async () => {
			throw { status: 429, message: "rate limited" };
		},
	});
	assert.equal(result.moa, "stopped-429");
	assert.deepEqual(result.snapshot, base);
	assert.equal(isRateLimited({ statusCode: 429 }), true);
});

test("next is capped", () => {
	const patch = sanitizeHandoffPacketPatch({
		next: Array.from({ length: 20 }, (_, i) => `step ${i}`),
	});
	assert.equal(patch?.next?.length, NEXT_MAX);
});

test("wire helper is identity when flag/tune moa is off", async () => {
	const snapshot = await persistReadySnapshot({
		sessionId: "no-sidecar",
		snapshot: base,
		flag: false,
		call: async () => ({ objective: "should not apply" }),
	});
	assert.deepEqual(snapshot, base);
});

test("flag default is off; env/flag can enable", () => {
	assert.equal(DEFAULT_TUNE.moa, false);
	assert.equal(HANDOFF_MOA_FLAG, "handoff-moa");
	assert.equal(sessionMoaEnabled({ sessionId: "s", flag: false, env: { PI_HANDOFF_MOA: "1" } }), false);
	assert.equal(sessionMoaEnabled({ sessionId: "s", flag: true }), true);
	const flags: string[] = [];
	registerHandoffMoaFlag({
		registerFlag: (name) => {
			flags.push(name);
		},
	});
	assert.deepEqual(flags, [HANDOFF_MOA_FLAG]);
});

test("persistFromContextReadySync is identity when moa off", () => {
	let persisted: typeof base | undefined;
	const result = persistFromContextReadySync({
		sessionId: "no-sidecar",
		snapshot: base,
		flag: false,
		persist: (snapshot) => {
			persisted = snapshot;
			return { path: "/tmp/pointer.json" };
		},
	});
	assert.deepEqual(result.snapshot, base);
	assert.equal(result.path, "/tmp/pointer.json");
	assert.deepEqual(persisted, base);
});

test("switchComplete requires phase + successor_id + switched_at", () => {
	assert.equal(switchComplete({ phase: "successor", successor_id: "c", switched_at: "t" }), false);
	assert.equal(switchComplete({ phase: "switch", successor_id: null, switched_at: "t" }), false);
	assert.equal(switchComplete({ phase: "switch", successor_id: "c", switched_at: undefined }), false);
	assert.equal(switchComplete({ phase: "switch", successor_id: "c", switched_at: "t" }), true);
});

test("tune sidecar persists snake_case", () => {
	const prev = process.env.HOME;
	process.env.HOME = tmp;
	try {
		const saved = persistSessionTune("sid-snake", { kind: "planning", moa: false, lane: "pointer" });
		assert.equal(saved.prepare_percent, 30);
		assert.equal(saved.kind, "planning");
		const loaded = loadSessionTune("sid-snake");
		assert.equal(loaded.kind, "planning");
		assert.match(tuneSidecarPath("sid-snake"), /sid-snake\.tune\.json$/);
		const raw = JSON.parse(readFileSync(tuneSidecarPath("sid-snake"), "utf8"));
		assert.equal(raw.prepare_percent, 30);
		assert.equal(raw.preparePercent, undefined);
	} finally {
		process.env.HOME = prev;
	}
});
