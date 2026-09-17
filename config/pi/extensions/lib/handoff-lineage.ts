/**
 * Durable owner → successor lineage for pointer handoff.
 * A queued /handoff-now is not a finished switch.
 */
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import {
	estimateContextPercent,
	handoffLaneSettled,
	handoffPrepPathForSession,
	planHandoffLane,
	safeSessionId,
	type CompactHandoffConfig,
	type ContextPercentEstimate,
	type ContextUsageLike,
	type HandoffKind,
	type HandoffLaneAction,
	type HandoffPrepState,
} from "./compact-snapshot.ts";

export const HANDOFF_LINEAGE_SCHEMA = "pi.handoff-lineage.v1" as const;

export type HandoffLineagePhase = "prepared" | "aligned" | "queued" | "switched" | "successor";

export type HandoffLineage = {
	schema: typeof HANDOFF_LINEAGE_SCHEMA;
	owner_session_id: string;
	owner_session_file?: string;
	cursor_conversation_id?: string;
	snapshot_path: string;
	child_session_id?: string;
	child_session_file?: string;
	child_job_id?: string;
	generation: number;
	ancestors: string[];
	phase: HandoffLineagePhase;
	kind?: HandoffKind;
	created_at: string;
	updated_at: string;
	queued_at?: string;
	switched_at?: string;
	successor_at?: string;
};

export function lineageRoot(home = homedir()): string {
	return join(home, ".pi", "agent", "lineage");
}

export function lineagePathForSession(sessionId: string, home = homedir()): string {
	return join(lineageRoot(home), `${safeSessionId(sessionId)}.json`);
}

export function readHandoffLineage(sessionId: string, home = homedir()): HandoffLineage | undefined {
	try {
		const raw = JSON.parse(readFileSync(lineagePathForSession(sessionId, home), "utf8")) as Partial<HandoffLineage>;
		if (!raw || raw.schema !== HANDOFF_LINEAGE_SCHEMA) return undefined;
		if (typeof raw.owner_session_id !== "string" || typeof raw.snapshot_path !== "string") return undefined;
		return raw as HandoffLineage;
	} catch {
		return undefined;
	}
}

export function writeHandoffLineage(lineage: HandoffLineage, home = homedir()): string {
	const path = lineagePathForSession(lineage.owner_session_id, home);
	mkdirSync(dirname(path), { recursive: true });
	writeFileSync(path, `${JSON.stringify(lineage, null, 2)}\n`);
	return path;
}

export function writeHandoffLineageAliases(
	lineage: HandoffLineage,
	aliases: readonly string[],
	home = homedir(),
): string {
	const path = writeHandoffLineage(lineage, home);
	const canonical = safeSessionId(lineage.owner_session_id);
	for (const raw of aliases) {
		const id = safeSessionId(raw);
		if (!id || id === canonical) continue;
		writeHandoffLineage({ ...lineage, owner_session_id: id }, home);
	}
	return path;
}

export function mergeHandoffLineage(
	previous: HandoffLineage | undefined,
	patch: Partial<HandoffLineage> & Pick<HandoffLineage, "owner_session_id" | "snapshot_path">,
): HandoffLineage {
	const now = patch.updated_at || new Date().toISOString();
	const owner = patch.owner_session_id;
	const ancestors = uniqueIds([
		...(previous?.ancestors ?? []),
		previous?.owner_session_id,
		...(patch.ancestors ?? []),
	]).filter((id) => id !== owner);
	return {
		schema: HANDOFF_LINEAGE_SCHEMA,
		generation: patch.generation ?? previous?.generation ?? 1,
		ancestors,
		phase: patch.phase ?? previous?.phase ?? "prepared",
		created_at: previous?.created_at || now,
		...previous,
		...patch,
		schema: HANDOFF_LINEAGE_SCHEMA,
		owner_session_id: owner,
		snapshot_path: patch.snapshot_path,
		ancestors,
		updated_at: now,
	};
}

function uniqueIds(ids: Array<string | undefined>): string[] {
	const seen = new Set<string>();
	const out: string[] = [];
	for (const raw of ids) {
		const id = raw ? safeSessionId(raw) : "";
		if (!id || seen.has(id)) continue;
		seen.add(id);
		out.push(id);
	}
	return out;
}

export function fileSizeOrZero(path?: string): number {
	if (!path) return 0;
	try {
		if (!existsSync(path)) return 0;
		return statSync(path).size;
	} catch {
		return 0;
	}
}

export function resolveLanePercent(input: {
	usage?: ContextUsageLike | null;
	tokens?: number | null;
	contextWindow?: number;
	sessionFile?: string;
	transcriptFile?: string;
	sessionBytes?: number;
	transcriptBytes?: number;
	charsPerToken?: number;
}): ContextPercentEstimate {
	return estimateContextPercent({
		usage: input.usage,
		tokens: input.tokens,
		contextWindow: input.contextWindow,
		sessionBytes: input.sessionBytes ?? fileSizeOrZero(input.sessionFile),
		transcriptBytes: input.transcriptBytes ?? fileSizeOrZero(input.transcriptFile),
		charsPerToken: input.charsPerToken,
	});
}

export function laneSettledFromDisk(input: {
	prep?: HandoffPrepState | null;
	lineage?: HandoffLineage | null;
	currentSessionFile?: string;
}): boolean {
	return handoffLaneSettled({
		prep: input.prep,
		currentSessionFile: input.currentSessionFile,
		lineageSuccessorAt: input.lineage?.successor_at,
		lineageJobId: input.lineage?.child_job_id,
	});
}

export function shouldSpawnSuccessor(input: {
	actions: readonly HandoffLaneAction[];
	settled?: boolean;
	successorJobId?: string;
	successorAt?: string;
}): boolean {
	if (input.settled) return false;
	if (input.successorAt && input.successorJobId) return false;
	return input.actions.includes("switch");
}

export function planOwnerHandoff(input: {
	percent: number;
	prep?: HandoffPrepState | null;
	lineage?: HandoffLineage | null;
	currentSessionFile?: string;
	config?: CompactHandoffConfig;
	compactedInsteadOfHandoff?: boolean;
	hasUI?: boolean;
	mode?: string;
}): ReturnType<typeof planHandoffLane> & { settled: boolean; spawnSuccessor: boolean } {
	const settled = laneSettledFromDisk({
		prep: input.prep,
		lineage: input.lineage,
		currentSessionFile: input.currentSessionFile,
	});
	const plan = planHandoffLane({
		percent: input.percent,
		prepared: Boolean(input.prep?.child_session_file),
		aligned: Boolean(input.prep?.aligned_at),
		switched: settled,
		compactedInsteadOfHandoff: input.compactedInsteadOfHandoff,
		preparePercent: input.config?.handoffPreparePercent,
		alignPercent: input.config?.handoffAlignPercent,
		switchPercent: input.config?.handoffSwitchPercent,
		overflowPercent: input.config?.overflowPercent,
		hasUI: input.hasUI,
		mode: input.mode,
	});
	return {
		...plan,
		settled,
		spawnSuccessor: shouldSpawnSuccessor({
			actions: plan.actions,
			settled,
			successorJobId: input.lineage?.child_job_id || input.prep?.successor_job_id,
			successorAt: input.lineage?.successor_at || input.prep?.successor_at,
		}),
	};
}

export type CursorHandoffHookPayload = {
	hook_event_name?: string;
	conversation_id?: string;
	session_id?: string;
	transcript_path?: string;
	workspace_roots?: string[];
	status?: string;
	loop_count?: number;
	trigger?: string;
	context_usage_percent?: number;
	context_tokens?: number;
	context_window_size?: number;
	message_count?: number;
};

export function cursorOwnerSessionId(payload: CursorHandoffHookPayload): string {
	const raw = payload.conversation_id || payload.session_id || "";
	return raw ? `cursor-${safeSessionId(raw)}` : `cursor-pid-${process.pid}`;
}

export function planCursorHandoffHook(
	payload: CursorHandoffHookPayload,
	opts?: { prep?: HandoffPrepState | null; lineage?: HandoffLineage | null; config?: CompactHandoffConfig },
): ReturnType<typeof planOwnerHandoff> & { estimate: ContextPercentEstimate; ownerId: string } {
	const ownerId = cursorOwnerSessionId(payload);
	const estimate = resolveLanePercent({
		usage: {
			percent: payload.context_usage_percent,
			tokens: payload.context_tokens,
			contextWindow: payload.context_window_size,
		},
		transcriptFile: payload.transcript_path,
		contextWindow: payload.context_window_size,
	});
	const plan = planOwnerHandoff({
		percent: estimate.percent,
		prep: opts?.prep,
		lineage: opts?.lineage,
		config: opts?.config,
		hasUI: true,
		mode: "rpc",
		compactedInsteadOfHandoff: payload.hook_event_name === "preCompact",
	});
	return { ...plan, estimate, ownerId };
}

export function formatSuccessorNotice(input: {
	snapshotPath: string;
	jobId?: string;
	percent?: number;
}): string {
	const pct = typeof input.percent === "number" ? ` (${Math.round(input.percent)}%)` : "";
	const job = input.jobId ? ` job: ${input.jobId}` : "";
	return `Handoff successor spawned${pct}. snapshot: ${input.snapshotPath}${job}`;
}

export function prepPathForOwner(sessionId: string): string {
	return handoffPrepPathForSession(sessionId);
}
