/**
 * Project-scoped job-bus paths and subscription tokens.
 *
 * Named lanes are per-project: ~/.pi/agent/jobs/projects/<slug>/streams/<lane>
 * Session inboxes stay per-session. Host-global ~/.pi/agent/jobs/streams/<lane>
 * is opt-in only (global:LANE or legacy).
 */
import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, join } from "node:path";

export const UNSCOPED_PROJECT = "unscoped";

export type WatchToken =
	| { kind: "legacy" }
	| { kind: "unscoped" }
	| { kind: "session"; sid: string }
	| { kind: "lane"; lane: string; project: string; global: boolean };

export function safeProjectSlug(raw: string): string {
	return raw.replace(/[^A-Za-z0-9._:-]/g, "_").slice(0, 128);
}

export function slugFromCwd(
	cwd = "",
	opts: { gitExists?: (dir: string) => boolean } = {},
): string {
	const abs = String(cwd || "").trim();
	if (!abs) return UNSCOPED_PROJECT;
	const parts = abs.split(/[/\\]/).filter(Boolean);
	const srcIdx = parts.indexOf("src");
	if (srcIdx >= 0 && parts[srcIdx + 1]) {
		return repoSlug(parts[srcIdx + 1]);
	}
	const gitExists = opts.gitExists || ((dir: string) => existsSync(join(dir, ".git")));
	let dir = abs;
	for (let i = 0; i < 16; i++) {
		if (gitExists(dir)) {
			if (dir === homedir()) return UNSCOPED_PROJECT;
			const parent = basename(dirname(dir));
			if (parent.endsWith("-worktrees")) return repoSlug(parent);
			const base = basename(dir);
			if (!base || base === "." || base === "home") return UNSCOPED_PROJECT;
			return safeProjectSlug(base) || UNSCOPED_PROJECT;
		}
		const parent = dirname(dir);
		if (parent === dir) break;
		dir = parent;
	}
	return UNSCOPED_PROJECT;
}

function repoSlug(segment: string): string {
	const name = segment.endsWith("-worktrees") ? segment.slice(0, -"-worktrees".length) : segment;
	return safeProjectSlug(name) || UNSCOPED_PROJECT;
}

/** Session bind: PI_JOB_PROJECT overrides cwd. */
export function projectSlug(
	cwd = "",
	env: NodeJS.ProcessEnv = process.env,
	opts?: { gitExists?: (dir: string) => boolean },
): string {
	const explicit = String(env.PI_JOB_PROJECT || "").trim();
	if (explicit) return safeProjectSlug(explicit);
	return slugFromCwd(cwd, opts);
}

/**
 * Job write: record.project, then job cwd, then env, then unscoped.
 * Job cwd wins over a parent session's PI_JOB_PROJECT so a home
 * orchestrator writing a child project's job lands on that project's bus.
 */
export function resolveJobProject(
	record: { project?: string; cwd?: string } = {},
	env: NodeJS.ProcessEnv = process.env,
	opts?: { gitExists?: (dir: string) => boolean },
): string {
	const stamped = String(record.project || "").trim();
	if (stamped) return safeProjectSlug(stamped);
	const fromCwd = slugFromCwd(record.cwd || "", opts);
	if (fromCwd && fromCwd !== UNSCOPED_PROJECT) return fromCwd;
	const explicit = String(env.PI_JOB_PROJECT || "").trim();
	if (explicit) return safeProjectSlug(explicit);
	return fromCwd || UNSCOPED_PROJECT;
}

export function jobsHostRoot(home: string): string {
	return join(home, ".pi", "agent", "jobs");
}

export function projectStreamsRoot(project: string, jobsRoot: string): string {
	return join(jobsRoot, "projects", safeProjectSlug(project || UNSCOPED_PROJECT), "streams");
}

export function projectLaneDir(project: string, lane: string, jobsRoot: string): string {
	return join(projectStreamsRoot(project, jobsRoot), safeProjectSlug(lane));
}

export function legacyLaneDir(lane: string, jobsRoot: string): string {
	return join(jobsRoot, "streams", safeProjectSlug(lane));
}

export function parseWatchToken(token: string, boundProject: string): WatchToken | undefined {
	const raw = token.trim();
	if (!raw) return undefined;
	if (raw === "legacy" || raw === "global") return { kind: "legacy" };
	if (raw === "unscoped") return { kind: "unscoped" };
	if (raw.startsWith("session:")) {
		const sid = safeProjectSlug(raw.slice("session:".length));
		return sid ? { kind: "session", sid } : undefined;
	}
	if (raw.startsWith("global:")) {
		const lane = raw.slice("global:".length).replace(/^stream:/, "");
		return lane ? { kind: "lane", lane, project: "", global: true } : undefined;
	}
	if (raw.startsWith("project:")) {
		const rest = raw.slice("project:".length);
		const parts = rest.includes("/") ? rest.split("/") : rest.split(":");
		const project = safeProjectSlug(parts[0] || "");
		if (!project) return undefined;
		const lane = parts.slice(1).join("/") || "*";
		return { kind: "lane", lane, project, global: false };
	}
	const lane = raw.startsWith("stream:") ? raw.slice("stream:".length) : raw;
	if (!lane) return undefined;
	return {
		kind: "lane",
		lane,
		project: boundProject || UNSCOPED_PROJECT,
		global: false,
	};
}

function globMatch(name: string, pattern: string): boolean {
	const re = new RegExp(
		`^${pattern.replace(/[.+^${}()|\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".")}$`,
	);
	return re.test(name);
}

function listLaneDirs(
	root: string,
	pattern: string,
	listChildren: (dir: string) => string[],
): string[] {
	if (!/[*?\[]/.test(pattern)) return [join(root, safeProjectSlug(pattern))];
	try {
		return listChildren(root)
			.filter((name) => globMatch(name, pattern))
			.map((name) => join(root, name));
	} catch {
		return [];
	}
}

export function watchDirsForSubscriptions(opts: {
	inboxDir: string;
	jobsRoot: string;
	boundProject: string;
	subscriptions: string[];
	listChildren?: (dir: string) => string[];
}): string[] {
	const list = opts.listChildren || defaultListChildren;
	const dirs: string[] = [opts.inboxDir || join(opts.jobsRoot, UNSCOPED_PROJECT)];
	for (const spec of opts.subscriptions) {
		const token = parseWatchToken(spec, opts.boundProject);
		if (!token) continue;
		if (token.kind === "legacy") {
			dirs.push(opts.jobsRoot);
			continue;
		}
		if (token.kind === "unscoped") {
			dirs.push(join(opts.jobsRoot, UNSCOPED_PROJECT));
			continue;
		}
		if (token.kind === "session") {
			dirs.push(join(opts.jobsRoot, "sessions", token.sid));
			continue;
		}
		if (token.global) {
			dirs.push(...listLaneDirs(join(opts.jobsRoot, "streams"), token.lane, list));
			continue;
		}
		dirs.push(...listLaneDirs(projectStreamsRoot(token.project, opts.jobsRoot), token.lane, list));
	}
	return [...new Set(dirs)];
}

function defaultListChildren(dir: string): string[] {
	try {
		return readdirSync(dir, { withFileTypes: true })
			.filter((child) => child.isDirectory())
			.map((child) => child.name);
	} catch {
		return [];
	}
}

export function recordProject(record?: { project?: string; extra?: { project?: unknown } }): string {
	const extra = record?.extra && typeof record.extra === "object" ? record.extra : {};
	for (const value of [record?.project, extra.project]) {
		const text = String(value || "").trim();
		if (text) return safeProjectSlug(text);
	}
	return "";
}

export function isForeignProjectFile(opts: {
	filePath: string;
	inboxDir: string;
	boundProject: string;
	recordProject: string;
}): boolean {
	if (!opts.recordProject || !opts.boundProject) return false;
	if (opts.recordProject === opts.boundProject) return false;
	if (opts.inboxDir && (opts.filePath === opts.inboxDir || opts.filePath.startsWith(`${opts.inboxDir}/`))) {
		return false;
	}
	const needle = `/projects/${opts.recordProject}/`;
	return !opts.filePath.includes(needle);
}
