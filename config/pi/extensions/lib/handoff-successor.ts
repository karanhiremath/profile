/**
 * Isolated pi worker successor for switch. Does not replace the owner session.
 */
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, join } from "node:path";
import { randomBytes } from "node:crypto";
import {
	buildSnapshot,
	formatHandoffPrompt,
	persistSnapshot,
	safeSessionId,
	writeHandoffPrepAliases,
	HANDOFF_PREP_SCHEMA,
	type CompactSnapshot,
	type HandoffPrepState,
	type SnapshotEntry,
} from "./compact-snapshot.ts";
import {
	mergeHandoffLineage,
	planCursorHandoffHook,
	readHandoffLineage,
	writeHandoffLineageAliases,
	type CursorHandoffHookPayload,
	type HandoffLineage,
} from "./handoff-lineage.ts";
import { writeMinimalSiblingSession } from "./handoff-sibling-persist.ts";
import { spawnHandoffPrintTurn } from "./handoff-spawn.ts";

export function newSuccessorSessionId(now = new Date()): string {
	const stamp = now.toISOString().replace(/[:.]/g, "-");
	const suffix = randomBytes(4).toString("hex");
	return `${stamp}_${suffix}`;
}

export function successorSessionDir(home = homedir()): string {
	return join(home, ".pi", "agent", "sessions", "handoff-successors");
}

export function createSuccessorSessionFile(input: {
	cwd: string;
	sourceSessionId: string;
	snapshotPath: string;
	sessionId?: string;
	sessionDir?: string;
	home?: string;
}): { sessionId: string; sessionFile: string } {
	const sessionId = input.sessionId || newSuccessorSessionId();
	const dir = input.sessionDir || successorSessionDir(input.home);
	mkdirSync(dir, { recursive: true });
	const sessionFile = join(dir, `${safeSessionId(sessionId)}.jsonl`);
	writeMinimalSiblingSession({
		sessionFile,
		sessionId,
		cwd: input.cwd,
		sourceSessionId: input.sourceSessionId,
		snapshotPath: input.snapshotPath,
		phase: "successor",
	});
	return { sessionId, sessionFile };
}

export function spawnSuccessorWorker(input: {
	cwd: string;
	snapshot: CompactSnapshot;
	sourceSessionId: string;
	sessionFile?: string;
	sessionId?: string;
}): { jobId: string; sessionId: string; sessionFile: string } {
	const sibling =
		input.sessionFile && existsSync(input.sessionFile)
			? {
					sessionId:
						input.sessionId ||
						safeSessionId(basename(input.sessionFile).replace(/\.jsonl$/i, "")),
					sessionFile: input.sessionFile,
				}
			: createSuccessorSessionFile({
					cwd: input.cwd,
					sourceSessionId: input.sourceSessionId,
					snapshotPath: input.snapshot.snapshot_path,
				});
	const spawned = spawnHandoffPrintTurn({
		cwd: input.cwd,
		sessionFile: sibling.sessionFile,
		prompt: formatHandoffPrompt(input.snapshot, input.snapshot.objective),
		source: "handoff-successor",
	});
	return { jobId: spawned.jobId, sessionId: sibling.sessionId, sessionFile: sibling.sessionFile };
}

export function persistSuccessorLineage(input: {
	ownerId: string;
	aliases?: readonly string[];
	snapshot: CompactSnapshot;
	ownerSessionFile?: string;
	cursorConversationId?: string;
	childSessionId?: string;
	childSessionFile?: string;
	childJobId?: string;
	phase?: HandoffLineage["phase"];
	previous?: HandoffLineage;
}): { lineage: HandoffLineage; path: string } {
	const now = new Date().toISOString();
	const lineage = mergeHandoffLineage(input.previous || readHandoffLineage(input.ownerId), {
		owner_session_id: input.ownerId,
		owner_session_file: input.ownerSessionFile,
		cursor_conversation_id: input.cursorConversationId,
		snapshot_path: input.snapshot.snapshot_path,
		child_session_id: input.childSessionId,
		child_session_file: input.childSessionFile,
		child_job_id: input.childJobId,
		kind: input.snapshot.kind,
		phase: input.phase || "successor",
		successor_at: input.phase === "successor" || !input.phase ? now : input.previous?.successor_at,
		updated_at: now,
	});
	const path = writeHandoffLineageAliases(lineage, input.aliases || [input.ownerId]);
	return { lineage, path };
}

function textFromUnknown(value: unknown): string {
	if (typeof value === "string") return value;
	if (!value || typeof value !== "object") return "";
	const rec = value as Record<string, unknown>;
	if (typeof rec.text === "string") return rec.text;
	if (typeof rec.content === "string") return rec.content;
	if (Array.isArray(rec.content)) {
		return rec.content
			.map((block) => textFromUnknown(block))
			.filter(Boolean)
			.join("\n");
	}
	if (rec.message) return textFromUnknown(rec.message);
	return "";
}

export function extractTranscriptHints(transcriptPath?: string, maxBytes = 96_000): {
	lastUser: string[];
	lastAssistant?: string;
} {
	if (!transcriptPath || !existsSync(transcriptPath)) return { lastUser: [] };
	let body = "";
	try {
		const raw = readFileSync(transcriptPath, "utf8");
		body = raw.length > maxBytes ? raw.slice(-maxBytes) : raw;
	} catch {
		return { lastUser: [] };
	}
	const lastUser: string[] = [];
	let lastAssistant = "";
	for (const line of body.split("\n")) {
		const trimmed = line.trim();
		if (!trimmed.startsWith("{")) continue;
		try {
			const row = JSON.parse(trimmed) as Record<string, unknown>;
			const role = String(row.role || (row.message as { role?: string } | undefined)?.role || "");
			const text = textFromUnknown(row).trim();
			if (!text) continue;
			if (role === "user") lastUser.push(text.slice(0, 400));
			if (role === "assistant") lastAssistant = text.slice(0, 600);
		} catch {
			/* skip bad jsonl */
		}
	}
	return { lastUser: lastUser.slice(-3), lastAssistant: lastAssistant || undefined };
}

function snapshotFromCursorHook(payload: CursorHandoffHookPayload, ownerId: string): CompactSnapshot {
	const hints = extractTranscriptHints(payload.transcript_path);
	const cwd = payload.workspace_roots?.[0] || homedir();
	const branch: SnapshotEntry[] = [];
	for (const user of hints.lastUser) {
		branch.push({ type: "message", message: { role: "user", content: user } });
	}
	if (hints.lastAssistant) {
		branch.push({ type: "message", message: { role: "assistant", content: hints.lastAssistant } });
	}
	return buildSnapshot({
		branch,
		cwd,
		sessionId: ownerId,
		goal: hints.lastUser.at(-1),
		kind: "implementation",
		contextWindow: payload.context_window_size,
	});
}

export function persistCursorHookPrep(input: {
	ownerId: string;
	snapshot: CompactSnapshot;
	patch: Partial<HandoffPrepState>;
	previous?: HandoffPrepState;
}): HandoffPrepState {
	const next: HandoffPrepState = {
		schema: HANDOFF_PREP_SCHEMA,
		source_session_id: input.ownerId,
		snapshot_path: input.snapshot.snapshot_path,
		phase: "prepared",
		...input.previous,
		...input.patch,
		schema: HANDOFF_PREP_SCHEMA,
		source_session_id: input.ownerId,
		snapshot_path: input.snapshot.snapshot_path,
	};
	writeHandoffPrepAliases(next, [input.ownerId]);
	return next;
}

export type CursorHandoffHookResult = {
	ok: true;
	event: string;
	ownerId: string;
	percent: number;
	source: string;
	actions: string[];
	settled: boolean;
	spawned: boolean;
	snapshotPath?: string;
	jobId?: string;
	lineagePath?: string;
	followup_message?: string;
	user_message?: string;
};

export function runCursorHandoffHook(payload: CursorHandoffHookPayload): CursorHandoffHookResult {
	const event = payload.hook_event_name || "";
	const previous = readHandoffLineage(cursorOwnerId(payload));
	const plan = planCursorHandoffHook(payload, { lineage: previous });
	const ownerId = plan.ownerId;
	if (plan.actions.length === 0) {
		return {
			ok: true,
			event,
			ownerId,
			percent: plan.estimate.percent,
			source: plan.estimate.source,
			actions: [],
			settled: plan.settled,
			spawned: false,
		};
	}
	const snapshot = snapshotFromCursorHook(payload, ownerId);
	persistSnapshot(snapshot);
	persistCursorHookPrep({
		ownerId,
		snapshot,
		previous: undefined,
		patch: {
			phase: plan.actions.includes("switch") ? "queued" : "prepared",
			prepared_at: new Date().toISOString(),
			queued_at: plan.actions.includes("switch") ? new Date().toISOString() : undefined,
			mode: "interactive",
		},
	});
	if (!plan.spawnSuccessor) {
		const lineage = persistSuccessorLineage({
			ownerId,
			snapshot,
			cursorConversationId: payload.conversation_id,
			phase: plan.actions.includes("align") ? "aligned" : "prepared",
			previous,
		});
		return {
			ok: true,
			event,
			ownerId,
			percent: plan.estimate.percent,
			source: plan.estimate.source,
			actions: [...plan.actions],
			settled: plan.settled,
			spawned: false,
			snapshotPath: snapshot.snapshot_path,
			lineagePath: lineage.path,
		};
	}
	const spawned = spawnSuccessorWorker({
		cwd: payload.workspace_roots?.[0] || homedir(),
		snapshot,
		sourceSessionId: ownerId,
	});
	const now = new Date().toISOString();
	persistCursorHookPrep({
		ownerId,
		snapshot,
		patch: {
			phase: "successor",
			child_session_id: spawned.sessionId,
			child_session_file: spawned.sessionFile,
			child_job_id: spawned.jobId,
			successor_job_id: spawned.jobId,
			successor_at: now,
			queued_at: now,
		},
	});
	const lineage = persistSuccessorLineage({
		ownerId,
		snapshot,
		cursorConversationId: payload.conversation_id,
		childSessionId: spawned.sessionId,
		childSessionFile: spawned.sessionFile,
		childJobId: spawned.jobId,
		phase: "successor",
		previous,
	});
	const notice = `Handoff successor spawned (${Math.round(plan.estimate.percent)}%). snapshot: ${snapshot.snapshot_path} job: ${spawned.jobId}`;
	return {
		ok: true,
		event,
		ownerId,
		percent: plan.estimate.percent,
		source: plan.estimate.source,
		actions: [...plan.actions],
		settled: true,
		spawned: true,
		snapshotPath: snapshot.snapshot_path,
		jobId: spawned.jobId,
		lineagePath: lineage.path,
		user_message: event === "preCompact" ? notice : undefined,
	};
}

function cursorOwnerId(payload: CursorHandoffHookPayload): string {
	return planCursorHandoffHook(payload).ownerId;
}

export function cursorHookResponse(result: CursorHandoffHookResult): Record<string, string> {
	const out: Record<string, string> = {};
	if (result.followup_message) out.followup_message = result.followup_message;
	if (result.user_message) out.user_message = result.user_message;
	return out;
}
