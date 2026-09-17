/**
 * persistFromContext hook: buildSnapshot → persistReadySnapshot → persistSnapshot.
 * Compact-handoff imports this; do not call models here.
 */
import { persistReadySnapshot, persistReadySnapshotSync } from "./handoff-moa-wire.ts";
import type { HandoffPacket } from "./handoff-moa.ts";

export type PersistFn<T> = (snapshot: T) => { path?: string } & Record<string, unknown>;

export async function persistFromContextReady<T extends HandoffPacket>(opts: {
	sessionId: string;
	snapshot: T;
	persist: PersistFn<T>;
	flag?: unknown;
	call?: () => Promise<unknown>;
}): Promise<{ snapshot: T } & Record<string, unknown>> {
	const snapshot = await persistReadySnapshot({
		sessionId: opts.sessionId,
		snapshot: opts.snapshot,
		flag: opts.flag,
		call: opts.call,
	});
	return { snapshot, ...opts.persist(snapshot) };
}

/** Sync path when MoA is off (default). MoA-on still identity without `call`. */
export function persistFromContextReadySync<T extends HandoffPacket>(opts: {
	sessionId: string;
	snapshot: T;
	persist: PersistFn<T>;
	flag?: unknown;
}): { snapshot: T } & Record<string, unknown> {
	const snapshot = persistReadySnapshotSync({
		sessionId: opts.sessionId,
		snapshot: opts.snapshot,
		flag: opts.flag,
	});
	return { snapshot, ...opts.persist(snapshot) };
}
