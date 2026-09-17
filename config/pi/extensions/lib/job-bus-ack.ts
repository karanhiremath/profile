/**
 * Per-consumer job-bus ACK / cursor. Default poll is new messages only.
 * Each session inbox has its own .ack.json so consumers ACK independently.
 */
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

export const ACK_SCHEMA = "pi.job-bus-ack.v1";
export const ACK_FILENAME = ".ack.json";

export type AckCursor = {
	fp: string;
	jobId?: string;
	status?: string;
	type?: string;
	ts?: string;
	ackedAt?: string;
};

export type AckState = {
	schema: typeof ACK_SCHEMA;
	consumerId: string;
	ids: string[];
	cursors: Record<string, AckCursor>;
};

export function ackPath(inboxDir: string): string {
	return join(inboxDir, ACK_FILENAME);
}

export function emptyAck(consumerId: string): AckState {
	return { schema: ACK_SCHEMA, consumerId, ids: [], cursors: {} };
}

export function fingerprint(path: string): string {
	try {
		const st = statSync(path);
		return `${st.mtimeMs}:${st.size}`;
	} catch {
		return "";
	}
}

export function messageId(record: { jobId?: string; type?: string; status?: string; ts?: string }, path: string, fp = ""): string {
	const stamp = fp || fingerprint(path);
	return [record.jobId || path, record.type || "", record.status || "", record.ts || "", stamp].join("|");
}

/** Stable poll identity. Same job+type+status is one message even if the file is rewritten. */
export function logicalMessageId(
	record: { jobId?: string; type?: string; status?: string },
	path = "",
): string {
	return [record.jobId || path, record.type || "", record.status || ""].join("|");
}

/** Path-independent event identity. Status transitions change this; mtime/ts rewrites do not. */
export function eventKey(record?: { jobId?: string; type?: string; status?: string }): string {
	const job = String(record?.jobId || "").trim();
	if (!job) return "";
	return [job, record?.type || "", record?.status || ""].join("|");
}

export function loadAck(inboxDir: string, consumerId: string): AckState {
	try {
		const data = JSON.parse(readFileSync(ackPath(inboxDir), "utf8")) as Partial<AckState>;
		const ids = Array.isArray(data.ids) ? data.ids.map(String) : [];
		const cursors = data.cursors && typeof data.cursors === "object" ? data.cursors : {};
		return {
			schema: ACK_SCHEMA,
			consumerId: String(data.consumerId || consumerId),
			ids,
			cursors,
		};
	} catch {
		return emptyAck(consumerId);
	}
}

export function saveAck(inboxDir: string, state: AckState): string {
	const path = ackPath(inboxDir);
	mkdirSync(dirname(path), { recursive: true });
	const filled: AckState = {
		schema: ACK_SCHEMA,
		consumerId: state.consumerId,
		ids: [...new Set(state.ids.map(String))],
		cursors: state.cursors || {},
	};
	writeFileSync(path, `${JSON.stringify(filled, null, 2)}\n`);
	return path;
}

export function isAcked(state: AckState, path: string, record?: { jobId?: string; type?: string; status?: string; ts?: string }): boolean {
	const fp = fingerprint(path);
	if (!fp) return false;
	const entry = state.cursors[path];
	if (entry && entry.fp === fp) return true;
	if (!record) return false;
	const key = eventKey(record) || logicalMessageId(record, path);
	if (key && state.ids.includes(key)) return true;
	if (
		entry &&
		(entry.jobId || "") === (record.jobId || "") &&
		(entry.type || "") === (record.type || "") &&
		(entry.status || "") === (record.status || "")
	) {
		return true;
	}
	return state.ids.includes(messageId(record, path, fp));
}

export function ackPaths(
	state: AckState,
	paths: string[],
	readRecord: (path: string) => { jobId?: string; type?: string; status?: string; ts?: string } | undefined,
	now = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
): AckState {
	const next: AckState = {
		schema: ACK_SCHEMA,
		consumerId: state.consumerId,
		ids: [...state.ids],
		cursors: { ...state.cursors },
	};
	const known = new Set(next.ids);
	const stamped = now();
	for (const path of paths) {
		if (!existsSync(path)) continue;
		const fp = fingerprint(path);
		if (!fp) continue;
		const record = readRecord(path) || {};
		const mid = messageId(record, path, fp);
		const logical = logicalMessageId(record, path);
		next.cursors[path] = {
			fp,
			jobId: record.jobId,
			status: record.status,
			type: record.type,
			ts: record.ts,
			ackedAt: stamped,
		};
		if (!known.has(logical)) {
			next.ids.push(logical);
			known.add(logical);
		}
		if (!known.has(mid)) {
			next.ids.push(mid);
			known.add(mid);
		}
		if (record.jobId && !known.has(record.jobId)) {
			next.ids.push(record.jobId);
			known.add(record.jobId);
		}
		const key = eventKey(record);
		if (key && !known.has(key)) {
			next.ids.push(key);
			known.add(key);
		}
	}
	return next;
}

export function pendingPaths(
	state: AckState,
	paths: string[],
	readRecord: (path: string) => { jobId?: string; type?: string; status?: string; ts?: string } | undefined,
): string[] {
	return paths.filter((path) => !isAcked(state, path, readRecord(path)));
}

export function seenMapFromAck(state: AckState): Map<string, string> {
	const seen = new Map<string, string>();
	for (const [path, cursor] of Object.entries(state.cursors)) {
		if (cursor?.fp) seen.set(path, cursor.fp);
	}
	return seen;
}
