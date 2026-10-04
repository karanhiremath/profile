import { test } from "node:test";
import assert from "node:assert/strict";
import { isolatedChildEnv, isHostPaneEnvKey } from "./pi-invocation.ts";

test("isolatedChildEnv strips owner pane/tmux/herdr bind and keeps resume opt-out", () => {
	const env = isolatedChildEnv(
		{
			HERDR_ENV: "1",
			HERDR_PANE_ID: "ws:p1",
			HERDR_TAB_ID: "ws:t1",
			TMUX: "/tmp/tmux-501/default,1,0",
			TMUX_PANE: "%3",
			PI_SESSION_ID: "owner-sid",
			PI_FLEET_WORKSPACE: "/tmp/fleet.json",
			PATH: "/usr/bin",
			CURSOR_AGENT: "1",
		},
		{ PI_CURSOR_LOCAL_RESUME: "0" },
	);
	assert.equal(env.HERDR_ENV, undefined);
	assert.equal(env.HERDR_PANE_ID, undefined);
	assert.equal(env.TMUX, undefined);
	assert.equal(env.TMUX_PANE, undefined);
	assert.equal(env.PI_SESSION_ID, undefined);
	assert.equal(env.PI_FLEET_WORKSPACE, undefined);
	assert.equal(env.CURSOR_AGENT, undefined);
	assert.equal(env.PATH, "/usr/bin");
	assert.equal(env.PI_CURSOR_LOCAL_RESUME, "0");
	assert.equal(env.PI_JOB_BUS_STEER_SELF, "0");
	assert.equal(isHostPaneEnvKey("HERDR_PANE_ID"), true);
	assert.equal(isHostPaneEnvKey("PATH"), false);
});

test("handoff spawn extras mark the child so it cannot re-enter the owner lane", () => {
	const env = isolatedChildEnv(
		{ HERDR_PANE_ID: "ws:p1" },
		{
			PI_CURSOR_LOCAL_RESUME: "0",
			PI_HANDOFF_CHILD: "1",
			PI_HANDOFF_STEER_MODE: "headless",
			PI_FLEET_COMMS: "0",
		},
	);
	assert.equal(env.PI_HANDOFF_CHILD, "1");
	assert.equal(env.PI_HANDOFF_STEER_MODE, "headless");
	assert.equal(env.PI_FLEET_COMMS, "0");
	assert.equal(env.HERDR_PANE_ID, undefined);
});
