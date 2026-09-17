import { mkdirSync, mkdtempSync, writeFileSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";
import assert from "node:assert/strict";
import {
	ackPaths,
	emptyAck,
	fingerprint,
	isAcked,
	loadAck,
	pendingPaths,
	saveAck,
	seenMapFromAck,
} from "./job-bus-ack.ts";

const tmp = mkdtempSync(join(tmpdir(), "job-bus-ack-"));
after(() => {
	rmSync(tmp, { recursive: true, force: true });
});

function writeStatus(dir: string, jobId: string, status: string, ts: string): string {
	mkdirSync(dir, { recursive: true });
	const path = join(dir, `${jobId}.status.json`);
	writeFileSync(path, `${JSON.stringify({ jobId, status, type: `job.${status}`, ts }, null, 2)}\n`);
	return path;
}

function read(path: string) {
	return JSON.parse(readFileSync(path, "utf8"));
}

test("duplicate poll does not retrigger after ack", () => {
	const inbox = join(tmp, "sess-a");
	const file = writeStatus(inbox, "job-1", "succeeded", "t1");
	let state = ackPaths(emptyAck("sess-a"), [file], read);
	saveAck(inbox, state);
	state = loadAck(inbox, "sess-a");
	assert.deepEqual(pendingPaths(state, [file], read), []);
	assert.deepEqual(pendingPaths(state, [file], read), []);
	assert.equal(isAcked(state, file, read(file)), true);
});

test("same status rewrite is not pending after ack", () => {
	const inbox = join(tmp, "sess-same");
	const file = writeStatus(inbox, "job-same", "running", "t1");
	let state = ackPaths(emptyAck("sess-same"), [file], read);
	saveAck(inbox, state);
	writeStatus(inbox, "job-same", "running", "t-heartbeat");
	state = loadAck(inbox, "sess-same");
	assert.deepEqual(pendingPaths(state, [file], read), []);
	assert.equal(isAcked(state, file, read(file)), true);
});

test("ack advances cursor; new fingerprint is pending", () => {
	const inbox = join(tmp, "sess-b");
	const file = writeStatus(inbox, "job-2", "running", "t1");
	let state = ackPaths(emptyAck("sess-b"), [file], read);
	saveAck(inbox, state);
	assert.deepEqual(pendingPaths(loadAck(inbox, "sess-b"), [file], read), []);
	const before = fingerprint(file);
	writeStatus(inbox, "job-2", "succeeded", "t2");
	assert.notEqual(fingerprint(file), before);
	state = loadAck(inbox, "sess-b");
	assert.deepEqual(pendingPaths(state, [file], read), [file]);
	state = ackPaths(state, [file], read);
	saveAck(inbox, state);
	assert.deepEqual(pendingPaths(loadAck(inbox, "sess-b"), [file], read), []);
});

test("inbox and named-stream copies of the same event ack once", () => {
	const inbox = join(tmp, "sess-cross");
	const named = join(tmp, "stream-cross");
	const a = writeStatus(inbox, "job-shared", "succeeded", "t1");
	const b = writeStatus(named, "job-shared", "succeeded", "t-other");
	let state = ackPaths(emptyAck("sess-cross"), [a], read);
	saveAck(inbox, state);
	state = loadAck(inbox, "sess-cross");
	assert.deepEqual(pendingPaths(state, [a, b], read), []);
	writeStatus(named, "job-shared", "succeeded", "t-rewritten");
	assert.deepEqual(pendingPaths(loadAck(inbox, "sess-cross"), [b], read), []);
	writeStatus(named, "job-shared", "failed", "t3");
	assert.deepEqual(pendingPaths(loadAck(inbox, "sess-cross"), [b], read), [b]);
});

test("two consumers ack independently", () => {
	const a = join(tmp, "consumer-a");
	const b = join(tmp, "consumer-b");
	const named = join(tmp, "stream");
	const file = writeStatus(named, "job-shared", "succeeded", "t1");
	const stateA = ackPaths(emptyAck("consumer-a"), [file], read);
	saveAck(a, stateA);
	assert.deepEqual(pendingPaths(loadAck(a, "consumer-a"), [file], read), []);
	assert.deepEqual(pendingPaths(loadAck(b, "consumer-b"), [file], read), [file]);
	saveAck(b, ackPaths(emptyAck("consumer-b"), [file], read));
	assert.deepEqual(pendingPaths(loadAck(b, "consumer-b"), [file], read), []);
	assert.notEqual(join(a, ".ack.json"), join(b, ".ack.json"));
	assert.equal(seenMapFromAck(loadAck(a, "consumer-a")).get(file), fingerprint(file));
});
