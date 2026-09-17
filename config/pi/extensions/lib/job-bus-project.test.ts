import { test } from "node:test";
import assert from "node:assert/strict";
import {
	isForeignProjectFile,
	parseWatchToken,
	projectLaneDir,
	projectSlug,
	recordProject,
	resolveJobProject,
	slugFromCwd,
	watchDirsForSubscriptions,
} from "./job-bus-project.ts";

test("slugFromCwd maps src repo and worktrees to one project", () => {
	assert.equal(slugFromCwd("/home/x/src/cartesia-security"), "cartesia-security");
	assert.equal(slugFromCwd("/home/x/src/cartesia-security-worktrees/il5"), "cartesia-security");
	assert.equal(slugFromCwd("/home/x/src/cartesia-security/scripts/infra"), "cartesia-security");
	assert.equal(slugFromCwd("/home/x/src/forge-worktrees/fips-runtime"), "forge");
	assert.equal(slugFromCwd("/home/x/src/gypsum"), "gypsum");
	assert.equal(slugFromCwd("/home/karan.hiremath", { gitExists: () => false }), "unscoped");
	assert.equal(slugFromCwd(""), "unscoped");
});

test("PI_JOB_PROJECT overrides session cwd; job cwd wins on write", () => {
	assert.equal(projectSlug("/home/x/src/gypsum", { PI_JOB_PROJECT: "cartesia-security" }), "cartesia-security");
	assert.equal(
		resolveJobProject({ cwd: "/home/x/src/cartesia-security" }, { PI_JOB_PROJECT: "gypsum" }),
		"cartesia-security",
	);
	assert.equal(resolveJobProject({ project: "explicit", cwd: "/home/x/src/gypsum" }), "explicit");
	assert.equal(
		resolveJobProject({ cwd: "/tmp/no-repo" }, { PI_JOB_PROJECT: "home-bus" }, { gitExists: () => false }),
		"home-bus",
	);
	assert.equal(resolveJobProject({}), "unscoped");
});

test("parseWatchToken: bare lane is this project; global and project tokens stay explicit", () => {
	assert.deepEqual(parseWatchToken("subagent", "cartesia-security"), {
		kind: "lane",
		lane: "subagent",
		project: "cartesia-security",
		global: false,
	});
	assert.deepEqual(parseWatchToken("stream:cloudbuild", "gypsum"), {
		kind: "lane",
		lane: "cloudbuild",
		project: "gypsum",
		global: false,
	});
	assert.deepEqual(parseWatchToken("global:subagent", "cartesia-security"), {
		kind: "lane",
		lane: "subagent",
		project: "",
		global: true,
	});
	assert.deepEqual(parseWatchToken("project:gypsum/subagent", "cartesia-security"), {
		kind: "lane",
		lane: "subagent",
		project: "gypsum",
		global: false,
	});
	assert.deepEqual(parseWatchToken("project:gypsum:assembler", "cartesia-security"), {
		kind: "lane",
		lane: "assembler",
		project: "gypsum",
		global: false,
	});
	assert.deepEqual(parseWatchToken("project:gypsum", "cartesia-security"), {
		kind: "lane",
		lane: "*",
		project: "gypsum",
		global: false,
	});
	assert.deepEqual(parseWatchToken("legacy", "cartesia-security"), { kind: "legacy" });
	assert.deepEqual(parseWatchToken("session:sess-a", "cartesia-security"), { kind: "session", sid: "sess-a" });
});

test("subscribe subagent watches this project only, never host-global streams", () => {
	const jobsRoot = "/home/x/.pi/agent/jobs";
	const inbox = `${jobsRoot}/sessions/sess-here`;
	const dirs = watchDirsForSubscriptions({
		inboxDir: inbox,
		jobsRoot,
		boundProject: "cartesia-security",
		subscriptions: ["subagent"],
	});
	assert.deepEqual(dirs, [
		inbox,
		projectLaneDir("cartesia-security", "subagent", jobsRoot),
	]);
	assert.ok(!dirs.some((d) => d === `${jobsRoot}/streams/subagent`));
	assert.ok(!dirs.some((d) => d.includes("/projects/gypsum/")));
});

test("foreign project and legacy tokens resolve to those trees only", () => {
	const jobsRoot = "/home/x/.pi/agent/jobs";
	const inbox = `${jobsRoot}/sessions/sess-here`;
	const listed = watchDirsForSubscriptions({
		inboxDir: inbox,
		jobsRoot,
		boundProject: "cartesia-security",
		subscriptions: ["project:gypsum/subagent", "global:assembler", "legacy"],
		listChildren: () => ["assembler", "subagent"],
	});
	assert.ok(listed.includes(inbox));
	assert.ok(listed.includes(projectLaneDir("gypsum", "subagent", jobsRoot)));
	assert.ok(listed.includes(`${jobsRoot}/streams/assembler`));
	assert.ok(listed.includes(jobsRoot));
	assert.ok(!listed.includes(projectLaneDir("cartesia-security", "subagent", jobsRoot)));
});

test("isForeignProjectFile allows inbox and explicit project path", () => {
	const inbox = "/home/x/.pi/agent/jobs/sessions/sess-here";
	assert.equal(
		isForeignProjectFile({
			filePath: `${inbox}/job.status.json`,
			inboxDir: inbox,
			boundProject: "cartesia-security",
			recordProject: "gypsum",
		}),
		false,
	);
	assert.equal(
		isForeignProjectFile({
			filePath: "/home/x/.pi/agent/jobs/projects/gypsum/streams/subagent/job.status.json",
			inboxDir: inbox,
			boundProject: "cartesia-security",
			recordProject: "gypsum",
		}),
		false,
	);
	assert.equal(
		isForeignProjectFile({
			filePath: "/home/x/.pi/agent/jobs/streams/subagent/job.status.json",
			inboxDir: inbox,
			boundProject: "cartesia-security",
			recordProject: "gypsum",
		}),
		true,
	);
	assert.equal(recordProject({ project: "gypsum" }), "gypsum");
});
