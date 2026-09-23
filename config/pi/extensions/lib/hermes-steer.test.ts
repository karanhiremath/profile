import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
	classifyFailure,
	heartbeatRoots,
	inboxPaths,
	isHermesSeat,
	isProtectedSeat,
	listHeartbeats,
	planHermesTransport,
	recoveryPrompt,
	tryAcquireLock,
	writeHermesInbox,
} from "./hermes-steer.ts";

test("classify interrupt and cursor-sdk failures", () => {
	assert.equal(classifyFailure("status: interrupted"), "interrupted");
	assert.equal(classifyFailure("This operation was aborted"), "cursor-sdk");
	assert.equal(classifyFailure("subagent failed"), "subagent-failed");
	assert.equal(classifyFailure("Ready"), null);
	assert.match(recoveryPrompt("interrupted"), /interrupted/);
});

test("tmux/proc sids plan hermes-tui transport", () => {
	assert.equal(planHermesTransport("hermes", "tmux:cosw:0.3").transport, "hermes-tui");
	assert.equal(planHermesTransport("herm-tui", "sess-1").transport, "hermes-tui");
	assert.equal(planHermesTransport("hermes", "run-1").transport, "hermes-http");
});

test("writeHermesInbox writes session and tmux files", () => {
	const home = mkdtempSync(join(tmpdir(), "pi-hermes-steer-"));
	const ident = {
		hermes_home: home,
		session_id: "sess-1",
		control_port: 0,
		pid: "9",
		tmux_target: "cosw:0.3",
	};
	const paths = writeHermesInbox(ident, "continue after interrupt", { mode: "nudge", source: "test" });
	assert.ok(paths.length >= 2);
	assert.deepEqual(inboxPaths(ident).sort(), [...paths].sort());
	const raw = readFileSync(paths[0], "utf8");
	assert.match(raw, /continue after interrupt/);
	assert.match(raw, /nudge/);
	rmSync(home, { recursive: true, force: true });
});

test("empty or corrupt lock is stealable", () => {
	const dir = mkdtempSync(join(tmpdir(), "pi-fleet-lock-"));
	const lock = join(dir, "fleet-nudge.lock");
	writeFileSync(lock, "");
	assert.equal(tryAcquireLock(lock, 11, 1, () => true), true);
	writeFileSync(lock, "{not-json");
	assert.equal(tryAcquireLock(lock, 12, 2, () => true), true);
	assert.equal(tryAcquireLock(lock, 13, 3, (pid) => pid === 12), false);
	assert.equal(tryAcquireLock(lock, 14, 4, () => false), true);
	rmSync(dir, { recursive: true, force: true });
});

test("listHeartbeats finds COSW profile live dir under hermes-agents", () => {
	const home = mkdtempSync(join(tmpdir(), "pi-hermes-beats-"));
	const cosw = join(home, ".local/share/hermes-agents/chief-of-staff-work/profiles/chief-of-staff-work");
	const live = join(cosw, "steer-inbox/live");
	mkdirSync(live, { recursive: true });
	writeFileSync(
		join(live, `${process.pid}.json`),
		JSON.stringify({
			pid: process.pid,
			session_id: "sess-o2",
			hermes_home: cosw,
			tmux_target: "cosw-o2:0.1",
			socket_path: `/run/user/2005/herm-tui-${process.pid}.sock`,
		}),
	);
	writeFileSync(
		join(live, "dead.json"),
		JSON.stringify({ pid: 2147483000, tmux_target: "cosw-o2:0.0", session_id: "dead" }),
	);
	assert.ok(heartbeatRoots(home).some((root) => root.endsWith("chief-of-staff-work")));
	const beats = listHeartbeats(home);
	assert.equal(beats.length, 1);
	assert.equal(beats[0].tmux_target, "cosw-o2:0.1");
	assert.equal(beats[0].pid, String(process.pid));
	rmSync(home, { recursive: true, force: true });
});

test("isHermesSeat matches COSW bun/node hog panes", () => {
	assert.equal(isHermesSeat("bun", "workhost-1", "cosw-o2:0.1"), true);
	assert.equal(isHermesSeat("node", "workhost-1", "cosw:0.1"), true);
	assert.equal(isHermesSeat("btop", "π", "cosw:0.0"), false);
	assert.equal(isHermesSeat("pi", "π", "cosw:0.3"), false);
	assert.equal(isHermesSeat("bun", "other", "sagemaker:0.0"), false);
	assert.equal(isProtectedSeat("cosw-o1:0.0"), true);
	assert.equal(isProtectedSeat("cosw-o2:0.1"), false);
	assert.equal(isProtectedSeat("cosw-yoshi:0.0"), true);
	assert.equal(isProtectedSeat("cosw:0.0"), true);
	assert.equal(isProtectedSeat("cosw:0.2"), false);
});
