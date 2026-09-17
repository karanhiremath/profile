/**
 * Per-session handoff knobs. Flag + sidecar; env is process default only.
 * Sidecar is snake_case (`pi.handoff-tune.v1`). TS maps camel at this edge only.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import {
	DEFAULT_POINTER,
	POINTER_KINDS,
	POINTER_LANES,
	TUNE_SCHEMA,
	parseKind,
	parseLane,
	type PointerKind,
	type PointerLane,
} from "./handoff-pointer-schema.ts";

export const HANDOFF_MOA_FLAG = "handoff-moa";
export { TUNE_SCHEMA, POINTER_KINDS as PI_HANDOFF_KINDS };
export type PiHandoffKind = PointerKind;
export type PiHandoffLane = PointerLane;

export type HandoffSessionTune = {
	schema: typeof TUNE_SCHEMA;
	session_id: string;
	prepare_percent: number;
	align_percent: number;
	switch_percent: number;
	successor_target_percent: number;
	successor_ceiling_percent: number;
	successor_force_percent: number;
	kind: PointerKind;
	lane: PointerLane;
	successor_model: string;
	moa: boolean;
};

/** @deprecated camel aliases — persist/load snake_case only */
export type HandoffSessionTuneCamel = {
	preparePercent: number;
	alignPercent: number;
	switchPercent: number;
	successorModel: string;
};

export const DEFAULT_TUNE = {
	prepare_percent: DEFAULT_POINTER.prepare_percent,
	align_percent: DEFAULT_POINTER.align_percent,
	switch_percent: DEFAULT_POINTER.switch_percent,
	successor_target_percent: DEFAULT_POINTER.successor_target_percent,
	successor_ceiling_percent: DEFAULT_POINTER.successor_ceiling_percent,
	successor_force_percent: DEFAULT_POINTER.successor_force_percent,
	kind: DEFAULT_POINTER.kind,
	lane: DEFAULT_POINTER.lane,
	successor_model: "",
	moa: false,
};

export type HandoffFlagApi = {
	registerFlag: (
		name: string,
		options: { description: string; type: "boolean"; default: boolean },
	) => void;
	getFlag?: (name: string) => unknown;
};

export function tuneSidecarPath(sessionId: string): string {
	const sid = sessionId.replace(/[^A-Za-z0-9._-]/g, "_");
	return join(homedir(), ".pi", "agent", "handoffs", `${sid}.tune.json`);
}

function clampPercent(value: unknown, fallback: number): number {
	const n = typeof value === "number" ? value : Number(value);
	if (!Number.isFinite(n)) return fallback;
	return Math.min(95, Math.max(1, Math.round(n)));
}

function envMoaDefault(env: NodeJS.ProcessEnv = process.env): boolean {
	const raw = env.PI_HANDOFF_MOA;
	if (raw === undefined) return false;
	return raw === "1" || raw.toLowerCase() === "true" || raw.toLowerCase() === "on";
}

export function defaultTune(sessionId: string, env: NodeJS.ProcessEnv = process.env): HandoffSessionTune {
	return {
		schema: TUNE_SCHEMA,
		session_id: sessionId,
		...DEFAULT_TUNE,
		moa: envMoaDefault(env),
	};
}

function fromRaw(sessionId: string, raw: Record<string, unknown>, fallback: HandoffSessionTune): HandoffSessionTune {
	return {
		schema: TUNE_SCHEMA,
		session_id: sessionId,
		prepare_percent: clampPercent(raw.prepare_percent ?? raw.preparePercent, fallback.prepare_percent),
		align_percent: clampPercent(raw.align_percent ?? raw.alignPercent, fallback.align_percent),
		switch_percent: clampPercent(raw.switch_percent ?? raw.switchPercent, fallback.switch_percent),
		successor_target_percent: clampPercent(
			raw.successor_target_percent ?? raw.successorTargetPercent,
			fallback.successor_target_percent,
		),
		successor_ceiling_percent: clampPercent(
			raw.successor_ceiling_percent ?? raw.successorCeilingPercent,
			fallback.successor_ceiling_percent,
		),
		successor_force_percent: clampPercent(
			raw.successor_force_percent ?? raw.successorForcePercent,
			fallback.successor_force_percent,
		),
		kind: parseKind(raw.kind, fallback.kind),
		lane: parseLane(raw.lane, fallback.lane),
		successor_model:
			typeof raw.successor_model === "string"
				? raw.successor_model
				: typeof raw.successorModel === "string"
					? raw.successorModel
					: "",
		moa: typeof raw.moa === "boolean" ? raw.moa : fallback.moa,
	};
}

export function loadSessionTune(sessionId: string, env: NodeJS.ProcessEnv = process.env): HandoffSessionTune {
	const fallback = defaultTune(sessionId, env);
	const path = tuneSidecarPath(sessionId);
	if (!existsSync(path)) return fallback;
	try {
		return fromRaw(sessionId, JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>, fallback);
	} catch {
		return fallback;
	}
}

export function persistSessionTune(
	sessionId: string,
	partial: Partial<Omit<HandoffSessionTune, "schema" | "session_id">>,
	env: NodeJS.ProcessEnv = process.env,
): HandoffSessionTune {
	const next = { ...loadSessionTune(sessionId, env), ...partial, schema: TUNE_SCHEMA, session_id: sessionId };
	const path = tuneSidecarPath(sessionId);
	mkdirSync(dirname(path), { recursive: true });
	writeFileSync(path, `${JSON.stringify(next, null, 2)}\n`);
	return next;
}

export function registerHandoffMoaFlag(pi: HandoffFlagApi): void {
	pi.registerFlag(HANDOFF_MOA_FLAG, {
		description: "Optional one-call handoff-packet field patch (default off)",
		type: "boolean",
		default: false,
	});
}

export function sessionMoaEnabled(opts: {
	sessionId: string;
	flag?: unknown;
	env?: NodeJS.ProcessEnv;
}): boolean {
	if (opts.flag === true) return true;
	if (opts.flag === false) return false;
	return loadSessionTune(opts.sessionId, opts.env).moa;
}

export function settingsItems(tune: HandoffSessionTune): Array<{
	id: string;
	label: string;
	value: string;
	options: string[];
}> {
	return [
		{ id: "prepare", label: "prepare %", value: String(tune.prepare_percent), options: ["30", "40", "50"] },
		{ id: "align", label: "align %", value: String(tune.align_percent), options: ["50", "60", "70"] },
		{ id: "switch", label: "switch %", value: String(tune.switch_percent), options: ["80", "90", "95"] },
		{ id: "successor_target", label: "successor land %", value: String(tune.successor_target_percent), options: ["20", "30", "40"] },
		{ id: "successor_ceiling", label: "successor ceiling %", value: String(tune.successor_ceiling_percent), options: ["50", "60", "70"] },
		{ id: "successor_force", label: "successor force %", value: String(tune.successor_force_percent), options: ["80", "90", "95"] },
		{ id: "kind", label: "kind", value: tune.kind, options: [...POINTER_KINDS] },
		{ id: "lane", label: "lane", value: tune.lane, options: [...POINTER_LANES] },
		{ id: "moa", label: "MoA packet", value: tune.moa ? "on" : "off", options: ["off", "on"] },
		{
			id: "successor",
			label: "successor model",
			value: tune.successor_model || "inherit",
			options: ["inherit"],
		},
	];
}
