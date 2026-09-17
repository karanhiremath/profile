import { existsSync, mkdtempSync, readFileSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";
import assert from "node:assert/strict";
import {
	HANDOFF_PROMPT_MAX_CHARS,
	POINTER_MAX_CHARS,
	SNAPSHOT_MAX_BYTES,
	SNAPSHOT_SCHEMA,
	buildSnapshot,
	CONTINUE_NOW,
	formatContinueWorkerTask,
	formatHandoffPrompt,
	formatPointerSummary,
	inferHandoffKind,
	parseHandoffArgs,
	resolveLimits,
	shouldAutoContinue,
	snapshotJson,
	writeSnapshot,
	applyPreviousSnapshot,
	continueInjectOptions,
	compactInterceptAction,
	formatHandoffNowCommand,
	inCompactCooldown,
	preferHandoffAfterCompact,
	shouldCancelInPlaceCompact,
	isCompactMetaUser,
	isHarnessRedirect,
	readSnapshot,
	afterCompactTriage,
	applyHandoffSwitchEffects,
	describeHandoffSwitchEffects,
	formatHandoffAlignPrompt,
	formatHandoffPrepareCommand,
	formatHandoffPreparePrompt,
	handoffChildReady,
	handoffSwitchAction,
	handoffSwitchPresentation,
	handoffSwitchReady,
	handoffSwitchTarget,
	planHandoffLane,
	shouldFallbackHandoffPrompt,
	shouldFallbackNewSession,
	shouldInjectContinueAfterLane,
	shouldInjectHandoffPrompt,
	shouldPushOwnerEditorOnDefer,
	shouldQueueHandoffNowAfterSwitch,
	shouldSpawnHandoffWarmup,
	shouldCreateHandoffSibling,
	handoffPrepInFlight,
	shouldOpenNewHandoffSession,
	keepLiveHandoffChild,
	tryClaimHandoffPrep,
	sessionSteerMode,
	sessionUuidFromId,
	isHandoffChildSession,
	resolveLiveHandoffPrep,
	writeHandoffPrep,
	writeHandoffPrepAliases,
	readHandoffPrep,
	readHandoffPrepAny,
	ownerSessionIds,
	handoffPrepPathForSession,
	estimateContextPercent,
	handoffLaneSettled,
	HANDOFF_PREP_SCHEMA,
} from "./compact-snapshot.ts";

const tmp = mkdtempSync(join(tmpdir(), "compact-snapshot-"));
after(() => {
	rmSync(tmp, { recursive: true, force: true });
});

function user(text: string) {
	return { type: "message", message: { role: "user", content: text } };
}

function assistant(text: string, tools?: Array<{ name: string; path: string }>) {
	const content: unknown[] = [{ type: "text", text }];
	for (const tool of tools ?? []) {
		content.push({ type: "toolCall", name: tool.name, arguments: { path: tool.path } });
	}
	return { type: "message", message: { role: "assistant", content } };
}

test("parseHandoffArgs strips --llm", () => {
	assert.deepEqual(parseHandoffArgs("--llm continue validation"), {
		llm: true,
		silent: false,
		kind: undefined,
		budgetPercent: undefined,
		goal: "continue validation",
	});
	assert.deepEqual(parseHandoffArgs("continue validation"), {
		llm: false,
		silent: false,
		kind: undefined,
		budgetPercent: undefined,
		goal: "continue validation",
	});
	assert.deepEqual(parseHandoffArgs("--type monitoring --budget 3 watch assembler"), {
		llm: false,
		silent: false,
		kind: "monitoring",
		budgetPercent: 3,
		goal: "watch assembler",
	});
	assert.deepEqual(parseHandoffArgs("--yes --type implementation ship the pointer"), {
		llm: false,
		silent: true,
		kind: "implementation",
		budgetPercent: undefined,
		goal: "ship the pointer",
	});
});

test("buildSnapshot keeps last users, files, and ids without the transcript", () => {
	const snapshot = buildSnapshot({
		branch: [
			user("ignore this huge prior handoff\n## Files to read first\n".repeat(50)),
			user("Fix job-bus isolation"),
			assistant("next: subscribe assembler", [
				{ name: "read", path: "scripts/infra/cbuild_job_bus.py" },
				{ name: "edit", path: "scripts/infra/cbuild_job_bus.py" },
			]),
			user(`Continue. case .csec/cases/gypsum-extimport-cutover-20260821 job subagent-1-abcd uuid 11111111-2222-4333-8444-555555555555 https://github.com/cartesia-ai/foo/pull/64`),
		],
		cwd: tmp,
		sessionId: "test-session",
		now: "2026-08-21T00:00:00.000Z",
	});
	assert.equal(snapshot.schema, SNAPSHOT_SCHEMA);
	assert.equal(snapshot.last_user.length <= 3, true);
	assert.equal(snapshot.last_user.some((item) => item.includes("Files to read first")), false);
	assert.deepEqual(snapshot.files_modified, ["scripts/infra/cbuild_job_bus.py"]);
	assert.equal(snapshot.case, ".csec/cases/gypsum-extimport-cutover-20260821");
	assert.ok(snapshot.jobs.some((job) => job.startsWith("subagent-")));
	assert.ok(snapshot.prs[0]?.includes("/pull/64"));
});

test("pointer and handoff stay tiny even when history is huge", () => {
	const huge = "x".repeat(50_000);
	const snapshot = buildSnapshot({
		branch: [user(huge), assistant(huge), user("ship the pointer mechanism")],
		goal: "make compact/handoff pointer-based",
		sessionId: "huge",
	});
	const pointer = formatPointerSummary(snapshot);
	const prompt = formatHandoffPrompt(snapshot, "make compact/handoff pointer-based");
	assert.ok(pointer.length <= POINTER_MAX_CHARS);
	assert.ok(prompt.length <= HANDOFF_PROMPT_MAX_CHARS);
	assert.ok(prompt.includes("Do not restate"));
	assert.ok(prompt.includes("Do not ask"));
	assert.ok(prompt.includes(snapshot.snapshot_path));
	assert.ok(!prompt.includes(huge));
	assert.ok(Buffer.byteLength(snapshotJson(snapshot), "utf8") <= SNAPSHOT_MAX_BYTES);
});

test("previous pointer summaries are not inlined", () => {
	const previous = [
		"schema: pi.compact-snapshot.v1",
		"snapshot: /tmp/prior.json",
		"objective: old work",
		"rule: Read the snapshot file.",
	].join("\n");
	const snapshot = buildSnapshot({
		branch: [{ type: "compaction", summary: previous, details: { snapshot_path: "/tmp/prior.json" } }],
		previousSummary: previous,
		sessionId: "linked",
	});
	assert.equal(snapshot.previous_snapshot, "/tmp/prior.json");
	assert.ok(!formatPointerSummary(snapshot).includes("old work restated"));
});

test("writeSnapshot persists json", () => {
	const snapshot = buildSnapshot({
		branch: [user("write me")],
		sessionId: "write-test",
		now: "2026-08-21T00:00:00.000Z",
	});
	snapshot.snapshot_path = join(tmp, "write-test.json");
	const path = writeSnapshot(snapshot);
	const parsed = JSON.parse(readFileSync(path, "utf8"));
	assert.equal(parsed.schema, SNAPSHOT_SCHEMA);
	assert.equal(parsed.objective.includes("write me"), true);
});

test("inferHandoffKind maps monitoring/planning/implementation", () => {
	assert.equal(inferHandoffKind("watch assembler"), "monitoring");
	assert.equal(inferHandoffKind("planning the next wave"), "planning");
	assert.equal(inferHandoffKind("fix the collector"), "implementation");
});

test("resolveLimits clamps budget to 5 percent of the window", () => {
	const capped = resolveLimits({ budgetPercent: 10, contextWindow: 256000 });
	assert.equal(capped.budgetPercent, 5);
	assert.ok(capped.budgetTokens <= 12800);
	const tight = resolveLimits({ budgetPercent: 0.5, contextWindow: 256000 });
	assert.ok(tight.promptMaxChars <= 800);
});

test("handoff prompt requires fire-and-forget gather", () => {
	const snapshot = buildSnapshot({
		branch: [user("watch assembler")],
		goal: "watch assembler",
		kind: "monitoring",
		sessionId: "monitor-test",
	});
	const prompt = formatHandoffPrompt(snapshot, "watch assembler");
	assert.match(prompt, /wait=false/);
	assert.match(prompt, /kind: monitoring/);
	assert.match(prompt, /job_bus|subscribe/i);
	assert.match(prompt, /Do not ask/);
});

test("implementation pull-up continues now instead of waiting for gather", () => {
	const snapshot = buildSnapshot({
		branch: [user("ship the lock-bearing PR")],
		goal: "ship the lock-bearing PR",
		kind: "implementation",
		sessionId: "impl-continue",
	});
	const pointer = formatPointerSummary(snapshot);
	const prompt = formatHandoffPrompt(snapshot, "ship the lock-bearing PR");
	const worker = formatContinueWorkerTask(snapshot);
	assert.match(pointer, new RegExp(CONTINUE_NOW));
	assert.match(pointer, /Execute next now/);
	assert.doesNotMatch(prompt, /Do not edit until gather/);
	assert.match(prompt, /Parent executes next in this same turn/);
	assert.match(prompt, /Do not wait for gather/);
	assert.match(prompt, /60%|handoff|Do not default to \/compact/);
	assert.match(prompt, /Do not ask/);
	assert.match(worker, /Execute:/);
	assert.match(worker, /Do not ask/);
});

test("shouldAutoContinue still injects on willRetry; only config can disable", () => {
	assert.equal(shouldAutoContinue({}), true);
	assert.equal(shouldAutoContinue({ autoContinue: true }), true);
	assert.equal(shouldAutoContinue({ autoContinue: false }), false);
	assert.equal(shouldAutoContinue({ willRetry: true }), true);
	assert.equal(shouldAutoContinue({ willRetry: true, autoContinue: true }), true);
	assert.equal(shouldAutoContinue({ willRetry: true, autoContinue: false }), false);
});

test("continueInjectOptions steers mid-retry and followUp when idle", () => {
	assert.deepEqual(continueInjectOptions({ willRetry: true }), {
		deliverAs: "steer",
		triggerTurn: true,
	});
	assert.deepEqual(continueInjectOptions({ idle: false }), {
		deliverAs: "steer",
		triggerTurn: true,
	});
	assert.deepEqual(continueInjectOptions({ idle: true }), {
		deliverAs: "followUp",
		triggerTurn: true,
	});
});

test("compact-meta users inherit previous objective; harness redirects do not", () => {
	assert.equal(isCompactMetaUser("what happened ehre???"), true);
	assert.equal(isHarnessRedirect("fix the compact continuation in the profile-level harness p0"), true);
	const previous = buildSnapshot({
		branch: [user("ship gypsum torch213 sbom")],
		goal: "ship gypsum torch213 sbom",
		sessionId: "prior-obj",
	});
	const current = buildSnapshot({
		branch: [user("what happened ehre???")],
		sessionId: "meta-obj",
	});
	const inherited = applyPreviousSnapshot(current, previous);
	assert.equal(inherited.objective.includes("gypsum torch213"), true);
	const redirect = applyPreviousSnapshot(
		buildSnapshot({
			branch: [user("p0: handoffs are preferred over compaction")],
			sessionId: "redir-obj",
		}),
		previous,
	);
	assert.equal(redirect.objective.includes("handoffs are preferred"), true);
	assert.ok(formatHandoffNowCommand(previous).startsWith("/handoff-now --type"));
	assert.equal(inCompactCooldown(Date.now() - 1000, 5000), true);
	assert.equal(inCompactCooldown(Date.now() - 10_000, 5000), false);
});

test("preferHandoff cancels in-place compact even on willRetry", () => {
	assert.equal(shouldCancelInPlaceCompact({ preferHandoff: true }), true);
	assert.equal(shouldCancelInPlaceCompact({ preferHandoff: false }), false);
	assert.equal(compactInterceptAction({ preferHandoff: true, handoffReady: true }), "handoff-cancel");
	assert.equal(compactInterceptAction({ preferHandoff: true, handoffReady: false }), "handoff-cancel");
	assert.equal(compactInterceptAction({ preferHandoff: false, handoffReady: true }), "pointer-compact");
	assert.equal(preferHandoffAfterCompact({ preferHandoff: true, willRetry: true }), true);
	assert.equal(preferHandoffAfterCompact({ preferHandoff: true, aborted: true }), true);
	assert.equal(preferHandoffAfterCompact({ preferHandoff: false, willRetry: true }), false);
	const snapshot = buildSnapshot({
		branch: [user("ship the pointer")],
		goal: "ship the pointer",
		kind: "implementation",
		sessionId: "dump-not-done",
	});
	assert.match(formatHandoffNowCommand(snapshot), /^\/handoff-now --type implementation/);
	assert.match(formatHandoffPrompt(snapshot, "ship the pointer"), /dump is not done/i);
});

test("handoff lane prepares at 60, aligns near 70, switches at 75", () => {
	assert.deepEqual(planHandoffLane({ percent: 55 }).actions, []);
	assert.deepEqual(planHandoffLane({ percent: 61 }).actions, ["prepare"]);
	assert.deepEqual(planHandoffLane({ percent: 71, prepared: true }).actions, ["align"]);
	assert.deepEqual(planHandoffLane({ percent: 76, prepared: true, aligned: true }).actions, ["switch"]);
	assert.deepEqual(planHandoffLane({ percent: 76 }).actions, ["prepare", "switch"]);
	assert.equal(planHandoffLane({ percent: 81, prepared: true, aligned: true }).phase, "overflow");
	assert.deepEqual(planHandoffLane({ percent: 40, compactedInsteadOfHandoff: true }).actions, ["prepare"]);
	assert.deepEqual(planHandoffLane({ percent: 40, prepared: true, compactedInsteadOfHandoff: true }).actions, [
		"switch",
	]);
	assert.deepEqual(planHandoffLane({ percent: 76, switched: true }).actions, []);
});

test("estimateContextPercent falls back when usage.percent is null", () => {
	assert.deepEqual(estimateContextPercent({ usage: { percent: 90, tokens: 1, contextWindow: 256000 } }).source, "usage");
	assert.equal(estimateContextPercent({ usage: { percent: 90 } }).percent, 90);
	assert.deepEqual(
		estimateContextPercent({ usage: { percent: null, tokens: 192000, contextWindow: 256000 } }),
		{ percent: 75, source: "tokens" },
	);
	assert.equal(
		estimateContextPercent({ usage: { percent: null, tokens: null }, sessionBytes: 4 * 192000, contextWindow: 256000 }).source,
		"session-file",
	);
	assert.equal(
		estimateContextPercent({
			usage: { percent: null, tokens: null },
			transcriptBytes: 8 * 192000,
			contextWindow: 256000,
		}).percent,
		75,
	);
	assert.deepEqual(estimateContextPercent({ usage: { percent: null, tokens: null } }), { percent: 0, source: "unknown" });
});

test("queued /handoff-now is not a settled switch", () => {
	const owner = "/tmp/sessions/owner.jsonl";
	const child = "/tmp/sessions/child.jsonl";
	assert.equal(
		handoffLaneSettled({
			prep: { phase: "switched", switched_at: "2026-09-01T06:38:31.508Z", child_session_file: child },
			currentSessionFile: owner,
		}),
		false,
	);
	assert.equal(
		handoffLaneSettled({
			prep: { phase: "queued", queued_at: "2026-09-01T06:38:31.508Z", child_session_file: child },
			currentSessionFile: owner,
		}),
		false,
	);
	assert.equal(
		handoffLaneSettled({
			prep: {
				phase: "successor",
				successor_at: "2026-09-01T06:50:00.000Z",
				successor_job_id: "handoff-1",
				child_session_file: child,
			},
			currentSessionFile: owner,
		}),
		true,
	);
	assert.equal(
		handoffLaneSettled({
			prep: { phase: "switched", child_session_file: child },
			currentSessionFile: child,
		}),
		true,
	);
	assert.equal(shouldInjectHandoffPrompt({ prompt_sent_at: "2026-09-01T06:22:42.773Z" }), true);
	assert.equal(shouldInjectHandoffPrompt({ phase: "successor", successor_at: "2026-09-01T06:50:00.000Z" }), false);
});

test("sessionSteerMode and switch action follow headless vs interactive", () => {
	assert.equal(sessionSteerMode({ hasUI: false }), "headless");
	assert.equal(sessionSteerMode({ hasUI: true, mode: "tui" }), "interactive");
	assert.equal(sessionSteerMode({ hasUI: true, mode: "rpc" }), "interactive");
	assert.equal(sessionSteerMode({ hasUI: false, mode: "json" }), "headless");
	assert.equal(sessionSteerMode({ hasUI: true, mode: "print" }), "headless");
	assert.equal(sessionSteerMode({ hasUI: true, env: { PI_HANDOFF_STEER_MODE: "headless" } }), "headless");
	assert.equal(sessionSteerMode({ hasUI: false, env: { PI_HANDOFF_STEER_MODE: "interactive" } }), "interactive");
	assert.equal(handoffSwitchAction({ mode: "headless", prepared: true }), "switch-now");
	assert.equal(handoffSwitchAction({ mode: "interactive", prepared: true }), "push-interactive");
	assert.equal(handoffSwitchAction({ mode: "headless", prepared: false }), "handoff-now-fallback");
	assert.equal(afterCompactTriage(), "handoff-candidate");
	assert.equal(afterCompactTriage({ preferHandoff: false }), "handoff-candidate");
	assert.equal(handoffChildReady({ fileExists: true }), true);
	assert.equal(handoffChildReady({ jobStatus: "succeeded" }), true);
	assert.equal(handoffChildReady({}), false);
});

test("75% switch traces differ for headless vs interactive and never confirm", async () => {
	const headlessPlan = planHandoffLane({
		percent: 76,
		prepared: true,
		aligned: true,
		hasUI: false,
		mode: "json",
	});
	const interactivePlan = planHandoffLane({
		percent: 76,
		prepared: true,
		aligned: true,
		hasUI: true,
		mode: "tui",
	});
	assert.equal(headlessPlan.steerMode, "headless");
	assert.equal(headlessPlan.switchKind, "switch-now");
	assert.equal(interactivePlan.steerMode, "interactive");
	assert.equal(interactivePlan.switchKind, "push-interactive");

	const headless = handoffSwitchPresentation({
		mode: headlessPlan.steerMode,
		hasUI: false,
		replacementHasUI: false,
		prepared: true,
	});
	const interactive = handoffSwitchPresentation({
		mode: interactivePlan.steerMode,
		hasUI: true,
		replacementHasUI: true,
		prepared: true,
	});
	assert.deepEqual(describeHandoffSwitchEffects(headless), [
		"replacement.send.followUp",
		"kind.switch-now",
	]);
	assert.deepEqual(describeHandoffSwitchEffects(interactive), [
		"owner.notify",
		"replacement.notify",
		"replacement.editor",
		"kind.push-interactive",
	]);
	assert.equal(headless.confirm, false);
	assert.equal(interactive.confirm, false);

	const headlessCalls: string[] = [];
	await applyHandoffSwitchEffects({
		presentation: headless,
		prompt: "continue the snapshot",
		snapshotPath: "/tmp/snap.json",
		owner: {
			hasUI: false,
			notify: () => headlessCalls.push("owner.notify"),
			setEditorText: () => headlessCalls.push("owner.editor"),
		},
		replacement: {
			hasUI: false,
			notify: () => headlessCalls.push("replacement.notify"),
			setEditorText: () => headlessCalls.push("replacement.editor"),
			sendUserMessage: (_text, opts) => {
				headlessCalls.push(`replacement.send.${opts.deliverAs}`);
			},
		},
	});
	assert.deepEqual(headlessCalls, ["replacement.send.followUp"]);

	const interactiveCalls: string[] = [];
	let editor = "";
	await applyHandoffSwitchEffects({
		presentation: interactive,
		prompt: "continue the snapshot",
		snapshotPath: "/tmp/snap.json",
		owner: {
			hasUI: true,
			notify: () => interactiveCalls.push("owner.notify"),
			setEditorText: (text) => {
				editor = text;
				interactiveCalls.push("owner.editor");
			},
		},
		replacement: {
			hasUI: true,
			notify: () => interactiveCalls.push("replacement.notify"),
			setEditorText: () => interactiveCalls.push("replacement.editor"),
			sendUserMessage: (_text, opts) => {
				interactiveCalls.push(`replacement.send.${opts.deliverAs}`);
			},
		},
	});
	assert.deepEqual(interactiveCalls, [
		"owner.notify",
		"replacement.notify",
		"replacement.editor",
	]);
	assert.equal(editor, "");
	assert.equal(interactive.owner.setEditorText, false);
	assert.equal(interactive.replacement.setEditorText, true);
});

test("print/json stay headless even when hasUI is true; TUI/RPC stay interactive", () => {
	assert.equal(planHandoffLane({ percent: 76, prepared: true, aligned: true, hasUI: true, mode: "print" }).steerMode, "headless");
	assert.equal(planHandoffLane({ percent: 76, prepared: true, aligned: true, hasUI: true, mode: "json" }).steerMode, "headless");
	assert.equal(planHandoffLane({ percent: 76, prepared: true, aligned: true, hasUI: true, mode: "rpc" }).steerMode, "interactive");
	const printSwitch = handoffSwitchPresentation({
		mode: "headless",
		hasUI: true,
		replacementHasUI: true,
		prepared: true,
	});
	assert.equal(printSwitch.owner.setEditorText, false);
	assert.equal(printSwitch.replacement.setEditorText, false);
	assert.equal(printSwitch.replacement.notify, true);
	assert.equal(printSwitch.sendUserMessage, true);
	assert.equal(printSwitch.confirm, false);
	assert.equal(
		handoffSwitchPresentation({ mode: "headless", prepared: true, promptAlreadySent: true }).sendUserMessage,
		false,
	);
});

test("mocked switchSession is silent in headless and pushes the editor in interactive", async () => {
	async function driveSwitch(mode: "headless" | "interactive") {
		const calls: string[] = [];
		const hasUI = mode === "interactive";
		const presentation = handoffSwitchPresentation({
			mode,
			hasUI,
			replacementHasUI: hasUI,
			prepared: true,
		});
		assert.equal(presentation.confirm, false);
		const fakeSwitch = async (_file: string, opts: { withSession: (ctx: { hasUI: boolean }) => Promise<void> }) => {
			calls.push("switchSession");
			await opts.withSession({ hasUI });
			return { cancelled: false };
		};
		await fakeSwitch("/tmp/child.jsonl", {
			withSession: async (replacement) => {
				await applyHandoffSwitchEffects({
					presentation: handoffSwitchPresentation({
						mode,
						hasUI,
						replacementHasUI: replacement.hasUI,
						prepared: true,
					}),
					prompt: "continue now",
					snapshotPath: "/tmp/snap.json",
					owner: {
						hasUI,
						notify: () => calls.push("owner.notify"),
						setEditorText: () => calls.push("owner.editor"),
					},
					replacement: {
						hasUI: replacement.hasUI,
						notify: () => calls.push("replacement.notify"),
						setEditorText: () => calls.push("replacement.editor"),
						sendUserMessage: () => {
							calls.push("replacement.followUp");
						},
					},
				});
			},
		});
		return calls;
	}

	assert.deepEqual(await driveSwitch("headless"), ["switchSession", "replacement.followUp"]);
	assert.deepEqual(await driveSwitch("interactive"), [
		"switchSession",
		"owner.notify",
		"replacement.notify",
		"replacement.editor",
	]);
});

test("same-tick 75% prepare does not spawn a competing warm-up", () => {
	const late = planHandoffLane({ percent: 76 });
	assert.deepEqual(late.actions, ["prepare", "switch"]);
	assert.equal(shouldSpawnHandoffWarmup(late.actions), false);
	assert.equal(shouldSpawnHandoffWarmup(["prepare"]), true);
	assert.equal(shouldSpawnHandoffWarmup(["prepare", "align"]), true);
	assert.equal(handoffSwitchReady({ fileExists: true, sameTickCreate: true }), true);
	assert.equal(handoffSwitchReady({ fileExists: true }), false);
	assert.equal(handoffSwitchReady({ fileExists: true, aligned: true }), true);
});

test("sibling file exists never falls through to newSession", () => {
	assert.equal(handoffSwitchTarget({ siblingFileExists: true, switchSessionAvailable: true }), "switch-sibling");
	assert.equal(handoffSwitchTarget({ siblingFileExists: true, switchSessionAvailable: false }), "defer");
	assert.equal(handoffSwitchTarget({ siblingFileExists: false, switchSessionAvailable: false }), "new-session");
	assert.equal(shouldInjectHandoffPrompt({}), true);
	assert.equal(shouldInjectHandoffPrompt({ prompt_sent_at: "2026-08-31T23:49:13.715Z" }), true);
	assert.equal(
		shouldInjectHandoffPrompt({
			prompt_sent_at: "2026-08-31T23:49:13.715Z",
			switched_at: "2026-09-01T01:33:29.630Z",
		}),
		false,
	);
	const alreadySent = handoffSwitchPresentation({
		mode: "headless",
		hasUI: false,
		prepared: true,
		promptAlreadySent: true,
	});
	assert.equal(alreadySent.sendUserMessage, false);
	assert.equal(shouldQueueHandoffNowAfterSwitch({ promptDelivered: true, mode: "headless" }), false);
	assert.equal(shouldQueueHandoffNowAfterSwitch({ promptDelivered: false, mode: "headless" }), true);
	assert.equal(shouldQueueHandoffNowAfterSwitch({ promptDelivered: false, mode: "interactive" }), false);
	assert.equal(shouldQueueHandoffNowAfterSwitch({ promptDelivered: true, mode: "interactive" }), false);
	assert.equal(
		shouldQueueHandoffNowAfterSwitch({
			promptDelivered: false,
			mode: "interactive",
			switchSessionAvailable: false,
		}),
		true,
	);
	assert.equal(
		shouldQueueHandoffNowAfterSwitch({
			promptDelivered: false,
			mode: "interactive",
			switchSessionAvailable: true,
		}),
		false,
	);
	assert.equal(
		shouldQueueHandoffNowAfterSwitch({
			promptDelivered: true,
			mode: "interactive",
			switchSessionAvailable: false,
		}),
		true,
	);
	assert.equal(
		shouldQueueHandoffNowAfterSwitch({
			promptDelivered: false,
			mode: "headless",
			switchSessionAvailable: false,
		}),
		true,
	);
	assert.equal(shouldFallbackHandoffPrompt({ prep: { prompt_sent_at: "2026-08-31T23:49:13.715Z" }, mode: "headless" }), true);
	assert.equal(
		shouldFallbackHandoffPrompt({
			prep: { prompt_sent_at: "2026-08-31T23:49:13.715Z", switched_at: "2026-09-01T01:33:29.630Z" },
			mode: "headless",
		}),
		false,
	);
	assert.equal(shouldFallbackHandoffPrompt({ prep: {}, mode: "headless" }), true);
	assert.equal(shouldFallbackHandoffPrompt({ prep: {}, mode: "interactive" }), false);
	assert.equal(shouldInjectContinueAfterLane({ handoffQueued: true, prep: {} }), false);
	assert.equal(shouldInjectContinueAfterLane({ handoffQueued: false, prep: { prompt_sent_at: "2026-08-31T23:49:13.715Z" } }), false);
	assert.equal(shouldInjectContinueAfterLane({ handoffQueued: false, prep: {} }), true);
	assert.equal(shouldPushOwnerEditorOnDefer({ mode: "interactive", hasUI: true, prep: {} }), true);
	assert.equal(shouldPushOwnerEditorOnDefer({ mode: "interactive", hasUI: true, prep: { prompt_sent_at: "2026-08-31T23:49:13.715Z" } }), false);
	assert.equal(shouldPushOwnerEditorOnDefer({ mode: "headless", hasUI: true, prep: {} }), false);
	assert.equal(shouldPushOwnerEditorOnDefer({ mode: "interactive", hasUI: false, prep: {} }), false);
	assert.equal(shouldFallbackNewSession({ siblingFileExists: true }), false);
	assert.equal(shouldFallbackNewSession({ prepInFlight: true }), false);
	assert.equal(shouldFallbackNewSession({ sameTickPrepare: true }), false);
	assert.equal(shouldFallbackNewSession({ spawnWarmup: true }), false);
	assert.equal(shouldFallbackNewSession({}), true);
	assert.equal(handoffSwitchTarget({ siblingFileExists: false, sameTickPrepare: true }), "defer");
	assert.equal(handoffSwitchTarget({ siblingFileExists: false, spawnWarmup: true }), "defer");
	assert.equal(handoffSwitchTarget({ siblingFileExists: false, prepInFlight: true, switchSessionAvailable: true }), "defer");
	const now = Date.parse("2026-08-31T23:49:13.715Z");
	const preparedAt = "2026-08-31T23:49:13.700Z";
	assert.equal(handoffPrepInFlight({ preparedAt, now }), true);
	assert.equal(handoffPrepInFlight({ childFile: "/tmp/pending.jsonl", fileExists: false }), true);
	assert.equal(handoffPrepInFlight({ childFile: "/tmp/ready.jsonl", fileExists: true }), false);
	assert.equal(handoffPrepInFlight({ childJobId: "handoff-1" }), true);
	assert.equal(
		shouldOpenNewHandoffSession({
			target: "new-session",
			childFile: "/tmp/pending.jsonl",
			siblingFileExists: false,
		}),
		false,
	);
	assert.equal(shouldOpenNewHandoffSession({ target: "new-session", childJobId: "handoff-1" }), false);
	assert.equal(shouldOpenNewHandoffSession({ target: "new-session", sameTickPrepare: true }), false);
	assert.equal(shouldFallbackHandoffPrompt({ prep: { prepared_at: preparedAt }, mode: "headless", now }), false);
	assert.equal(shouldSpawnHandoffWarmup(planHandoffLane({ percent: 76 }).actions) && shouldFallbackNewSession({ sameTickPrepare: true }), false);
});

test("second prepare in the same tick does not create another sibling", () => {
	assert.equal(shouldCreateHandoffSibling({ fileExists: true }), false);
	assert.equal(shouldCreateHandoffSibling({ childFile: "/tmp/child.jsonl", fileExists: true }), false);
	assert.equal(shouldCreateHandoffSibling({ childFile: "/tmp/missing.jsonl", fileExists: false }), true);
	assert.equal(shouldCreateHandoffSibling({}), true);
	assert.equal(
		shouldCreateHandoffSibling({
			preparedAt: new Date().toISOString(),
			now: Date.now(),
		}),
		false,
	);
	assert.equal(
		shouldCreateHandoffSibling({
			preparedAt: new Date(Date.now() - 30_000).toISOString(),
			now: Date.now(),
		}),
		true,
	);

	const id = `claim-once-${Date.now()}-handoff`;
	const stub = {
		schema: HANDOFF_PREP_SCHEMA,
		source_session_id: id,
		snapshot_path: join(tmp, "snap.json"),
		phase: "prepared" as const,
		prepared_at: new Date().toISOString(),
	};
	const first = tryClaimHandoffPrep(stub);
	assert.equal(first.claimed, true);
	const second = tryClaimHandoffPrep(stub);
	assert.equal(second.claimed, false);
	assert.equal(second.existing?.source_session_id, id);
	unlinkSync(first.path);
});

test("env UUID and file basename collapse to one owner session", () => {
	const fileId = "2026-08-31T22-39-55-198Z_01a059fa-ab3e-7960-bba7-ecb2d77563ad";
	const uuid = "01a059fa-ab3e-7960-bba7-ecb2d77563ad";
	const ids = ownerSessionIds({
		sessionFile: `/tmp/sessions/${fileId}.jsonl`,
		sessionId: uuid,
		env: { PI_SESSION_ID: uuid, CDEV_SESSION_ID: uuid },
	});
	assert.equal(ids.canonical, fileId);
	assert.deepEqual(ids.aliases, [fileId, uuid]);
	assert.equal(sessionUuidFromId(fileId), uuid);
	const fileOnly = ownerSessionIds({ sessionFile: `/tmp/sessions/${fileId}.jsonl` });
	assert.deepEqual(fileOnly.aliases, [fileId, uuid]);
	const uuidOnly = ownerSessionIds({ sessionId: uuid, env: { PI_SESSION_ID: uuid } });
	assert.deepEqual(uuidOnly.aliases, [uuid]);
});

test("after switch the child is a new owner and can open another context", () => {
	const parentFile = "/tmp/sessions/2026-08-31T22-39-55-198Z_01a059fa-ab3e-7960-bba7-ecb2d77563ad.jsonl";
	const childFile = "/tmp/sessions/2026-08-31T23-51-01-088Z_01a05a3b-c2e0-7427-a970-30b88399c0aa.jsonl";
	const parentUuid = "01a059fa-ab3e-7960-bba7-ecb2d77563ad";
	const childIds = ownerSessionIds({
		sessionFile: childFile,
		env: { PI_SESSION_ID: parentUuid, CDEV_SESSION_ID: parentUuid },
	});
	assert.match(childIds.canonical, /c2e0/);
	assert.equal(childIds.aliases.includes(parentUuid), false);
	assert.equal(isHandoffChildSession({ childFile, currentFile: childFile }), true);
	assert.equal(isHandoffChildSession({ childFile, currentFile: parentFile }), false);

	const parentPrep = {
		schema: HANDOFF_PREP_SCHEMA,
		source_session_id: parentUuid,
		snapshot_path: "/tmp/snap.json",
		child_session_file: childFile,
		phase: "switched" as const,
		prepared_at: "2026-08-31T23:51:01.082Z",
	};
	assert.equal(resolveLiveHandoffPrep({ prep: parentPrep, currentSessionFile: childFile }), undefined);
	assert.equal(resolveLiveHandoffPrep({ prep: parentPrep, currentSessionFile: parentFile })?.phase, "switched");
	assert.equal(
		handoffSwitchTarget({
			siblingFileExists: true,
			switchSessionAvailable: true,
			siblingIsCurrent: true,
		}),
		"new-session",
	);
	assert.equal(
		shouldCreateHandoffSibling({
			childFile,
			fileExists: true,
			preparedAt: parentPrep.prepared_at,
			currentSessionFile: childFile,
		}),
		true,
	);
	assert.equal(
		shouldOpenNewHandoffSession({
			target: "new-session",
			siblingFileExists: true,
			childFile,
			preparedAt: parentPrep.prepared_at,
			currentSessionFile: childFile,
		}),
		true,
	);
	assert.deepEqual(planHandoffLane({ percent: 76, prepared: false, switched: false }).actions, ["prepare", "switch"]);
	assert.deepEqual(keepLiveHandoffChild({ child_session_file: childFile, child_session_id: "c" }, childFile), {});
});

test("file-id and uuid-only callers cannot both claim a sibling", () => {
	const fileId = `2026-08-31T22-39-55-198Z_01a05a00-aa00-4000-8000-${Date.now().toString(16).padStart(12, "0").slice(-12)}`;
	const uuid = sessionUuidFromId(fileId);
	assert.ok(uuid);
	const stub = {
		schema: HANDOFF_PREP_SCHEMA,
		source_session_id: fileId,
		snapshot_path: join(tmp, "snap.json"),
		phase: "prepared" as const,
		prepared_at: new Date().toISOString(),
	};
	const first = tryClaimHandoffPrep(stub, [fileId]);
	assert.equal(first.claimed, true);
	assert.equal(existsSync(handoffPrepPathForSession(uuid)), true);
	const second = tryClaimHandoffPrep({ ...stub, source_session_id: uuid }, [uuid]);
	assert.equal(second.claimed, false);
	assert.equal(shouldOpenNewHandoffSession({ target: "new-session", preparedAt: stub.prepared_at }), false);
	assert.equal(shouldOpenNewHandoffSession({ target: "new-session", siblingFileExists: true }), false);
	assert.equal(shouldOpenNewHandoffSession({ target: "switch-sibling" }), false);
	assert.equal(shouldOpenNewHandoffSession({ target: "new-session" }), true);
	const child = join(tmp, `${fileId}-keep-child.jsonl`);
	writeFileSync(child, "x\n");
	assert.equal(keepLiveHandoffChild({ child_session_file: child, child_session_id: "c1" }).child_session_id, "c1");
	assert.deepEqual(keepLiveHandoffChild({ child_session_file: join(tmp, "missing.jsonl") }), {});
	unlinkSync(first.path);
	unlinkSync(handoffPrepPathForSession(uuid));
	unlinkSync(child);
});

test("readHandoffPrepAny prefers the alias whose sibling file exists", () => {
	const fileId = `alias-file-${Date.now()}-handoff`;
	const uuid = `alias-uuid-${Date.now()}-handoff`;
	const child = join(tmp, `${fileId}-child.jsonl`);
	writeFileSync(child, "x\n");
	writeHandoffPrep({
		schema: HANDOFF_PREP_SCHEMA,
		source_session_id: uuid,
		snapshot_path: join(tmp, "snap.json"),
		phase: "prepared",
		prepared_at: "2026-08-31T00:00:00.000Z",
	});
	writeHandoffPrep({
		schema: HANDOFF_PREP_SCHEMA,
		source_session_id: fileId,
		snapshot_path: join(tmp, "snap.json"),
		child_session_file: child,
		phase: "aligned",
		prepared_at: "2026-08-31T00:00:00.000Z",
	});
	const loaded = readHandoffPrepAny([uuid, fileId]);
	assert.equal(loaded?.source_session_id, fileId);
	assert.equal(loaded?.child_session_file, child);
	const claimed = tryClaimHandoffPrep(
		{
			schema: HANDOFF_PREP_SCHEMA,
			source_session_id: uuid,
			snapshot_path: join(tmp, "snap.json"),
			phase: "prepared",
			prepared_at: new Date().toISOString(),
		},
		[fileId, uuid],
	);
	assert.equal(claimed.claimed, false);
	unlinkSync(handoffPrepPathForSession(fileId));
	unlinkSync(handoffPrepPathForSession(uuid));
});

test("writeHandoffPrepAliases mirrors the canonical prep onto env UUID keys", () => {
	const fileId = `alias-write-${Date.now()}-handoff`;
	const uuid = `alias-write-uuid-${Date.now()}-handoff`;
	const child = join(tmp, `${fileId}-child.jsonl`);
	writeFileSync(child, "x\n");
	writeHandoffPrepAliases(
		{
			schema: HANDOFF_PREP_SCHEMA,
			source_session_id: fileId,
			snapshot_path: join(tmp, "snap.json"),
			child_session_file: child,
			phase: "prepared",
			prepared_at: "2026-08-31T00:00:00.000Z",
		},
		[fileId, uuid],
	);
	assert.equal(readHandoffPrep(uuid)?.child_session_file, child);
	assert.equal(readHandoffPrepAny([uuid])?.child_session_file, child);
	unlinkSync(handoffPrepPathForSession(fileId));
	unlinkSync(handoffPrepPathForSession(uuid));
});

test("prepare/align prompts stay tiny and do not take over", () => {
	const snapshot = buildSnapshot({
		branch: [user("ship the pointer")],
		goal: "ship the pointer",
		kind: "implementation",
		sessionId: "prep-prompt",
	});
	const prepare = formatHandoffPreparePrompt(snapshot, "ship the pointer");
	const align = formatHandoffAlignPrompt(snapshot, "ship the pointer");
	assert.match(prepare, /background handoff warm-up/i);
	assert.match(prepare, /Do not replace the owner session/);
	assert.match(align, /Align with the current owner session/);
	assert.match(align, /Do not take over until switch/);
	assert.match(formatHandoffPrepareCommand(snapshot), /^\/handoff-prepare --type implementation/);
	assert.ok(prepare.length <= HANDOFF_PROMPT_MAX_CHARS);
});

test("handoff prep state roundtrips", () => {
	const path = writeHandoffPrep({
		schema: HANDOFF_PREP_SCHEMA,
		source_session_id: "prep-roundtrip",
		snapshot_path: join(tmp, "snap.json"),
		child_session_file: join(tmp, "child.jsonl"),
		phase: "prepared",
		prepared_at: "2026-08-31T00:00:00.000Z",
	});
	assert.ok(path.includes("prep-roundtrip"));
	const loaded = readHandoffPrep("prep-roundtrip");
	assert.equal(loaded?.schema, HANDOFF_PREP_SCHEMA);
	assert.equal(loaded?.phase, "prepared");
	assert.equal(loaded?.child_session_file?.endsWith("child.jsonl"), true);
});

test("resolveLimits exposes 60/70/75 handoff lane defaults", () => {
	const limits = resolveLimits({ contextWindow: 256000 });
	assert.equal(limits.handoffPreparePercent, 60);
	assert.equal(limits.handoffAlignPercent, 70);
	assert.equal(limits.handoffSwitchPercent, 75);
});

test("readSnapshot rejects invalid files", () => {
	const snapshot = buildSnapshot({
		branch: [user("persist me")],
		sessionId: "read-roundtrip",
		now: "2026-08-21T00:00:00.000Z",
	});
	snapshot.snapshot_path = join(tmp, "read-roundtrip.json");
	const path = writeSnapshot(snapshot);
	const loaded = readSnapshot(path);
	assert.equal(loaded?.schema, SNAPSHOT_SCHEMA);
	assert.equal(readSnapshot(join(tmp, "missing.json")), undefined);
});
