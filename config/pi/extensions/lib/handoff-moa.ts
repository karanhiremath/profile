/**
 * Capped handoff-packet field patch. Schema wins; LLM prose is discarded.
 * Wire after `buildSnapshot`, before `persistSnapshot`. MoA off → identity.
 *
 * Live compact-handoff.ts is still uncommitted on profile HEAD; this lib
 * is the call site. Do not invoke models from this file.
 */
export const HANDOFF_PACKET_FIELDS = ["objective", "next", "blockers"] as const;
export const NEXT_MAX = 6;
export const BLOCKERS_MAX = 6;
export const OBJECTIVE_MAX_CHARS = 400;

export type HandoffPacketField = (typeof HANDOFF_PACKET_FIELDS)[number];

export type HandoffPacketPatch = {
	objective?: string;
	next?: string[];
	blockers?: string[];
};

export type HandoffPacket = {
	objective: string;
	next: string[];
	blockers: string[];
};

export type MoaPatchResult<T extends HandoffPacket> = {
	snapshot: T;
	moa: "off" | "patched" | "stopped-429" | "discarded";
};

function capLine(value: string, max: number): string {
	const trimmed = value.trim();
	if (trimmed.length <= max) return trimmed;
	return trimmed.slice(0, max);
}

function capLines(values: unknown, maxItems: number, maxChars: number): string[] {
	if (!Array.isArray(values)) return [];
	const out: string[] = [];
	for (const item of values) {
		if (typeof item !== "string") continue;
		const line = capLine(item, maxChars);
		if (!line) continue;
		out.push(line);
		if (out.length >= maxItems) break;
	}
	return out;
}

export function isRateLimited(err: unknown): boolean {
	if (err && typeof err === "object") {
		const rec = err as { status?: unknown; statusCode?: unknown; code?: unknown; message?: unknown };
		if (rec.status === 429 || rec.statusCode === 429 || rec.code === 429) return true;
		if (typeof rec.message === "string" && /\b429\b|rate[_ ]?limit/i.test(rec.message)) return true;
	}
	if (typeof err === "string" && /\b429\b|rate[_ ]?limit/i.test(err)) return true;
	return false;
}

/** Drop novels. Only objective / next / blockers survive. */
export function sanitizeHandoffPacketPatch(raw: unknown): HandoffPacketPatch | null {
	if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
	const rec = raw as Record<string, unknown>;
	const patch: HandoffPacketPatch = {};
	if (typeof rec.objective === "string") {
		const objective = capLine(rec.objective, OBJECTIVE_MAX_CHARS);
		if (objective) patch.objective = objective;
	}
	if ("next" in rec) patch.next = capLines(rec.next, NEXT_MAX, OBJECTIVE_MAX_CHARS);
	if ("blockers" in rec) patch.blockers = capLines(rec.blockers, BLOCKERS_MAX, OBJECTIVE_MAX_CHARS);
	if (patch.objective === undefined && patch.next === undefined && patch.blockers === undefined) {
		return null;
	}
	return patch;
}

export function applyHandoffPacketPatch<T extends HandoffPacket>(
	base: T,
	patch: HandoffPacketPatch | null,
): T {
	if (!patch) return base;
	return {
		...base,
		objective: patch.objective ?? base.objective,
		next: patch.next ?? base.next,
		blockers: patch.blockers ?? base.blockers,
	};
}

export async function maybeMoaPatch<T extends HandoffPacket>(opts: {
	moa: boolean;
	snapshot: T;
	call?: () => Promise<unknown>;
}): Promise<MoaPatchResult<T>> {
	if (!opts.moa || !opts.call) return { snapshot: opts.snapshot, moa: "off" };
	try {
		const raw = await opts.call();
		const patch = sanitizeHandoffPacketPatch(raw);
		if (!patch) return { snapshot: opts.snapshot, moa: "discarded" };
		return { snapshot: applyHandoffPacketPatch(opts.snapshot, patch), moa: "patched" };
	} catch (err) {
		if (isRateLimited(err)) return { snapshot: opts.snapshot, moa: "stopped-429" };
		return { snapshot: opts.snapshot, moa: "discarded" };
	}
}
