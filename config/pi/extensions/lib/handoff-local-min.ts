/**
 * Compact-descent planner: draft on first dump, switch at harness-graph local min.
 * First preCompact never switches. successor_at ≠ switch.
 */
export type DescentPhase = "idle" | "prepare" | "align" | "switch" | "overflow";
export type DescentAction = "prepare" | "design" | "align" | "switch";

export type DescentInput = {
	percent: number;
	compactGeneration?: number;
	prepared?: boolean;
	aligned?: boolean;
	switched?: boolean;
	compactedInsteadOfHandoff?: boolean;
	preparePercent?: number;
	alignPercent?: number;
	switchPercent?: number;
	overflowPercent?: number;
	designerStarted?: boolean;
	successorMaySwitch?: boolean;
};

function clamp(n: number, fallback: number): number {
	if (!Number.isFinite(n)) return fallback;
	return Math.min(95, Math.max(1, n));
}

/** First dump is never a floor. 2nd dump still ≥ align, or 3rd+ dump, is. */
export function atHarnessLocalMin(input: {
	compactGeneration?: number;
	percent: number;
	alignPercent?: number;
	switchPercent?: number;
}): boolean {
	const generation = input.compactGeneration ?? 0;
	const alignPercent = clamp(input.alignPercent ?? 60, 60);
	const switchPercent = clamp(input.switchPercent ?? 90, 90);
	if (generation <= 1) return false;
	if (input.percent >= switchPercent) return true;
	if (generation >= 2 && input.percent >= alignPercent) return true;
	if (generation >= 3) return true;
	return false;
}

export function planCompactDescent(input: DescentInput): {
	phase: DescentPhase;
	actions: DescentAction[];
	localMin: boolean;
} {
	const preparePercent = clamp(input.preparePercent ?? 30, 30);
	const alignPercent = clamp(input.alignPercent ?? 60, 60);
	const switchPercent = clamp(input.switchPercent ?? 90, 90);
	const overflowPercent = clamp(input.overflowPercent ?? 90, 90);
	const generation = input.compactGeneration ?? (input.compactedInsteadOfHandoff ? 1 : 0);
	const prepared = input.prepared === true;
	const aligned = input.aligned === true;
	const switched = input.switched === true;
	const localMin = atHarnessLocalMin({
		compactGeneration: generation,
		percent: input.percent,
		alignPercent,
		switchPercent,
	});
	const actions: DescentAction[] = [];

	if (switched) {
		return { phase: "idle", actions, localMin: false };
	}

	const dump = input.compactedInsteadOfHandoff === true;
	if (dump && !prepared) {
		actions.push("prepare");
		if (!input.designerStarted) actions.push("design");
	} else if (!prepared && input.percent >= preparePercent) {
		actions.push("prepare");
		if (!input.designerStarted) actions.push("design");
	}

	const canAlign = prepared || actions.includes("prepare");
	if (canAlign && !aligned && !localMin && input.percent >= alignPercent && input.percent < switchPercent) {
		actions.push("align");
	} else if (dump && prepared && !localMin && input.percent < switchPercent) {
		if (!aligned) actions.push("align");
	}

	const percentSwitch = !dump && (input.percent >= switchPercent || input.percent >= overflowPercent);
	if (percentSwitch || localMin) {
		if (!prepared && !actions.includes("prepare")) actions.push("prepare");
		if (input.successorMaySwitch === false) {
			if (!input.designerStarted && !actions.includes("design")) actions.push("design");
		} else {
			actions.push("switch");
		}
	}

	let phase: DescentPhase = "idle";
	if (actions.includes("switch")) {
		phase = input.percent >= overflowPercent ? "overflow" : "switch";
	} else if (actions.includes("align")) {
		phase = "align";
	} else if (actions.includes("prepare") || actions.includes("design")) {
		phase = "prepare";
	}

	return { phase, actions, localMin };
}

export function handoffDesignerBrief(input: {
	snapshotPath: string;
	ownerId: string;
	percent: number;
	generation: number;
}): string {
	return [
		"Handoff designer. Read-only steer of this harness graph.",
		`owner: ${input.ownerId}`,
		`snapshot: ${input.snapshotPath}`,
		`percent: ${Math.round(input.percent)} generation: ${input.generation}`,
		"Patch only objective / next / blockers / keep-vs-drop graph nodes.",
		"Successor land ≤ 30%. Ceiling 60%. Force 90%. Packet 5%.",
		"Drop graph nodes until estimated land ≤ target. Do not switch a fat child.",
		"Do not switch. Do not relaunch congress. Schema wins.",
	].join("\n");
}
