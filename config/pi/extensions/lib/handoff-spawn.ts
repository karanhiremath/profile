/**
 * Detached pi print-turn spawn. No SessionManager — safe for Cursor hooks.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { getPiInvocation, spawnDetachedJobWaiter } from "../subagent/pi-invocation.ts";
import {
	defaultStreamName,
	ensureJobDir,
	eventsPathFor,
	extraBusPath,
	namedStreamDir,
	newJobId,
	statusPathFor,
	streamPath,
	writeJobRecord,
} from "../subagent/jobs.ts";
import { resolveJobProject } from "./job-bus-project.ts";

export function spawnHandoffPrintTurn(input: {
	cwd: string;
	sessionFile: string;
	prompt: string;
	source?: string;
}): { jobId: string } {
	const source = input.source || "handoff";
	const jobId = newJobId(source.startsWith("handoff") ? "handoff" : source);
	const dir = ensureJobDir(jobId);
	const stdoutPath = join(dir, "stdout.jsonl");
	const stderrPath = join(dir, "stderr.log");
	const metaPath = join(dir, "meta.json");
	const runner = join(dirname(fileURLToPath(import.meta.url)), "..", "subagent", "job-runner.mjs");
	const args = ["--mode", "json", "-p", "--session", input.sessionFile, input.prompt];
	const invocation = getPiInvocation(args);
	const streamName = defaultStreamName(source, jobId);
	const project = resolveJobProject({ cwd: input.cwd });
	const meta = {
		schema: "pi.job-watcher.v1",
		jobId,
		source,
		stream: streamName,
		project,
		task: input.prompt.slice(0, 240),
		cwd: input.cwd,
		stdoutPath,
		stderrPath,
		statusPath: statusPathFor(jobId),
		eventsPath: eventsPathFor(jobId),
		namedStreamDir: namedStreamDir(streamName, homedir(), project),
		streamPath: streamPath(),
		busPath: extraBusPath() || "",
	};
	mkdirSync(dir, { recursive: true });
	writeFileSync(metaPath, `${JSON.stringify(meta, null, 2)}\n`);
	writeJobRecord({
		schema: "pi.job-watcher.v1",
		jobId,
		source,
		type: "job.started",
		status: "running",
		stream: streamName,
		project,
		task: meta.task,
		cwd: input.cwd,
		ts: new Date().toISOString(),
		stdoutPath,
		stderrPath,
		message:
			source === "handoff-successor"
				? "handoff successor worker; owner session stays"
				: "handoff sibling warm-up; owner session stays",
	});
	const spawned = spawnDetachedJobWaiter({
		runner,
		jobId,
		requestedCwd: input.cwd,
		fallbackCwd: process.cwd(),
		command: invocation.command,
		args: invocation.args,
		metaPath,
		onSpawnError: (err) => {
			writeJobRecord({
				schema: "pi.job-watcher.v1",
				jobId,
				source,
				type: "job.failed",
				status: "failed",
				stream: streamName,
				project,
				task: meta.task,
				cwd: input.cwd,
				ts: new Date().toISOString(),
				stdoutPath,
				stderrPath,
				exitCode: 127,
				message: String(err),
			});
		},
	});
	if (spawned.missingCwd) {
		writeJobRecord({
			schema: "pi.job-watcher.v1",
			jobId,
			source,
			type: "job.failed",
			status: "failed",
			stream: streamName,
			project,
			task: meta.task,
			cwd: input.cwd,
			ts: new Date().toISOString(),
			stdoutPath,
			stderrPath,
			exitCode: 127,
			message: `cwd does not exist: ${spawned.missingCwd}`,
		});
	}
	return { jobId };
}
