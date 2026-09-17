/**
 * Pointer-based compact/handoff snapshots.
 *
 * Durable state lives on disk. The live model only sees a short pointer.
 * Never serialize the transcript into grok-4.6:fast (or any conversation model).
 */
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join } from "node:path";

export const SNAPSHOT_SCHEMA = "pi.compact-snapshot.v1" as const;
export const SNAPSHOT_MAX_BYTES = 8192;
export const POINTER_MAX_CHARS = 1200;
export const HANDOFF_PROMPT_MAX_CHARS = 800;
export const EXTRACT_MAX_CHARS = 2000;
export const LAST_USER_MAX = 3;
export const LAST_USER_CHARS = 400;
export const LAST_ASSISTANT_CHARS = 600;
export const FILE_LIST_MAX = 20;
export const NEXT_MAX = 6;
export const DEFAULT_CONTEXT_WINDOW = 256_000;
export const DEFAULT_BUDGET_PERCENT = 5;
export const DEFAULT_CHARS_PER_TOKEN = 4;
export const CONFIG_PATH = join(homedir(), ".pi", "agent", "compact-handoff.json");

export const HANDOFF_KINDS = ["implementation", "monitoring", "planning"] as const;
export type HandoffKind = (typeof HANDOFF_KINDS)[number];

export type CompactSnapshot = {
	schema: typeof SNAPSHOT_SCHEMA;
	ts: string;
	session_id: string;
	session_file?: string;
	cwd?: string;
	snapshot_path: string;
	previous_snapshot?: string;
	objective: string;
	last_user: string[];
	last_assistant?: string;
	files_read: string[];
	files_modified: string[];
	case?: string;
	jobs: string[];
	prs: string[];
	blockers: string[];
	next: string[];
	do_not: string[];
	kind: HandoffKind;
	budget_percent: number;
};

export type CompactHandoffConfig = {
	budgetPercent: number;
	/** Last-resort in-place compact only when preferHandoff is false. */
	autoCompactPercent: number;
	/** Start a background handoff session with no human input. Default 60. */
	handoffPreparePercent: number;
	/** Refresh the prepared session from the current snapshot. Default 70. */
	handoffAlignPercent: number;
	/** Cut over to the prepared session. Default 75. */
	handoffSwitchPercent: number;
	overflowPercent: number;
	charsPerToken: number;
	defaultKind: HandoffKind;
	defaultContextWindow: number;
	pointerMaxChars: number;
	promptMaxChars: number;
	extractMaxChars: number;
	snapshotMaxBytes: number;
	/** After compact succeeds, inject a continue turn. Default true. */
	autoContinue: boolean;
	/** Handoff lane is the default; in-place compact is fallback only. */
	preferHandoff: boolean;
	/** Ignore a second auto-compact/handoff inside this window. */
	compactCooldownMs: number;
};

export type CompactLimits = {
	budgetPercent: number;
	budgetTokens: number;
	budgetChars: number;
	pointerMaxChars: number;
	promptMaxChars: number;
	extractMaxChars: number;
	autoCompactPercent: number;
	handoffPreparePercent: number;
	handoffAlignPercent: number;
	handoffSwitchPercent: number;
	overflowPercent: number;
	contextWindow: number;
	kind: HandoffKind;
};

export const HANDOFF_PREP_SCHEMA = "pi.handoff-prep.v1" as const;
export type HandoffLanePhase = "idle" | "prepare" | "align" | "switch" | "overflow";
export type HandoffLaneAction = "prepare" | "align" | "switch";
export type SessionSteerMode = "headless" | "interactive";
export type HandoffSwitchKind = "switch-now" | "push-interactive" | "handoff-now-fallback";
export type HandoffPrepPhase =
	| "prepared"
	| "aligned"
	| "queued"
	| "switched"
	| "successor"
	| "compacted-triage";

export type HandoffPrepState = {
	schema: typeof HANDOFF_PREP_SCHEMA;
	source_session_id: string;
	source_session_file?: string;
	snapshot_path: string;
	child_session_id?: string;
	child_session_file?: string;
	child_job_id?: string;
	successor_job_id?: string;
	lineage_path?: string;
	phase: HandoffPrepPhase;
	mode?: SessionSteerMode;
	prepared_at?: string;
	aligned_at?: string;
	queued_at?: string;
	switched_at?: string;
	successor_at?: string;
	prompt_sent_at?: string;
};

export type ParsedHandoffArgs = {
	llm: boolean;
	silent: boolean;
	kind?: HandoffKind;
	budgetPercent?: number;
	goal: string;
};

export type SnapshotMessage = {
	role?: string;
	content?: unknown;
	summary?: string;
};

export type SnapshotEntry = {
	type: string;
	message?: SnapshotMessage;
	summary?: string;
	details?: { snapshot_path?: string; readFiles?: string[]; modifiedFiles?: string[] };
};

export type FileOpsLike = {
	read?: Iterable<string>;
	written?: Iterable<string>;
	edited?: Iterable<string>;
};

const DEFAULT_DO_NOT = [
	"Do not reload prior transcripts or compaction novels",
	"Do not restate this snapshot in chat",
	"Do not spawn a helper LLM to re-summarize history",
	"Do not parent-read listed files; spawn subagent wait=false",
	"Do not inline file contents into the parent context",
	"Do not ask whether to continue; execute next now",
	"Do not wait for gather on implementation pull-up; execute next now",
	"Do not explain the compact dump unless the operator asked about the harness",
	"Do not treat a compact dump as a finished turn",
	"Do not prefer in-place compact when /handoff-now can continue the work",
	"Do not default to /compact; prepare a handoff at ~60% and switch at ~75%",
	"Do not wait for a human to initialize the background handoff session",
];

export const GATHER_SUBAGENT = "spawn subagent wait=false";
export const CONTINUE_NOW = "continue-now";

const SKIP_USER_RE =
	/^(?:##\s+Files to read first\b|Write the new-session prompt now\b|Read this compact snapshot first\b|schema:\s*pi\.compact-snapshot)/i;

const UUID_RE = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;
const SUBAGENT_RE = /\bsubagent-\d+-[a-z0-9]+\b/gi;
const CBUILD_RE = /\bcbuild-dev-[a-z0-9]+\b/gi;
const CASE_RE = /\.csec\/cases\/[A-Za-z0-9._-]+/g;
const PR_RE = /https?:\/\/github\.com\/[^/\s]+\/[^/\s]+\/pull\/\d+/gi;
const SNAPSHOT_PATH_RE = /(?:snapshot(?:_path)?|Continue from compact snapshot)[:\s]+(\S+\.json)/i;

export function snapshotsRoot(): string {
	return join(homedir(), ".pi", "agent", "snapshots");
}

export function handoffsRoot(): string {
	return join(homedir(), ".pi", "agent", "handoffs");
}

export function handoffPrepPathForSession(sessionId: string): string {
	return join(handoffsRoot(), `${safeSessionId(sessionId)}.json`);
}

export function safeSessionId(raw: string): string {
	return raw.replace(/[^A-Za-z0-9._:-]/g, "_").slice(0, 128);
}

export function snapshotPathForSession(sessionId: string): string {
	return join(snapshotsRoot(), `${safeSessionId(sessionId)}.json`);
}

export function sessionIdFromFile(sessionFile?: string): string {
	if (!sessionFile) return `pid-${process.pid}`;
	return safeSessionId(basename(sessionFile).replace(/\.jsonl$/i, ""));
}

const OWNER_SESSION_ENV_KEYS = ["PI_SESSION_ID", "CDEV_SESSION_STEER_SID", "CDEV_SESSION_ID"] as const;
const SESSION_UUID_RE = /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;

/** File basename `..._<uuid>` and a bare uuid are the same owner. */
export function sessionUuidFromId(raw?: string): string {
	if (!raw) return "";
	const match = safeSessionId(raw).match(SESSION_UUID_RE);
	return match ? match[1] : "";
}

/** Collapse file-id + uuid spellings so two callers cannot claim two prep files. */
export function expandOwnerAliases(ids: readonly string[]): string[] {
	const seen = new Set<string>();
	const out: string[] = [];
	for (const raw of ids) {
		const id = safeSessionId(raw);
		if (!id || seen.has(id)) continue;
		seen.add(id);
		out.push(id);
		const uuid = sessionUuidFromId(id);
		if (uuid && !seen.has(uuid)) {
			seen.add(uuid);
			out.push(uuid);
		}
	}
	return out;
}

/** True when `id` names the same session as `seed` (file-id or uuid). */
export function sessionIdMatches(id?: string, seed?: string): boolean {
	if (!id || !seed) return false;
	if (id === seed) return true;
	const seedUuid = sessionUuidFromId(seed);
	const idUuid = sessionUuidFromId(id);
	if (seedUuid && (id === seedUuid || idUuid === seedUuid)) return true;
	if (idUuid && idUuid === seed) return true;
	return false;
}

export function sessionFileIdsEqual(a?: string, b?: string): boolean {
	if (!a || !b) return false;
	if (a === b) return true;
	return sessionIdFromFile(a) === sessionIdFromFile(b);
}

/** The current session is the prepared child, not the owner of that prep. */
export function isHandoffChildSession(input: {
	childFile?: string;
	currentFile?: string;
}): boolean {
	return sessionFileIdsEqual(input.childFile, input.currentFile);
}

/**
 * Parent prep must not follow the child after switch. The child is a new owner
 * and needs its own sibling / newSession to open a fresh context.
 */
export function resolveLiveHandoffPrep(input: {
	prep?: HandoffPrepState | null;
	currentSessionFile?: string;
}): HandoffPrepState | undefined {
	if (!input.prep) return undefined;
	if (
		isHandoffChildSession({
			childFile: input.prep.child_session_file,
			currentFile: input.currentSessionFile,
		})
	) {
		return undefined;
	}
	return input.prep;
}

/** File basename wins. Env IDs are aliases only when they name this session. */
export function ownerSessionIds(input: {
	sessionFile?: string;
	sessionId?: string;
	env?: NodeJS.ProcessEnv | Record<string, string | undefined>;
}): { canonical: string; aliases: string[] } {
	const env = input.env || {};
	const fromFile = input.sessionFile ? sessionIdFromFile(input.sessionFile) : "";
	const fromApi = input.sessionId ? safeSessionId(input.sessionId) : "";
	const fromEnv = OWNER_SESSION_ENV_KEYS.map((key) => safeSessionId((env[key] || "").trim())).filter(Boolean);
	const seed = fromFile || fromApi;
	const envAliases = seed ? fromEnv.filter((id) => sessionIdMatches(id, fromFile) || sessionIdMatches(id, fromApi)) : fromEnv;
	const aliases = expandOwnerAliases([fromFile, fromApi, ...envAliases]);
	const canonical = fromFile || fromApi || envAliases[0] || `pid-${process.pid}`;
	if (!aliases.includes(canonical)) aliases.unshift(canonical);
	return { canonical, aliases };
}

export function readHandoffPrepAny(ids: readonly string[]): HandoffPrepState | undefined {
	const loaded: HandoffPrepState[] = [];
	for (const id of ids) {
		const prep = readHandoffPrep(id);
		if (prep) loaded.push(prep);
	}
	const withChild = loaded.find((prep) => prep.child_session_file && existsSync(prep.child_session_file));
	return withChild || loaded[0];
}

export function writeHandoffPrepAliases(prep: HandoffPrepState, aliases: readonly string[]): string {
	const path = writeHandoffPrep(prep);
	const canonical = safeSessionId(prep.source_session_id);
	for (const id of expandOwnerAliases(aliases)) {
		if (!id || id === canonical) continue;
		writeHandoffPrep({ ...prep, source_session_id: id });
	}
	return path;
}

export function capText(text: string, maxChars: number): string {
	const normalized = text.replace(/\r\n?/g, "\n").replace(/[ \t]+\n/g, "\n").trim();
	if (normalized.length <= maxChars) return normalized;
	return `${normalized.slice(0, Math.max(0, maxChars - 24)).trimEnd()}\n…[truncated]`;
}

export function uniqueCap(items: string[], maxItems: number, itemChars: number): string[] {
	const seen = new Set<string>();
	const out: string[] = [];
	for (const raw of items) {
		const item = capText(raw, itemChars);
		if (!item || seen.has(item)) continue;
		seen.add(item);
		out.push(item);
		if (out.length >= maxItems) break;
	}
	return out;
}

export function isHandoffKind(value: string): value is HandoffKind {
	return (HANDOFF_KINDS as readonly string[]).includes(value);
}

export function inferHandoffKind(goal: string, fallback: HandoffKind = "implementation"): HandoffKind {
	const text = goal.toLowerCase();
	if (/\b(monitor|watcher|watching|watch|job-bus|cloudbuild|assembler|heartbeat|subscribe)\b/.test(text)) {
		return "monitoring";
	}
	if (/\b(plan|planning|design|decide|architecture|doctrine)\b/.test(text)) {
		return "planning";
	}
	return fallback;
}

export function defaultCompactHandoffConfig(): CompactHandoffConfig {
	return {
		budgetPercent: DEFAULT_BUDGET_PERCENT,
		autoCompactPercent: 80,
		handoffPreparePercent: 60,
		handoffAlignPercent: 70,
		handoffSwitchPercent: 75,
		overflowPercent: 80,
		charsPerToken: DEFAULT_CHARS_PER_TOKEN,
		defaultKind: "implementation",
		defaultContextWindow: DEFAULT_CONTEXT_WINDOW,
		pointerMaxChars: POINTER_MAX_CHARS,
		promptMaxChars: HANDOFF_PROMPT_MAX_CHARS,
		extractMaxChars: EXTRACT_MAX_CHARS,
		snapshotMaxBytes: SNAPSHOT_MAX_BYTES,
		autoContinue: true,
		preferHandoff: true,
		compactCooldownMs: 180_000,
	};
}

export function loadCompactHandoffConfig(): CompactHandoffConfig {
	const base = defaultCompactHandoffConfig();
	try {
		const raw = JSON.parse(readFileSync(CONFIG_PATH, "utf8")) as Partial<CompactHandoffConfig>;
		if (typeof raw.budgetPercent === "number") base.budgetPercent = raw.budgetPercent;
		if (typeof raw.autoCompactPercent === "number") base.autoCompactPercent = raw.autoCompactPercent;
		if (typeof raw.handoffPreparePercent === "number") base.handoffPreparePercent = raw.handoffPreparePercent;
		if (typeof raw.handoffAlignPercent === "number") base.handoffAlignPercent = raw.handoffAlignPercent;
		if (typeof raw.handoffSwitchPercent === "number") base.handoffSwitchPercent = raw.handoffSwitchPercent;
		if (typeof raw.overflowPercent === "number") base.overflowPercent = raw.overflowPercent;
		if (typeof raw.charsPerToken === "number") base.charsPerToken = raw.charsPerToken;
		if (raw.defaultKind && isHandoffKind(raw.defaultKind)) base.defaultKind = raw.defaultKind;
		if (typeof raw.defaultContextWindow === "number") base.defaultContextWindow = raw.defaultContextWindow;
		if (typeof raw.pointerMaxChars === "number") base.pointerMaxChars = raw.pointerMaxChars;
		if (typeof raw.promptMaxChars === "number") base.promptMaxChars = raw.promptMaxChars;
		if (typeof raw.extractMaxChars === "number") base.extractMaxChars = raw.extractMaxChars;
		if (typeof raw.snapshotMaxBytes === "number") base.snapshotMaxBytes = raw.snapshotMaxBytes;
		if (typeof raw.autoContinue === "boolean") base.autoContinue = raw.autoContinue;
		if (typeof raw.preferHandoff === "boolean") base.preferHandoff = raw.preferHandoff;
		if (typeof raw.compactCooldownMs === "number" && raw.compactCooldownMs >= 0) {
			base.compactCooldownMs = raw.compactCooldownMs;
		}
	} catch {
		/* optional */
	}
	const envBudget = Number(process.env.PI_HANDOFF_BUDGET_PERCENT || "");
	if (Number.isFinite(envBudget) && envBudget > 0) base.budgetPercent = envBudget;
	const envKind = (process.env.PI_HANDOFF_KIND || "").trim();
	if (isHandoffKind(envKind)) base.defaultKind = envKind;
	const envContinue = (process.env.PI_HANDOFF_AUTO_CONTINUE || "").trim().toLowerCase();
	if (envContinue === "0" || envContinue === "false") base.autoContinue = false;
	if (envContinue === "1" || envContinue === "true") base.autoContinue = true;
	const envPrefer = (process.env.PI_HANDOFF_PREFER || "").trim().toLowerCase();
	if (envPrefer === "0" || envPrefer === "false") base.preferHandoff = false;
	if (envPrefer === "1" || envPrefer === "true") base.preferHandoff = true;
	const envPrepare = Number(process.env.PI_HANDOFF_PREPARE_PERCENT || "");
	if (Number.isFinite(envPrepare) && envPrepare > 0) base.handoffPreparePercent = envPrepare;
	const envAlign = Number(process.env.PI_HANDOFF_ALIGN_PERCENT || "");
	if (Number.isFinite(envAlign) && envAlign > 0) base.handoffAlignPercent = envAlign;
	const envSwitch = Number(process.env.PI_HANDOFF_SWITCH_PERCENT || "");
	if (Number.isFinite(envSwitch) && envSwitch > 0) base.handoffSwitchPercent = envSwitch;
	return base;
}

function clampLanePercent(value: number, fallback: number): number {
	if (!Number.isFinite(value) || value <= 0) return fallback;
	return Math.min(95, Math.max(10, value));
}

function clampBudgetPercent(value: number): number {
	if (!Number.isFinite(value) || value <= 0) return DEFAULT_BUDGET_PERCENT;
	return Math.min(5, Math.max(0.1, value));
}

export function resolveLimits(input: {
	contextWindow?: number;
	budgetPercent?: number;
	kind?: HandoffKind;
	goal?: string;
	config?: CompactHandoffConfig;
} = {}): CompactLimits {
	const config = input.config || loadCompactHandoffConfig();
	const window = Math.max(8_000, input.contextWindow || config.defaultContextWindow);
	const budgetPercent = clampBudgetPercent(input.budgetPercent ?? config.budgetPercent);
	const budgetTokens = Math.floor((window * budgetPercent) / 100);
	const budgetChars = Math.max(400, budgetTokens * Math.max(1, config.charsPerToken));
	return {
		budgetPercent,
		budgetTokens,
		budgetChars,
		pointerMaxChars: Math.min(config.pointerMaxChars, budgetChars),
		promptMaxChars: Math.min(config.promptMaxChars, budgetChars),
		extractMaxChars: Math.min(config.extractMaxChars, budgetChars),
		autoCompactPercent: config.autoCompactPercent,
		handoffPreparePercent: clampLanePercent(config.handoffPreparePercent, 60),
		handoffAlignPercent: clampLanePercent(config.handoffAlignPercent, 70),
		handoffSwitchPercent: clampLanePercent(config.handoffSwitchPercent, 75),
		overflowPercent: config.overflowPercent,
		contextWindow: window,
		kind: input.kind || inferHandoffKind(input.goal || "", config.defaultKind),
	};
}

export function parseHandoffArgs(args: string): ParsedHandoffArgs {
	const tokens = args.trim().split(/\s+/).filter(Boolean);
	let llm = false;
	let silent = false;
	let kind: HandoffKind | undefined;
	let budgetPercent: number | undefined;
	const rest: string[] = [];
	for (let i = 0; i < tokens.length; i++) {
		const token = tokens[i];
		if (token === "--llm") {
			llm = true;
			continue;
		}
		if (token === "--yes" || token === "--auto" || token === "--silent") {
			silent = true;
			continue;
		}
		if (token === "--type" || token === "--kind") {
			const value = (tokens[++i] || "").trim();
			if (isHandoffKind(value)) kind = value;
			continue;
		}
		if (token.startsWith("--type=") || token.startsWith("--kind=")) {
			const value = token.slice(token.indexOf("=") + 1);
			if (isHandoffKind(value)) kind = value;
			continue;
		}
		if (token === "--budget") {
			const value = Number(tokens[++i]);
			if (Number.isFinite(value)) budgetPercent = value;
			continue;
		}
		if (token.startsWith("--budget=")) {
			const value = Number(token.slice("--budget=".length));
			if (Number.isFinite(value)) budgetPercent = value;
			continue;
		}
		rest.push(token);
	}
	return { llm, silent, kind, budgetPercent, goal: rest.join(" ").trim() };
}

function textFromContent(content: unknown): string {
	if (typeof content === "string") return content;
	if (!Array.isArray(content)) return "";
	const parts: string[] = [];
	for (const block of content) {
		if (!block || typeof block !== "object") continue;
		const rec = block as Record<string, unknown>;
		if (rec.type === "text" && typeof rec.text === "string") parts.push(rec.text);
	}
	return parts.join("\n");
}

function pathsFromContent(content: unknown, read: string[], modified: string[]): void {
	if (!Array.isArray(content)) return;
	for (const block of content) {
		if (!block || typeof block !== "object") continue;
		const rec = block as Record<string, unknown>;
		if (rec.type !== "toolCall" && rec.type !== "tool_use") continue;
		const name = String(rec.name ?? "");
		const args = (rec.arguments ?? rec.input ?? {}) as Record<string, unknown>;
		const path =
			typeof args.path === "string"
				? args.path
				: typeof args.target_notebook === "string"
					? args.target_notebook
					: undefined;
		if (!path) continue;
		if (/^(read|Read|read_file)$/i.test(name)) read.push(path);
		if (/^(write|Write|edit|StrReplace|EditNotebook)$/i.test(name)) modified.push(path);
	}
}

function collectMatches(text: string, re: RegExp): string[] {
	return [...text.matchAll(re)].map((match) => match[0]);
}

function sectionLines(markdown: string, heading: string, maxLines: number): string[] {
	const re = new RegExp(`^#{1,3}\\s+${heading}\\s*$`, "im");
	const match = re.exec(markdown);
	if (!match || match.index === undefined) return [];
	const start = match.index + match[0].length;
	const rest = markdown.slice(start);
	const next = rest.search(/^#{1,3}\s+/m);
	const body = (next >= 0 ? rest.slice(0, next) : rest).trim();
	return body
		.split("\n")
		.map((line) => line.replace(/^\s*(?:[-*]|\d+[.)]|\[.\]|:)\s*/, "").trim())
		.filter((line) => line && line !== "---")
		.slice(0, maxLines);
}

function isSkipUser(text: string): boolean {
	const trimmed = text.trim();
	return (
		SKIP_USER_RE.test(trimmed) ||
		trimmed.includes("## Files to read first") ||
		trimmed.includes("## Conversation History") ||
		trimmed.includes("compact-snapshot")
	);
}

export function isHarnessRedirect(text: string): boolean {
	return /\b(?:p0|profile[- ]level|coding agent harness|fix (?:this|the) (?:compact|handoff|continuation)|never happen again|handoffs? are preferred)\b/i.test(
		text,
	);
}

export function isCompactMetaUser(text: string): boolean {
	const trimmed = text.trim();
	if (!trimmed) return true;
	if (isSkipUser(trimmed)) return true;
	if (/\b(?:continue-now|handoff-now|Execute Goal\/next now)\b/i.test(trimmed)) return true;
	if (
		trimmed.length < 120 &&
		/^(?:what happened|huh\??|continue(?: please)?|why did (?:you|we) stop)\b/i.test(trimmed)
	) {
		return true;
	}
	return false;
}

export function readSnapshot(path: string): CompactSnapshot | undefined {
	try {
		const raw = JSON.parse(readFileSync(path, "utf8")) as Partial<CompactSnapshot>;
		if (!raw || raw.schema !== SNAPSHOT_SCHEMA) return undefined;
		if (typeof raw.objective !== "string" || typeof raw.snapshot_path !== "string") return undefined;
		return raw as CompactSnapshot;
	} catch {
		return undefined;
	}
}

export function applyPreviousSnapshot(
	current: CompactSnapshot,
	previous?: CompactSnapshot,
): CompactSnapshot {
	if (!previous) return current;
	const users = current.last_user;
	const allMeta =
		users.length === 0 ||
		users.every((item) => isCompactMetaUser(item) && !isHarnessRedirect(item));
	if (!allMeta) return current;
	return {
		...current,
		objective: previous.objective || current.objective,
		next: previous.next.length ? previous.next : current.next,
		case: current.case || previous.case,
		files_read: uniqueCap([...previous.files_read, ...current.files_read], FILE_LIST_MAX, 240),
		files_modified: uniqueCap(
			[...previous.files_modified, ...current.files_modified],
			FILE_LIST_MAX,
			240,
		),
		prs: uniqueCap([...previous.prs, ...current.prs], 6, 160),
		jobs: uniqueCap([...previous.jobs, ...current.jobs], 8, 80),
		blockers: current.blockers.length ? current.blockers : previous.blockers,
	};
}

function iterableToList(value?: Iterable<string>): string[] {
	if (!value) return [];
	return [...value].filter((item) => typeof item === "string" && item.trim());
}

export function buildSnapshot(input: {
	branch?: SnapshotEntry[];
	fileOps?: FileOpsLike;
	previousSummary?: string;
	sessionFile?: string;
	cwd?: string;
	goal?: string;
	sessionId?: string;
	now?: string;
	kind?: HandoffKind;
	budgetPercent?: number;
	contextWindow?: number;
}): CompactSnapshot {
	const branch = input.branch ?? [];
	const lastUser: string[] = [];
	const read: string[] = iterableToList(input.fileOps?.read);
	const modified = [
		...iterableToList(input.fileOps?.written),
		...iterableToList(input.fileOps?.edited),
	];
	let lastAssistant = "";
	let previousSnapshot = "";
	const haystacks: string[] = [];

	for (const entry of branch) {
		if (entry.type === "compaction" || entry.type === "branch_summary") {
			const summary = entry.summary ?? entry.message?.summary ?? "";
			if (summary) haystacks.push(summary);
			const fromDetails = entry.details?.snapshot_path;
			const fromText = SNAPSHOT_PATH_RE.exec(summary)?.[1];
			previousSnapshot = fromDetails || fromText || previousSnapshot;
			if (entry.details?.readFiles) read.push(...entry.details.readFiles);
			if (entry.details?.modifiedFiles) modified.push(...entry.details.modifiedFiles);
			continue;
		}
		if (entry.type !== "message" || !entry.message) continue;
		const message = entry.message;
		if (message.role === "compactionSummary" && message.summary) {
			haystacks.push(message.summary);
			previousSnapshot = SNAPSHOT_PATH_RE.exec(message.summary)?.[1] || previousSnapshot;
			continue;
		}
		const text = message.summary || textFromContent(message.content);
		pathsFromContent(message.content, read, modified);
		if (message.role === "user") {
			if (text && !isSkipUser(text) && !(isCompactMetaUser(text) && !isHarnessRedirect(text))) {
				lastUser.push(text);
			}
			if (text) haystacks.push(text);
		} else if (message.role === "assistant") {
			if (text) {
				lastAssistant = text;
				haystacks.push(text);
			}
		}
	}

	if (input.previousSummary) {
		haystacks.push(input.previousSummary);
		previousSnapshot = SNAPSHOT_PATH_RE.exec(input.previousSummary)?.[1] || previousSnapshot;
	}

	const joined = haystacks.join("\n");
	const recentUsers = uniqueCap(lastUser.slice(-LAST_USER_MAX), LAST_USER_MAX, LAST_USER_CHARS);
	const objective = capText(
		input.goal?.trim() || recentUsers.at(-1) || "Continue current work",
		240,
	);
	const nextFromSummary = sectionLines(input.previousSummary || "", "Next Steps", NEXT_MAX);
	const nextFromAssistant = lastAssistant
		.split("\n")
		.map((line) => line.trim())
		.filter((line) => /^next:/i.test(line) || /^\s*-\s+/.test(line))
		.slice(0, NEXT_MAX);
	const next = uniqueCap(
		[input.goal?.trim(), ...nextFromSummary, ...nextFromAssistant].filter((item): item is string => Boolean(item)),
		NEXT_MAX,
		200,
	);
	const blockers = uniqueCap(sectionLines(input.previousSummary || lastAssistant, "Blocked", 4), 4, 160);
	const sessionId = input.sessionId || sessionIdFromFile(input.sessionFile);
	const snapshotPath = snapshotPathForSession(sessionId);
	const limits = resolveLimits({
		kind: input.kind,
		goal: input.goal || objective,
		budgetPercent: input.budgetPercent,
		contextWindow: input.contextWindow,
	});

	const built: CompactSnapshot = {
		schema: SNAPSHOT_SCHEMA,
		ts: input.now || new Date().toISOString(),
		session_id: sessionId,
		session_file: input.sessionFile,
		cwd: input.cwd,
		snapshot_path: snapshotPath,
		previous_snapshot: previousSnapshot || undefined,
		kind: limits.kind,
		budget_percent: limits.budgetPercent,
		objective,
		last_user: recentUsers,
		last_assistant: lastAssistant ? capText(lastAssistant, LAST_ASSISTANT_CHARS) : undefined,
		files_read: uniqueCap(read, FILE_LIST_MAX, 240),
		files_modified: uniqueCap(modified, FILE_LIST_MAX, 240),
		case: collectMatches(joined, CASE_RE).at(-1),
		jobs: uniqueCap([...collectMatches(joined, UUID_RE), ...collectMatches(joined, SUBAGENT_RE), ...collectMatches(joined, CBUILD_RE)], 8, 80),
		prs: uniqueCap(collectMatches(joined, PR_RE), 6, 160),
		blockers,
		next: next.length ? next : [objective],
		do_not: DEFAULT_DO_NOT,
	};
	const priorPath = previousSnapshot && previousSnapshot !== snapshotPath ? previousSnapshot : undefined;
	return applyPreviousSnapshot(built, priorPath ? readSnapshot(priorPath) : undefined);
}

function shrinkSnapshot(snapshot: CompactSnapshot): CompactSnapshot {
	let current = { ...snapshot };
	const dropOrder: Array<(item: CompactSnapshot) => CompactSnapshot> = [
		(item) => ({ ...item, last_assistant: undefined }),
		(item) => ({ ...item, last_user: item.last_user.slice(-1) }),
		(item) => ({ ...item, files_read: item.files_read.slice(0, 8) }),
		(item) => ({ ...item, files_modified: item.files_modified.slice(0, 8) }),
		(item) => ({ ...item, jobs: item.jobs.slice(0, 3), prs: item.prs.slice(0, 2) }),
		(item) => ({ ...item, last_user: [] }),
	];
	for (const drop of dropOrder) {
		if (Buffer.byteLength(JSON.stringify(current), "utf8") <= SNAPSHOT_MAX_BYTES) break;
		current = drop(current);
	}
	return current;
}

export function snapshotJson(snapshot: CompactSnapshot): string {
	return `${JSON.stringify(shrinkSnapshot(snapshot), null, 2)}\n`;
}

export function writeSnapshot(snapshot: CompactSnapshot, extraPath?: string): string {
	const body = snapshotJson(snapshot);
	const path = snapshot.snapshot_path;
	mkdirSync(dirname(path), { recursive: true });
	writeFileSync(path, body);
	if (extraPath) {
		mkdirSync(dirname(extraPath), { recursive: true });
		writeFileSync(extraPath, body);
	}
	return path;
}

export function caseSnapshotPath(snapshot: CompactSnapshot): string | undefined {
	if (!snapshot.case) return undefined;
	const caseDir = snapshot.cwd && !isAbsolute(snapshot.case) ? join(snapshot.cwd, snapshot.case) : snapshot.case;
	if (!existsSync(caseDir)) return undefined;
	return join(caseDir, "compact-snapshot.json");
}

export function persistSnapshot(snapshot: CompactSnapshot): { path: string; casePath?: string } {
	const casePath = caseSnapshotPath(snapshot);
	const path = writeSnapshot(snapshot, casePath);
	return { path, casePath };
}

export function formatPointerSummary(snapshot: CompactSnapshot, maxChars?: number): string {
	const limits = resolveLimits({ kind: snapshot.kind, budgetPercent: snapshot.budget_percent });
	const lines = [
		`schema: ${SNAPSHOT_SCHEMA}`,
		`snapshot: ${snapshot.snapshot_path}`,
		`kind: ${snapshot.kind}`,
		`budget: ${snapshot.budget_percent}%`,
		`objective: ${snapshot.objective}`,
	];
	if (snapshot.cwd) lines.push(`cwd: ${snapshot.cwd}`);
	if (snapshot.case) lines.push(`case: ${snapshot.case}`);
	if (snapshot.next.length) lines.push(`next: ${snapshot.next.join("; ")}`);
	if (snapshot.blockers.length) lines.push(`blockers: ${snapshot.blockers.join("; ")}`);
	if (snapshot.files_modified.length) {
		lines.push(`files_modified: ${snapshot.files_modified.slice(0, 8).join(", ")}`);
	}
	if (snapshot.files_read.length) {
		lines.push(`files_read: ${snapshot.files_read.slice(0, 8).join(", ")}`);
	}
	if (snapshot.jobs.length) lines.push(`jobs: ${snapshot.jobs.slice(0, 4).join(", ")}`);
	lines.push(`action: ${CONTINUE_NOW}`);
	lines.push(`gather: ${GATHER_SUBAGENT} execute next/objective; do not parent-read listed files`);
	lines.push("rule: Read the snapshot. Do not restate, ask, or explain this compact. Execute next now.");
	return capText(lines.join("\n"), maxChars ?? limits.pointerMaxChars);
}

function kindPromptBody(kind: HandoffKind): string {
	if (kind === "monitoring") {
		return [
			"Subscribe job_bus named lanes only in the owner pi session (session:SID / targetSid). Cursor chats stay inbox-only. Do not kill running jobs.",
			`Inspect status only via ${GATHER_SUBAGENT}. Do not parent-read logs.`,
		].join("\n");
	}
	if (kind === "planning") {
		return [
			`Gather listed files via ${GATHER_SUBAGENT}. Do not parent-read them.`,
			"Do not implement unless the operator asks.",
		].join("\n");
	}
	return [
		`Spawn worker wait=false to execute snapshot next/objective. Do not parent-read listed files.`,
		"Parent executes next in this same turn. Do not wait for gather. Ignore planning-only wait-for-gather wrappers.",
		"Prepare a background handoff at ~60% and switch at ~75%. Do not default to /compact. Do not ask whether to continue.",
	].join("\n");
}

export function formatHandoffPrompt(
	snapshot: CompactSnapshot,
	goal: string,
	maxChars?: number,
): string {
	const limits = resolveLimits({ kind: snapshot.kind, budgetPercent: snapshot.budget_percent, goal });
	const task = capText(goal.trim() || snapshot.objective, 240);
	const prompt = [
		"Read this compact snapshot first. Do not restate it. Do not reload transcripts.",
		"",
		`snapshot: ${snapshot.snapshot_path}`,
		`kind: ${snapshot.kind}`,
		`budget: ${snapshot.budget_percent}% of context`,
		`Goal: ${task}`,
		"",
		kindPromptBody(snapshot.kind),
		"Execute Goal/next now. Do not ask. Do not explain this compact. A dump is not done.",
	].join("\n");
	return capText(prompt, maxChars ?? limits.promptMaxChars);
}

export function formatContinueWorkerTask(snapshot: CompactSnapshot): string {
	const next = snapshot.next[0] || snapshot.objective;
	return capText(
		`Read snapshot ${snapshot.snapshot_path}. Execute: ${snapshot.objective}. Next: ${next}. Do not restate. Do not ask. Report blockers/deltas only.`,
		500,
	);
}

export function shouldAutoContinue(input: {
	willRetry?: boolean;
	autoContinue?: boolean;
}): boolean {
	return input.autoContinue !== false;
}

export function continueInjectOptions(input: {
	willRetry?: boolean;
	idle?: boolean;
}): { deliverAs: "steer" | "followUp"; triggerTurn: true } {
	if (input.willRetry || input.idle === false) {
		return { deliverAs: "steer", triggerTurn: true };
	}
	return { deliverAs: "followUp", triggerTurn: true };
}

export function formatHandoffNowCommand(snapshot: CompactSnapshot): string {
	const goal = capText(snapshot.next[0] || snapshot.objective, 200).replace(/\n+/g, " ");
	return `/handoff-now --type ${snapshot.kind} --budget ${snapshot.budget_percent} ${goal}`;
}

export function formatHandoffPrepareCommand(snapshot: CompactSnapshot): string {
	const goal = capText(snapshot.next[0] || snapshot.objective, 200).replace(/\n+/g, " ");
	return `/handoff-prepare --type ${snapshot.kind} --budget ${snapshot.budget_percent} ${goal}`;
}

export function formatHandoffPreparePrompt(
	snapshot: CompactSnapshot,
	goal: string,
	maxChars?: number,
): string {
	const limits = resolveLimits({ kind: snapshot.kind, budgetPercent: snapshot.budget_percent, goal });
	const task = capText(goal.trim() || snapshot.objective, 240);
	const prompt = [
		"Read this compact snapshot first. Do not restate it. Do not reload transcripts.",
		"",
		`snapshot: ${snapshot.snapshot_path}`,
		`kind: ${snapshot.kind}`,
		`budget: ${snapshot.budget_percent}% of context`,
		`Goal: ${task}`,
		"",
		"This is a background handoff warm-up. Get up to speed with the snapshot.",
		"Do not replace the owner session. Do not take over owner work. Do not ask.",
		"Report ready when aligned. Wait for align/switch.",
	].join("\n");
	return capText(prompt, maxChars ?? limits.promptMaxChars);
}

export function formatHandoffAlignPrompt(
	snapshot: CompactSnapshot,
	goal: string,
	maxChars?: number,
): string {
	const limits = resolveLimits({ kind: snapshot.kind, budgetPercent: snapshot.budget_percent, goal });
	const task = capText(goal.trim() || snapshot.objective, 240);
	const prompt = [
		"Snapshot refreshed. Align with the current owner session.",
		"",
		`snapshot: ${snapshot.snapshot_path}`,
		`kind: ${snapshot.kind}`,
		`Goal: ${task}`,
		"",
		"Stay ready for cutover. Do not take over until switch. Do not ask.",
	].join("\n");
	return capText(prompt, maxChars ?? limits.promptMaxChars);
}

export function readHandoffPrep(sessionId: string): HandoffPrepState | undefined {
	try {
		const raw = JSON.parse(readFileSync(handoffPrepPathForSession(sessionId), "utf8")) as Partial<HandoffPrepState>;
		if (!raw || raw.schema !== HANDOFF_PREP_SCHEMA) return undefined;
		if (typeof raw.source_session_id !== "string" || typeof raw.snapshot_path !== "string") return undefined;
		return raw as HandoffPrepState;
	} catch {
		return undefined;
	}
}

export function writeHandoffPrep(prep: HandoffPrepState): string {
	const path = handoffPrepPathForSession(prep.source_session_id);
	mkdirSync(dirname(path), { recursive: true });
	writeFileSync(path, `${JSON.stringify(prep, null, 2)}\n`);
	return path;
}

export function handoffChildReady(input: {
	sessionFile?: string;
	jobStatus?: string;
	assistantCount?: number;
	fileExists?: boolean;
}): boolean {
	if (input.jobStatus === "succeeded") return true;
	if ((input.assistantCount ?? 0) > 0) return true;
	if (input.fileExists || (input.sessionFile && existsSync(input.sessionFile))) return true;
	return false;
}

/** Switch-ready: warmed/aligned, or a same-tick sibling file we just created (no warm-up). */
export function handoffSwitchReady(input: {
	fileExists?: boolean;
	jobStatus?: string;
	assistantCount?: number;
	aligned?: boolean;
	sameTickCreate?: boolean;
}): boolean {
	if (input.sameTickCreate && input.fileExists) return true;
	if (input.aligned) return true;
	if (input.jobStatus === "succeeded") return true;
	if ((input.assistantCount ?? 0) > 0) return true;
	return false;
}

export type HandoffSwitchTarget = "switch-sibling" | "new-session" | "defer";

export type HandoffPrepClaim = Pick<
	HandoffPrepState,
	| "prompt_sent_at"
	| "prepared_at"
	| "child_job_id"
	| "child_session_file"
	| "switched_at"
	| "successor_at"
	| "successor_job_id"
	| "phase"
>;

export type ContextUsageLike = {
	percent?: number | null;
	tokens?: number | null;
	contextWindow?: number;
};

export type ContextPercentEstimate = {
	percent: number;
	source: "usage" | "tokens" | "session-file" | "transcript" | "unknown";
};

function clampReportedPercent(value: number): number {
	if (!Number.isFinite(value) || value < 0) return 0;
	return Math.min(200, value);
}

/**
 * Prefer live usage.percent. Cursor host and post-compact pi often have
 * percent === null; fall back to tokens, then session/transcript bytes.
 */
export function estimateContextPercent(input: {
	usage?: ContextUsageLike | null;
	tokens?: number | null;
	contextWindow?: number;
	sessionBytes?: number;
	transcriptBytes?: number;
	charsPerToken?: number;
}): ContextPercentEstimate {
	const window =
		(input.usage?.contextWindow && input.usage.contextWindow > 0
			? input.usage.contextWindow
			: undefined) ||
		(input.contextWindow && input.contextWindow > 0 ? input.contextWindow : undefined) ||
		DEFAULT_CONTEXT_WINDOW;
	const usagePercent = input.usage?.percent;
	if (typeof usagePercent === "number" && Number.isFinite(usagePercent)) {
		return { percent: clampReportedPercent(usagePercent), source: "usage" };
	}
	const tokens = input.usage?.tokens ?? input.tokens;
	if (typeof tokens === "number" && Number.isFinite(tokens) && tokens > 0 && window > 0) {
		return { percent: clampReportedPercent((tokens / window) * 100), source: "tokens" };
	}
	const cpt = input.charsPerToken && input.charsPerToken > 0 ? input.charsPerToken : DEFAULT_CHARS_PER_TOKEN;
	if (input.transcriptBytes && input.transcriptBytes > 0 && window > 0) {
		const transcriptCpt = Math.max(cpt, 8);
		return {
			percent: clampReportedPercent((input.transcriptBytes / transcriptCpt / window) * 100),
			source: "transcript",
		};
	}
	if (input.sessionBytes && input.sessionBytes > 0 && window > 0) {
		return {
			percent: clampReportedPercent((input.sessionBytes / cpt / window) * 100),
			source: "session-file",
		};
	}
	return { percent: 0, source: "unknown" };
}

/**
 * A queued /handoff-now or owner-editor dump is not a finished switch.
 * Settled only when we are already the child, or a successor worker exists.
 */
export function handoffLaneSettled(input: {
	prep?: Pick<
		HandoffPrepState,
		"phase" | "switched_at" | "successor_at" | "successor_job_id" | "child_session_file" | "child_job_id"
	> | null;
	currentSessionFile?: string;
	lineageSuccessorAt?: string;
	lineageJobId?: string;
}): boolean {
	const prep = input.prep;
	if (
		isHandoffChildSession({
			childFile: prep?.child_session_file,
			currentFile: input.currentSessionFile,
		})
	) {
		return true;
	}
	if (input.lineageSuccessorAt && input.lineageJobId) return true;
	if (prep?.phase === "successor" && (prep.successor_job_id || prep.child_job_id) && prep.successor_at) {
		return true;
	}
	return false;
}

/** Claim/warmup is live: sibling path not ready, job running, or prepared_at still inside the claim TTL. */
export function handoffPrepInFlight(input: {
	childFile?: string;
	fileExists?: boolean;
	preparedAt?: string;
	childJobId?: string;
	now?: number;
	claimTtlMs?: number;
	currentSessionFile?: string;
}): boolean {
	if (isHandoffChildSession({ childFile: input.childFile, currentFile: input.currentSessionFile })) {
		return false;
	}
	if (input.fileExists === true) return false;
	if (input.childFile) return true;
	if (input.childJobId) return true;
	if (!input.preparedAt) return false;
	const age = (input.now ?? Date.now()) - Date.parse(input.preparedAt);
	const ttl = input.claimTtlMs ?? HANDOFF_PREP_CLAIM_TTL_MS;
	return Number.isFinite(age) && age >= 0 && age < ttl;
}

export function handoffPrepIsInFlight(
	prep?: HandoffPrepClaim | null,
	opts?: { fileExists?: boolean; now?: number; claimTtlMs?: number; currentSessionFile?: string },
): boolean {
	if (!prep) return false;
	if (
		isHandoffChildSession({
			childFile: prep.child_session_file,
			currentFile: opts?.currentSessionFile,
		})
	) {
		return false;
	}
	const fileExists =
		opts?.fileExists ??
		Boolean(prep.child_session_file && existsSync(prep.child_session_file));
	return handoffPrepInFlight({
		childFile: prep.child_session_file,
		fileExists,
		preparedAt: prep.prepared_at,
		childJobId: prep.child_job_id,
		now: opts?.now,
		claimTtlMs: opts?.claimTtlMs,
		currentSessionFile: opts?.currentSessionFile,
	});
}

/** Warm-up print and ctx.newSession must not both emit the pointer in one tick. */
export function shouldFallbackNewSession(input: {
	siblingFileExists?: boolean;
	prepInFlight?: boolean;
	sameTickPrepare?: boolean;
	spawnWarmup?: boolean;
	siblingIsCurrent?: boolean;
}): boolean {
	if (input.siblingIsCurrent) {
		if (input.prepInFlight) return false;
		if (input.sameTickPrepare) return false;
		if (input.spawnWarmup) return false;
		return true;
	}
	if (input.siblingFileExists) return false;
	if (input.prepInFlight) return false;
	if (input.sameTickPrepare) return false;
	if (input.spawnWarmup) return false;
	return true;
}

/** A live sibling file must be switched into. newSession is only when no sibling exists. */
export function handoffSwitchTarget(input: {
	siblingFileExists?: boolean;
	switchSessionAvailable?: boolean;
	prepInFlight?: boolean;
	sameTickPrepare?: boolean;
	spawnWarmup?: boolean;
	siblingIsCurrent?: boolean;
}): HandoffSwitchTarget {
	const siblingExists = input.siblingFileExists === true && input.siblingIsCurrent !== true;
	if (siblingExists) {
		return input.switchSessionAvailable ? "switch-sibling" : "defer";
	}
	if (!shouldFallbackNewSession({ ...input, siblingFileExists: false })) return "defer";
	return "new-session";
}

/** Warm-up print jobs compete with the switch prompt. Skip them when switching in the same tick. */
export function shouldSpawnHandoffWarmup(actions: readonly HandoffLaneAction[]): boolean {
	return actions.includes("prepare") && !actions.includes("switch");
}

/**
 * Destination (replacement) still needs the pointer until switch completes.
 * An owner-editor dump sets `prompt_sent_at` and must not count as delivered.
 */
export function shouldInjectHandoffPrompt(
	prep?: Pick<HandoffPrepState, "prompt_sent_at" | "switched_at" | "successor_at" | "phase"> | null,
): boolean {
	if (prep?.switched_at) return false;
	if (prep?.phase === "successor" && prep.successor_at) return false;
	return true;
}

/**
 * Queue one `/handoff-now` when this stack cannot switchSession itself.
 * Event handlers never have switchSession (command-only; deadlock). Interactive
 * used to block the queue and wait forever — that is the 94% stuck-owner failure.
 * An owner-editor dump (`prompt_sent_at` without a switch) must not block the
 * event-path queue. Command ctx with switchSession stays editor-only and must
 * not re-queue itself.
 */
export function shouldQueueHandoffNowAfterSwitch(input: {
	promptDelivered?: boolean;
	mode?: SessionSteerMode;
	switchSessionAvailable?: boolean;
}): boolean {
	if (input.switchSessionAvailable === false) return true;
	if (input.promptDelivered) return false;
	if (input.mode === "interactive") return false;
	return true;
}

/** /handoff-now owner fallback: one headless followUp until switch completes. Owner-editor dump is not a switch. */
export function shouldFallbackHandoffPrompt(input: {
	prep?: HandoffPrepClaim | null;
	mode?: SessionSteerMode;
	fileExists?: boolean;
	now?: number;
}): boolean {
	if (handoffPrepIsInFlight(input.prep, { fileExists: input.fileExists, now: input.now })) {
		return false;
	}
	return shouldQueueHandoffNowAfterSwitch({
		promptDelivered: Boolean(input.prep?.switched_at || input.prep?.successor_at),
		mode: input.mode,
	});
}

/** Compact-triage injectContinue must not fire after the switch prompt already landed. */
export function shouldInjectContinueAfterLane(input: {
	handoffQueued?: boolean;
	prep?: Pick<HandoffPrepState, "prompt_sent_at"> | null;
}): boolean {
	if (input.handoffQueued) return false;
	return !input.prep?.prompt_sent_at;
}

/** Defer / /handoff-now fallback: one owner editor, and only if the pointer has not already landed. */
export function shouldPushOwnerEditorOnDefer(input: {
	mode?: SessionSteerMode;
	hasUI?: boolean;
	prep?: Pick<HandoffPrepState, "prompt_sent_at"> | null;
}): boolean {
	if (input.mode !== "interactive") return false;
	if (input.hasUI !== true) return false;
	return !input.prep?.prompt_sent_at;
}

export const HANDOFF_PREP_CLAIM_TTL_MS = 5000;

/** Create a sibling only when none exists and no recent in-flight claim is holding the slot. */
export function shouldCreateHandoffSibling(input: {
	childFile?: string;
	fileExists?: boolean;
	preparedAt?: string;
	now?: number;
	claimTtlMs?: number;
	currentSessionFile?: string;
}): boolean {
	if (isHandoffChildSession({ childFile: input.childFile, currentFile: input.currentSessionFile })) {
		return true;
	}
	if (input.fileExists === true) return false;
	if (input.fileExists === false) return true;
	if (input.childFile && input.fileExists !== false) return false;
	if (!input.preparedAt) return true;
	const age = (input.now ?? Date.now()) - Date.parse(input.preparedAt);
	const ttl = input.claimTtlMs ?? HANDOFF_PREP_CLAIM_TTL_MS;
	if (Number.isFinite(age) && age >= 0 && age < ttl) return false;
	return true;
}

/** Exclusive prepare claim so two callers in the same tick cannot both create siblings. */
export function tryClaimHandoffPrep(
	prep: HandoffPrepState,
	aliases: readonly string[] = [],
): {
	claimed: boolean;
	path: string;
	existing?: HandoffPrepState;
} {
	const unique = expandOwnerAliases([prep.source_session_id, ...aliases]);
	const existing = readHandoffPrepAny(unique);
	const path = handoffPrepPathForSession(prep.source_session_id);
	if (existing) {
		return { claimed: false, path, existing };
	}
	for (const id of unique) {
		if (existsSync(handoffPrepPathForSession(id))) {
			return { claimed: false, path, existing: readHandoffPrep(id) };
		}
	}
	const created: string[] = [];
	try {
		for (const id of unique) {
			const aliasPath = handoffPrepPathForSession(id);
			mkdirSync(dirname(aliasPath), { recursive: true });
			writeFileSync(aliasPath, `${JSON.stringify({ ...prep, source_session_id: id }, null, 2)}\n`, { flag: "wx" });
			created.push(aliasPath);
		}
		return { claimed: true, path };
	} catch (error) {
		for (const createdPath of created) {
			try {
				unlinkSync(createdPath);
			} catch {
				/* keep first writer's files */
			}
		}
		const code = error && typeof error === "object" && "code" in error ? String((error as { code?: string }).code) : "";
		if (code === "EEXIST") {
			return { claimed: false, path, existing: readHandoffPrepAny(unique) || readHandoffPrep(prep.source_session_id) };
		}
		throw error;
	}
}

/** Keep the first live sibling. A second prepare must not retarget the owner. */
export function keepLiveHandoffChild(
	previous?: Pick<HandoffPrepState, "child_session_file" | "child_session_id" | "child_job_id"> | null,
	currentSessionFile?: string,
): Partial<HandoffPrepState> {
	if (!previous?.child_session_file || !existsSync(previous.child_session_file)) return {};
	if (isHandoffChildSession({ childFile: previous.child_session_file, currentFile: currentSessionFile })) {
		return {};
	}
	return {
		child_session_file: previous.child_session_file,
		child_session_id: previous.child_session_id,
		child_job_id: previous.child_job_id,
	};
}

/** newSession only when no sibling file exists and no in-flight prepare claim is holding the slot. */
export function shouldOpenNewHandoffSession(input: {
	target?: HandoffSwitchTarget;
	siblingFileExists?: boolean;
	childFile?: string;
	childJobId?: string;
	preparedAt?: string;
	sameTickPrepare?: boolean;
	spawnWarmup?: boolean;
	now?: number;
	claimTtlMs?: number;
	currentSessionFile?: string;
}): boolean {
	if (input.target && input.target !== "new-session") return false;
	const siblingIsCurrent = isHandoffChildSession({
		childFile: input.childFile,
		currentFile: input.currentSessionFile,
	});
	return shouldFallbackNewSession({
		siblingFileExists: siblingIsCurrent ? false : input.siblingFileExists,
		siblingIsCurrent,
		prepInFlight: handoffPrepInFlight({
			childFile: siblingIsCurrent ? undefined : input.childFile,
			fileExists: siblingIsCurrent ? false : input.siblingFileExists,
			preparedAt: siblingIsCurrent ? undefined : input.preparedAt,
			childJobId: siblingIsCurrent ? undefined : input.childJobId,
			now: input.now,
			claimTtlMs: input.claimTtlMs,
			currentSessionFile: input.currentSessionFile,
		}),
		sameTickPrepare: input.sameTickPrepare,
		spawnWarmup: input.spawnWarmup,
	});
}

export function sessionSteerMode(input: {
	hasUI?: boolean;
	mode?: string;
	env?: NodeJS.ProcessEnv | Record<string, string | undefined>;
}): SessionSteerMode {
	const env = input.env || process.env;
	const forced = (env.PI_HANDOFF_STEER_MODE || env.PI_HANDOFF_MODE || "").toLowerCase();
	if (forced === "headless" || forced === "interactive") return forced;
	const mode = (input.mode || "").toLowerCase();
	if (mode === "print" || mode === "json") return "headless";
	if (input.hasUI === false) return "headless";
	if (input.hasUI === true) return "interactive";
	if (mode === "tui" || mode === "rpc") return "interactive";
	return "headless";
}

export function handoffSwitchAction(input: {
	mode: SessionSteerMode;
	prepared?: boolean;
}): HandoffSwitchKind {
	if (!input.prepared) return "handoff-now-fallback";
	return input.mode === "interactive" ? "push-interactive" : "switch-now";
}

export type HandoffSwitchPresentation = {
	switchKind: HandoffSwitchKind;
	confirm: false;
	sendUserMessage: boolean;
	sendDeliverAs: "followUp";
	owner: { notify: boolean; setEditorText: boolean };
	replacement: { notify: boolean; setEditorText: boolean };
};

/** Live switch side-effects. Never confirm. Interactive: editor only. Headless: one followUp. */
export function handoffSwitchPresentation(input: {
	mode: SessionSteerMode;
	hasUI?: boolean;
	replacementHasUI?: boolean;
	prepared?: boolean;
	promptAlreadySent?: boolean;
}): HandoffSwitchPresentation {
	const switchKind = handoffSwitchAction(input);
	const ownerInteractive = input.mode === "interactive" && input.hasUI === true;
	const replacementHasUI = input.replacementHasUI ?? input.hasUI;
	const sendUserMessage = input.mode === "headless" && input.promptAlreadySent !== true;
	const switchingIntoReplacement = input.prepared === true && replacementHasUI === true;
	return {
		switchKind,
		confirm: false,
		sendUserMessage,
		sendDeliverAs: "followUp",
		owner: {
			notify: ownerInteractive,
			// One pointer: destination editor on switch; owner editor only when we stay here.
			setEditorText: ownerInteractive && !switchingIntoReplacement,
		},
		replacement: {
			notify: replacementHasUI === true,
			setEditorText: input.mode === "interactive" && replacementHasUI === true,
		},
	};
}

export function describeHandoffSwitchEffects(presentation: HandoffSwitchPresentation): string[] {
	const traces: string[] = [];
	if (presentation.confirm) traces.push("confirm");
	if (presentation.owner.notify) traces.push("owner.notify");
	if (presentation.owner.setEditorText) traces.push("owner.editor");
	if (presentation.replacement.notify) traces.push("replacement.notify");
	if (presentation.replacement.setEditorText) traces.push("replacement.editor");
	if (presentation.sendUserMessage) traces.push(`replacement.send.${presentation.sendDeliverAs}`);
	traces.push(`kind.${presentation.switchKind}`);
	return traces;
}

export type HandoffSwitchUi = {
	hasUI: boolean;
	notify?: (message: string, level?: string) => void;
	setEditorText?: (text: string) => void;
	sendUserMessage?: (text: string, opts: { deliverAs: "followUp" | "steer" }) => Promise<void> | void;
};

/** Apply the same side-effects the live extensions use. Tests drive this with fake UIs. */
export async function applyHandoffSwitchEffects(input: {
	presentation: HandoffSwitchPresentation;
	prompt: string;
	snapshotPath: string;
	owner: HandoffSwitchUi;
	replacement: HandoffSwitchUi;
}): Promise<string[]> {
	const traces = describeHandoffSwitchEffects(input.presentation);
	if (input.presentation.confirm) {
		throw new Error("handoff switch must not open a confirm dialog");
	}
	if (input.presentation.owner.notify) {
		input.owner.notify?.(`Context switch — pushing prepared handoff`, "info");
	}
	if (input.presentation.owner.setEditorText) {
		input.owner.setEditorText?.(input.prompt);
	}
	if (input.presentation.replacement.notify) {
		input.replacement.notify?.(`Handoff switch. Snapshot: ${input.snapshotPath}`, "info");
	}
	if (input.presentation.replacement.setEditorText) {
		input.replacement.setEditorText?.(input.prompt);
	}
	if (input.presentation.sendUserMessage) {
		await input.replacement.sendUserMessage?.(input.prompt, {
			deliverAs: input.presentation.sendDeliverAs,
		});
	}
	return traces;
}

export function afterCompactTriage(_input?: {
	preferHandoff?: boolean;
	prepared?: boolean;
}): "handoff-candidate" {
	return "handoff-candidate";
}

export function planHandoffLane(input: {
	percent: number;
	previousPercent?: number | null;
	prepared?: boolean;
	aligned?: boolean;
	switched?: boolean;
	compactedInsteadOfHandoff?: boolean;
	preparePercent?: number;
	alignPercent?: number;
	switchPercent?: number;
	overflowPercent?: number;
	hasUI?: boolean;
	mode?: string;
	env?: NodeJS.ProcessEnv | Record<string, string | undefined>;
}): {
	phase: HandoffLanePhase;
	actions: HandoffLaneAction[];
	steerMode: SessionSteerMode;
	switchKind: HandoffSwitchKind;
} {
	const preparePercent = clampLanePercent(input.preparePercent ?? 60, 60);
	const alignPercent = clampLanePercent(input.alignPercent ?? 70, 70);
	const switchPercent = clampLanePercent(input.switchPercent ?? 75, 75);
	const overflowPercent = clampLanePercent(input.overflowPercent ?? 80, 80);
	const steerMode = sessionSteerMode(input);
	const prepared = input.prepared === true;
	const aligned = input.aligned === true;
	const switched = input.switched === true;
	const actions: HandoffLaneAction[] = [];

	if (switched) {
		return {
			phase: "idle",
			actions,
			steerMode,
			switchKind: handoffSwitchAction({ mode: steerMode, prepared }),
		};
	}

	if (input.compactedInsteadOfHandoff && !prepared) actions.push("prepare");

	if (!prepared && input.percent >= preparePercent) {
		if (!actions.includes("prepare")) actions.push("prepare");
	}
	if (
		(prepared || actions.includes("prepare")) &&
		!aligned &&
		input.percent >= alignPercent &&
		input.percent < switchPercent
	) {
		actions.push("align");
	}
	if (input.percent >= switchPercent) {
		if (!prepared && !actions.includes("prepare")) actions.push("prepare");
		actions.push("switch");
	} else if (input.percent >= overflowPercent) {
		if (!prepared && !actions.includes("prepare")) actions.push("prepare");
		actions.push("switch");
	} else if (input.compactedInsteadOfHandoff && prepared) {
		actions.push("switch");
	}

	let phase: HandoffLanePhase = "idle";
	if (actions.includes("switch")) {
		phase = input.percent >= overflowPercent ? "overflow" : "switch";
	} else if (actions.includes("align")) {
		phase = "align";
	} else if (actions.includes("prepare")) {
		phase = "prepare";
	}

	return {
		phase,
		actions,
		steerMode,
		switchKind: handoffSwitchAction({
			mode: steerMode,
			prepared: prepared || actions.includes("prepare"),
		}),
	};
}

export type CompactInterceptAction = "handoff-cancel" | "pointer-compact";

/** preferHandoff means never write an in-place compact dump. */
export function shouldCancelInPlaceCompact(input: {
	preferHandoff?: boolean;
}): boolean {
	return input.preferHandoff !== false;
}

/**
 * Native /compact dumps the pointer into chat. When preferHandoff, cancel
 * that compact so the dump never lands. Queue success is not required.
 */
export function compactInterceptAction(input: {
	preferHandoff?: boolean;
	handoffReady?: boolean;
}): CompactInterceptAction {
	if (shouldCancelInPlaceCompact(input)) return "handoff-cancel";
	return "pointer-compact";
}

/** preferHandoff still wins during overflow willRetry; steer is fallback-only. */
export function preferHandoffAfterCompact(input: {
	preferHandoff?: boolean;
	willRetry?: boolean;
	aborted?: boolean;
}): boolean {
	return input.preferHandoff !== false;
}

export function inCompactCooldown(lastAt: number, cooldownMs: number, now = Date.now()): boolean {
	if (!lastAt || cooldownMs <= 0) return false;
	return now - lastAt < cooldownMs;
}
