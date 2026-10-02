import { test } from "node:test";
import assert from "node:assert/strict";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import {
	filterTools,
	granolaAllowed,
	isGranolaTool,
	loadManifest,
	resolveProfile,
} from "./resolve.ts";

const manifest = loadManifest(
	join(fileURLToPath(new URL(".", import.meta.url)), "..", "manifests", "profiles.json"),
);

test("worker is implementor and granola is denied", () => {
	const profile = resolveProfile(manifest, { agent: "worker", cwd: "/tmp/cartesia-security-worktrees/x" });
	assert.equal(profile.className, "implementor");
	assert.equal(granolaAllowed(profile), false);
	assert.deepEqual(
		filterTools(profile, ["read", "query_granola_meetings", "list_meetings", "bash"]),
		["read", "bash"],
	);
});

test("work-notes-librarian allows granola on skill", () => {
	const profile = resolveProfile(manifest, { agent: "work-notes-librarian" });
	assert.equal(profile.className, "librarian");
	assert.equal(granolaAllowed(profile), true);
	assert.deepEqual(
		filterTools(profile, ["read", "query_granola_meetings"]),
		["read", "query_granola_meetings"],
	);
});

test("granola-notetaker is the notetaker class", () => {
	const profile = resolveProfile(manifest, { agent: "granola-notetaker" });
	assert.equal(profile.className, "notetaker");
	assert.equal(granolaAllowed(profile), true);
});

test("cartesia-security cwd defaults implementor even without agent", () => {
	const profile = resolveProfile(manifest, { cwd: "/home/x/src/cartesia-security-worktrees/il5" });
	assert.equal(profile.className, "implementor");
	assert.equal(granolaAllowed(profile), false);
});

test("isGranolaTool matches bridged MCP names", () => {
	assert.equal(isGranolaTool("mcp__plugin-granola-granola__query_granola_meetings"), true);
	assert.equal(isGranolaTool("read"), false);
});
