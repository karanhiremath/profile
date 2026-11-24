import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { ackPaths, ackReport, emptyAck } from "./job-bus-ack.ts";
import { isTerminalStatus } from "./job-bus-target.ts";

test("compact ACK counts unique newly acknowledged jobs and reports pending transitions", () => {
	const dir = mkdtempSync(join(tmpdir(), "ack-report-"));
	try {
		const paths = ["a", "mirror", "running", "failed"].map((file) => join(dir, file));
		const records = [
			{ jobId: "a", status: "running", type: "job.started" },
			{ jobId: "a", status: "running", type: "job.started" },
			{ jobId: "b", status: "running", type: "job.started" },
			{ jobId: "c", status: "failed", type: "job.failed" },
		];
		paths.forEach((p, i) => writeFileSync(p, JSON.stringify(records[i])));
		const read = (path: string) => records[paths.indexOf(path)];
		const before = emptyAck("consumer");
		const after = ackPaths(before, paths.slice(0, 2), read);
		assert.deepEqual(ackReport(before, after, paths, read, isTerminalStatus), { acked: 1, running: ["b"], terminal: ["c"] });
		assert.equal(ackReport(after, after, paths, read, isTerminalStatus).acked, 0);
		records[0] = { jobId: "a", status: "succeeded", type: "job.finished" };
		writeFileSync(paths[0], JSON.stringify(records[0]));
		assert.deepEqual(ackReport(after, after, paths, read, isTerminalStatus).terminal, ["a", "c"]);
	} finally {
		rmSync(dir, { recursive: true, force: true });
	}
});
