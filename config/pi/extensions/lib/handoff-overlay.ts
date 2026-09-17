/**
 * Board-wide handoff budget overlays. herm-tui is a host, not a second schema.
 * Unmeasured family/profile/launcher inherit 30/60/90. Do not invent percents.
 */
import {
	SUCCESSOR_CEILING_PERCENT,
	SUCCESSOR_FORCE_PERCENT,
	SUCCESSOR_TARGET_PERCENT,
	PACKET_BUDGET_PERCENT,
	resolveSuccessorBudget,
	type SuccessorBudget,
} from "./handoff-successor-budget.ts";

export type OverlayHost = "pi" | "hermes" | "herm-tui" | "cursor";
export type ModelFamily = "grok" | "gpt-6" | "codex" | "other";
export type OverlayLayer = "board" | "family" | "profile" | "launcher" | "session" | "explicit";

export type OverlayPatch = Partial<
	Pick<
		SuccessorBudget,
		| "packet_budget_percent"
		| "successor_target_percent"
		| "successor_ceiling_percent"
		| "successor_force_percent"
	>
> & { measured?: boolean };

export type OverlayInput = {
	host?: OverlayHost;
	profile?: string;
	launcher?: string;
	model?: string;
	session?: OverlayPatch;
	explicit?: OverlayPatch;
};

export type OverlayResult = {
	budget: SuccessorBudget;
	family: ModelFamily;
	profile: string;
	launcher: string;
	host: OverlayHost;
	source: OverlayLayer;
	measured: boolean;
};

const BOARD: OverlayPatch = {
	packet_budget_percent: PACKET_BUDGET_PERCENT,
	successor_target_percent: SUCCESSOR_TARGET_PERCENT,
	successor_ceiling_percent: SUCCESSOR_CEILING_PERCENT,
	successor_force_percent: SUCCESSOR_FORCE_PERCENT,
	measured: true,
};

/** Slots only. Fill percents after measurement. */
export const OVERLAY_TABLE: Record<string, OverlayPatch> = {
	"family:grok": { measured: false },
	"family:gpt-6": { measured: false },
	"family:codex": { measured: false },
	"profile:cos": { measured: false },
	"profile:cosw": { measured: false },
	"profile:dreamw": { measured: false },
	"launcher:cos-gpt6": { measured: false },
	"launcher:cosw-gpt6": { measured: false },
};

export function modelFamily(model = ""): ModelFamily {
	const raw = model.toLowerCase();
	if (/\bgpt-?6\b/.test(raw)) return "gpt-6";
	if (/\bgrok\b/.test(raw)) return "grok";
	if (/\bcodex\b/.test(raw) || /gpt-5/.test(raw)) return "codex";
	return "other";
}

export function parseLauncher(launcher = ""): { launcher: string; profile: string; family: ModelFamily } {
	const key = launcher.trim().toLowerCase().replace(/_/g, "-");
	if (!key) return { launcher: "", profile: "", family: "other" };
	const gpt6 = key.endsWith("-gpt6") || key.endsWith("-gpt-6");
	const profile = gpt6 ? key.replace(/-gpt-?6$/, "") : key;
	return {
		launcher: key,
		profile,
		family: gpt6 ? "gpt-6" : modelFamily(key),
	};
}

function hasPercents(patch?: OverlayPatch): boolean {
	if (!patch) return false;
	return (
		patch.packet_budget_percent != null ||
		patch.successor_target_percent != null ||
		patch.successor_ceiling_percent != null ||
		patch.successor_force_percent != null
	);
}

function merge(base: OverlayPatch, next?: OverlayPatch): OverlayPatch {
	if (!next) return base;
	return { ...base, ...next };
}

export function resolveHandoffOverlay(input: OverlayInput = {}): OverlayResult {
	const parsed = parseLauncher(input.launcher ?? "");
	const profile = (input.profile || parsed.profile || "").toLowerCase();
	const family = input.model ? modelFamily(input.model) : parsed.family;
	const launcher = parsed.launcher;
	const host = input.host ?? "pi";

	let patch = { ...BOARD };
	let source: OverlayLayer = "board";
	let measured = true;

	const layers: Array<[OverlayLayer, OverlayPatch | undefined]> = [
		["family", OVERLAY_TABLE[`family:${family}`]],
		["profile", profile ? OVERLAY_TABLE[`profile:${profile}`] : undefined],
		["launcher", launcher ? OVERLAY_TABLE[`launcher:${launcher}`] : undefined],
		["session", input.session],
		["explicit", input.explicit],
	];
	for (const [layer, next] of layers) {
		if (!next) continue;
		patch = merge(patch, next);
		if (hasPercents(next)) {
			source = layer;
			measured = next.measured !== false;
		}
	}

	return {
		budget: resolveSuccessorBudget({
			packet_budget_percent: patch.packet_budget_percent,
			successor_target_percent: patch.successor_target_percent,
			successor_ceiling_percent: patch.successor_ceiling_percent,
			successor_force_percent: patch.successor_force_percent,
		}),
		family,
		profile,
		launcher,
		host,
		source,
		measured,
	};
}
