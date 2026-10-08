/**
 * Force-write a sibling session JSONL. SessionManager defers persist until
 * an assistant message exists; handoff switch needs the file immediately.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

export function sessionFileHasAssistant(sessionFile?: string): boolean {
	if (!sessionFile || !existsSync(sessionFile)) return false;
	try {
		const body = readFileSync(sessionFile, "utf8");
		return /"role"\s*:\s*"assistant"/.test(body);
	} catch {
		return false;
	}
}

export type SiblingSessionWriter = {
	getSessionFile: () => string | undefined;
	getSessionId: () => string;
	getHeader: () => unknown;
	getEntries: () => unknown[];
};

export function writeMinimalSiblingSession(input: {
	sessionFile: string;
	sessionId: string;
	cwd: string;
	sourceSessionId?: string;
	snapshotPath?: string;
	phase?: string;
}): string {
	mkdirSync(dirname(input.sessionFile), { recursive: true });
	const header = {
		type: "session",
		version: 3,
		id: input.sessionId,
		cwd: input.cwd,
		timestamp: new Date().toISOString(),
	};
	const prep = {
		type: "custom",
		customType: "pi.handoff-prep",
		data: {
			source_session_id: input.sourceSessionId,
			snapshot_path: input.snapshotPath,
			phase: input.phase || "prepared",
		},
	};
	const lineage = {
		type: "custom",
		customType: "pi.handoff-lineage",
		data: {
			schema: "pi.handoff-lineage.v1",
			source_session_id: input.sourceSessionId,
			snapshot_path: input.snapshotPath,
			child_session_id: input.sessionId,
		},
	};
	writeFileSync(input.sessionFile, `${[header, prep, lineage].map((row) => JSON.stringify(row)).join("\n")}\n`);
	if (!existsSync(input.sessionFile)) {
		throw new Error("sibling handoff session did not persist a file");
	}
	return input.sessionFile;
}

export function persistSiblingSessionFile(sm: SiblingSessionWriter): string {
	const sessionFile = sm.getSessionFile();
	const sessionId = sm.getSessionId();
	const header = sm.getHeader();
	if (!sessionFile || !sessionId || !header) {
		throw new Error("sibling handoff session did not persist a file");
	}
	mkdirSync(dirname(sessionFile), { recursive: true });
	const lines = [header, ...sm.getEntries()].map((entry) => JSON.stringify(entry));
	writeFileSync(sessionFile, `${lines.join("\n")}\n`);
	if (!existsSync(sessionFile)) {
		throw new Error("sibling handoff session did not persist a file");
	}
	return sessionFile;
}
