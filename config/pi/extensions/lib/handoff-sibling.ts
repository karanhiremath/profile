/**
 * Sibling handoff session: create a child session file and warm it in the
 * background without replacing the owner TUI/RPC session.
 */
import { existsSync } from "node:fs";
import { SessionManager } from "@earendil-works/pi-coding-agent";
import { persistSiblingSessionFile } from "./handoff-sibling-persist.ts";

export { persistSiblingSessionFile, sessionFileHasAssistant } from "./handoff-sibling-persist.ts";
export type { SiblingSessionWriter } from "./handoff-sibling-persist.ts";
export { spawnHandoffPrintTurn } from "./handoff-spawn.ts";

export function createSiblingHandoffSession(input: {
	cwd: string;
	sessionDir?: string;
	parentSessionFile?: string;
	sourceSessionId?: string;
	snapshotPath?: string;
}): { sessionId: string; sessionFile: string } {
	const sm = SessionManager.create(input.cwd, input.sessionDir, {
		parentSession: input.parentSessionFile,
	});
	sm.appendCustomEntry("pi.handoff-prep", {
		source_session_id: input.sourceSessionId,
		snapshot_path: input.snapshotPath,
		phase: "prepared",
	});
	const sessionFile = persistSiblingSessionFile(sm);
	const sessionId = sm.getSessionId();
	if (!sessionId || !existsSync(sessionFile)) {
		throw new Error("sibling handoff session did not persist a file");
	}
	return { sessionId, sessionFile };
}
