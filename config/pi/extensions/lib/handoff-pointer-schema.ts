/**
 * Shared pointer-handoff wire. Snake_case on disk; TS maps camel at the edge only.
 * Switch requires successor_id + switched_at. successor_at ≠ switch.
 */
export const POINTER_SCHEMA = "pi.pointer-handoff.v1" as const;
export const TUNE_SCHEMA = "pi.handoff-tune.v1" as const;

export const POINTER_PHASES = ["idle", "prepare", "align", "switch"] as const;
export const POINTER_KINDS = ["implementation", "monitoring", "planning"] as const;
export const POINTER_LANES = ["pointer", "compact-fallback"] as const;

export type PointerPhase = (typeof POINTER_PHASES)[number];
export type PointerKind = (typeof POINTER_KINDS)[number];
export type PointerLane = (typeof POINTER_LANES)[number];

export type PointerHandoffRecord = {
	schema: typeof POINTER_SCHEMA;
	session_id: string;
	successor_id: string | null;
	phase: PointerPhase;
	kind: PointerKind;
	lane: PointerLane;
	context_percent: number;
	prepare_percent: number;
	align_percent: number;
	switch_percent: number;
	successor_target_percent: number;
	successor_ceiling_percent: number;
	successor_force_percent: number;
	moa: boolean;
	successor_model: string;
	snapshot_path: string;
	objective: string;
	next: string[];
	blockers: string[];
	switched_at?: string;
};

export const DEFAULT_POINTER: Omit<PointerHandoffRecord, "session_id"> = {
	schema: POINTER_SCHEMA,
	successor_id: null,
	phase: "idle",
	kind: "implementation",
	lane: "pointer",
	context_percent: 0,
	prepare_percent: 30,
	align_percent: 60,
	switch_percent: 90,
	successor_target_percent: 30,
	successor_ceiling_percent: 60,
	successor_force_percent: 90,
	moa: false,
	successor_model: "",
	snapshot_path: "",
	objective: "",
	next: [],
	blockers: [],
};

export function parseKind(value: unknown, fallback: PointerKind = "implementation"): PointerKind {
	return POINTER_KINDS.includes(value as PointerKind) ? (value as PointerKind) : fallback;
}

export function parseLane(value: unknown, fallback: PointerLane = "pointer"): PointerLane {
	return POINTER_LANES.includes(value as PointerLane) ? (value as PointerLane) : fallback;
}

export function parsePhase(value: unknown, fallback: PointerPhase = "idle"): PointerPhase {
	return POINTER_PHASES.includes(value as PointerPhase) ? (value as PointerPhase) : fallback;
}

export function switchComplete(rec: Pick<PointerHandoffRecord, "phase" | "successor_id" | "switched_at">): boolean {
	return rec.phase === "switch" && Boolean(rec.successor_id) && Boolean(rec.switched_at);
}
