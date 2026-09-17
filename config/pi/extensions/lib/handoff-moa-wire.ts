/**
 * Call site for compact-handoff persist. MoA off (default) is identity.
 * Import after `buildSnapshot` and before `persistSnapshot`.
 *
 *   const ready = await persistReadySnapshot({ sessionId, snapshot, flag });
 *   return persistSnapshot(ready);
 */
import { maybeMoaPatch, type HandoffPacket } from "./handoff-moa.ts";
import { sessionMoaEnabled } from "./handoff-session-tune.ts";

export async function persistReadySnapshot<T extends HandoffPacket>(opts: {
	sessionId: string;
	snapshot: T;
	flag?: unknown;
	call?: () => Promise<unknown>;
}): Promise<T> {
	const moa = sessionMoaEnabled({ sessionId: opts.sessionId, flag: opts.flag });
	const result = await maybeMoaPatch({
		moa,
		snapshot: opts.snapshot,
		call: opts.call,
	});
	return result.snapshot;
}

/** Sync wrapper for persistFromContext — MoA call is optional/async. */
export function persistReadySnapshotSync<T extends HandoffPacket>(opts: {
	sessionId: string;
	snapshot: T;
	flag?: unknown;
}): T {
	if (sessionMoaEnabled({ sessionId: opts.sessionId, flag: opts.flag })) {
		return opts.snapshot;
	}
	return opts.snapshot;
}
