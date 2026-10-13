/** Automatic pointer handoff. No dialogs, editor submission, or transcript rewriting. */
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { existsSync } from "node:fs";
import { dirname } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import {
	buildSnapshot, formatHandoffAlignPrompt, formatHandoffPreparePrompt, formatHandoffPrompt,
	handoffPrepIsInFlight, ownerSessionIds, parseHandoffArgs, persistSnapshot,
	readHandoffPrepAny, sessionSteerMode, shouldCreateHandoffSibling,
	keepLiveHandoffChild, isHandoffChildSession, resolveLiveHandoffPrep,
	tryClaimHandoffPrep, writeHandoffPrepAliases, HANDOFF_PREP_SCHEMA,
	HANDOFF_PREP_CLAIM_TTL_MS, type HandoffPrepState, type CompactSnapshot,
} from "./lib/compact-snapshot.ts";
import { createSiblingHandoffSession, spawnHandoffPrintTurn } from "./lib/handoff-sibling.ts";
import { captureHandoffPrepWriter, replaceHandoffSession } from "./lib/handoff-replacement.ts";

function ownerIds(ctx: ExtensionCommandContext) {
	return ownerSessionIds({ sessionFile: ctx.sessionManager.getSessionFile(),
		sessionId: ctx.sessionManager.getSessionId?.(), env: process.env });
}

function currentOwnerPrep(ctx: ExtensionCommandContext) {
	return resolveLiveHandoffPrep({ prep: readHandoffPrepAny(ownerIds(ctx).aliases),
		currentSessionFile: ctx.sessionManager.getSessionFile() });
}

function persistOwnerPrep(ctx: ExtensionCommandContext, prep: HandoffPrepState) {
	const ids = ownerIds(ctx);
	return writeHandoffPrepAliases({ ...prep,
		...keepLiveHandoffChild(readHandoffPrepAny(ids.aliases), ctx.sessionManager.getSessionFile()),
		source_session_id: ids.canonical }, ids.aliases);
}

function prepareOrAlignSibling(ctx: ExtensionCommandContext, snapshot: CompactSnapshot, align: boolean): void {
	const ids = ownerIds(ctx);
	const existing = currentOwnerPrep(ctx);
	const parentFile = ctx.sessionManager.getSessionFile();
	const childExists = Boolean(existing?.child_session_file && existsSync(existing.child_session_file));
	if (childExists && existing) {
		if (align) {
			spawnHandoffPrintTurn({ cwd: ctx.cwd, sessionFile: existing.child_session_file!,
				prompt: formatHandoffAlignPrompt(snapshot, snapshot.objective), source: "handoff-align" });
		}
		persistOwnerPrep(ctx, { ...existing, snapshot_path: snapshot.snapshot_path,
			...(align ? { phase: "aligned", aligned_at: new Date().toISOString() } : {}) });
		return;
	}
	if (!shouldCreateHandoffSibling({ childFile: existing?.child_session_file,
		fileExists: childExists, preparedAt: existing?.prepared_at, currentSessionFile: parentFile })) return;
	const prep: HandoffPrepState = {
		schema: HANDOFF_PREP_SCHEMA, source_session_id: ids.canonical, source_session_file: parentFile,
		snapshot_path: snapshot.snapshot_path, phase: "prepared", prepared_at: new Date().toISOString(),
		mode: sessionSteerMode({ hasUI: ctx.hasUI, mode: ctx.mode }),
	};
	if (!existing && !tryClaimHandoffPrep(prep, ids.aliases).claimed) return;
	const sibling = createSiblingHandoffSession({ cwd: ctx.cwd,
		sessionDir: ctx.sessionManager.getSessionDir?.() || (parentFile ? dirname(parentFile) : undefined),
		parentSessionFile: parentFile, sourceSessionId: ids.canonical, snapshotPath: snapshot.snapshot_path });
	prep.child_session_file = sibling.sessionFile;
	prep.child_session_id = sibling.sessionId;
	persistOwnerPrep(ctx, prep);
	const spawned = spawnHandoffPrintTurn({ cwd: ctx.cwd, sessionFile: sibling.sessionFile,
		prompt: formatHandoffPreparePrompt(snapshot, snapshot.objective), source: "handoff-prepare" });
	persistOwnerPrep(ctx, { ...prep, child_job_id: spawned.jobId });
	if (ctx.hasUI) ctx.ui.notify(`Handoff prepared in background: ${sibling.sessionFile}`, "info");
}

async function runHandoff(args: string, ctx: ExtensionCommandContext, mode: "now" | "prepare" | "align") {
	const parsed = parseHandoffArgs(args);
	const snapshot = buildSnapshot({ branch: ctx.sessionManager.getBranch(),
		sessionFile: ctx.sessionManager.getSessionFile(), cwd: ctx.cwd, goal: parsed.goal,
		kind: parsed.kind, budgetPercent: parsed.budgetPercent,
		contextWindow: ctx.getContextUsage()?.contextWindow, sessionId: ownerIds(ctx).canonical });
	persistSnapshot(snapshot);
	// --llm and --yes are accepted for compatibility, never required for progress.
	if (mode !== "now") {
		prepareOrAlignSibling(ctx, snapshot, mode === "align");
		return;
	}

	// A competing prepare gets a bounded grace period, not an indefinite human wait.
	const deadline = Date.now() + HANDOFF_PREP_CLAIM_TTL_MS;
	let prep = currentOwnerPrep(ctx);
	while (handoffPrepIsInFlight(prep, { currentSessionFile: ctx.sessionManager.getSessionFile() }) && Date.now() < deadline) {
		await delay(50);
		prep = currentOwnerPrep(ctx);
	}
	const childFile = prep?.child_session_file && existsSync(prep.child_session_file) &&
		!isHandoffChildSession({ childFile: prep.child_session_file, currentFile: ctx.sessionManager.getSessionFile() })
		? prep.child_session_file : undefined;
	if (childFile && typeof ctx.switchSession !== "function") {
		throw new Error("Handoff replacement unavailable: command context lacks switchSession; snapshot persisted");
	}
	const writeOwnerPrep = captureHandoffPrepWriter(ctx, snapshot.snapshot_path);
	// A prepare/align prompt is never an execution prompt. Always activate the replacement.
	await replaceHandoffSession(ctx, { childFile, prompt: formatHandoffPrompt(snapshot, snapshot.objective),
		snapshotPath: snapshot.snapshot_path, promptAlreadySent: false,
		onSwitched: (delivered) => writeOwnerPrep({ phase: "switched", switched_at: new Date().toISOString(),
			...(delivered ? { prompt_sent_at: new Date().toISOString() } : {}) }) });
	// No access to ctx/pi after replacement; it may be stale even on failure.
}

export default function (pi: ExtensionAPI) {
	for (const [name, mode, description] of [
		["handoff", "now", "Switch and continue automatically. --type --budget"],
		["handoff-now", "now", "Switch and continue automatically. --type --budget"],
		["handoff-bg", "prepare", "Prepare a background sibling without human input."],
		["handoff-prepare", "prepare", "Prepare a background sibling without human input."],
		["handoff-align", "align", "Refresh the prepared sibling without human input."],
	] as const) {
		pi.registerCommand(name, { description, handler: (args, ctx) => runHandoff(args, ctx, mode) });
	}
}
