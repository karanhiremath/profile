/**
 * Successor land/ceiling/force vs packet budget. Packet ≠ child fill.
 * Board ladder: 30 land / 60 ceiling / 90 force. Do not pad to hit target.
 */
export const PACKET_BUDGET_PERCENT = 5;
export const SUCCESSOR_TARGET_PERCENT = 30;
export const SUCCESSOR_CEILING_PERCENT = 60;
export const SUCCESSOR_FORCE_PERCENT = 90;
export const DEFAULT_CONTEXT_WINDOW = 256_000;
export const DEFAULT_CHARS_PER_TOKEN = 4;

export type SuccessorBudget = {
	packet_budget_percent: number;
	successor_target_percent: number;
	successor_ceiling_percent: number;
	successor_force_percent: number;
	context_window: number;
};

export type SuccessorFillInput = {
	contextWindow?: number;
	packetBytes?: number;
	promptChars?: number;
	baselineChars?: number;
	transcriptChars?: number;
	inlineSkillChars?: number;
	fileContentChars?: number;
	charsPerToken?: number;
	targetPercent?: number;
	ceilingPercent?: number;
	forcePercent?: number;
	packetBudgetPercent?: number;
};

export type PollutionKind =
	| "ok"
	| "over_packet"
	| "over_target"
	| "over_ceiling"
	| "over_force"
	| "transcript"
	| "inline_skill"
	| "file_contents";

export type SuccessorFill = {
	percent: number;
	tokens: number;
	packet_tokens: number;
	baseline_tokens: number;
	pollution: PollutionKind[];
	may_switch: boolean;
};

function clampPercent(n: number, fallback: number, min = 1, max = 95): number {
	if (!Number.isFinite(n)) return fallback;
	return Math.min(max, Math.max(min, n));
}

export function defaultSuccessorBudget(): SuccessorBudget {
	return {
		packet_budget_percent: PACKET_BUDGET_PERCENT,
		successor_target_percent: SUCCESSOR_TARGET_PERCENT,
		successor_ceiling_percent: SUCCESSOR_CEILING_PERCENT,
		successor_force_percent: SUCCESSOR_FORCE_PERCENT,
		context_window: DEFAULT_CONTEXT_WINDOW,
	};
}

export function resolveSuccessorBudget(input: Partial<SuccessorBudget> = {}): SuccessorBudget {
	const base = defaultSuccessorBudget();
	return {
		packet_budget_percent: clampPercent(
			input.packet_budget_percent ?? base.packet_budget_percent,
			PACKET_BUDGET_PERCENT,
			0.1,
			5,
		),
		successor_target_percent: clampPercent(
			input.successor_target_percent ?? base.successor_target_percent,
			SUCCESSOR_TARGET_PERCENT,
			5,
			50,
		),
		successor_ceiling_percent: clampPercent(
			input.successor_ceiling_percent ?? base.successor_ceiling_percent,
			SUCCESSOR_CEILING_PERCENT,
			20,
			80,
		),
		successor_force_percent: clampPercent(
			input.successor_force_percent ?? base.successor_force_percent,
			SUCCESSOR_FORCE_PERCENT,
			70,
			95,
		),
		context_window: Math.max(8_000, input.context_window ?? DEFAULT_CONTEXT_WINDOW),
	};
}

function tokensFromChars(chars: number, charsPerToken: number): number {
	if (!Number.isFinite(chars) || chars <= 0) return 0;
	return Math.ceil(chars / Math.max(1, charsPerToken));
}

export function estimateSuccessorFill(input: SuccessorFillInput = {}): SuccessorFill {
	const budget = resolveSuccessorBudget({
		context_window: input.contextWindow,
		successor_target_percent: input.targetPercent,
		successor_ceiling_percent: input.ceilingPercent,
		successor_force_percent: input.forcePercent,
		packet_budget_percent: input.packetBudgetPercent,
	});
	const cpt = input.charsPerToken ?? DEFAULT_CHARS_PER_TOKEN;
	const packetChars = (input.packetBytes ?? 0) + (input.promptChars ?? 0);
	const baselineChars = input.baselineChars ?? 0;
	const transcriptChars = input.transcriptChars ?? 0;
	const inlineSkillChars = input.inlineSkillChars ?? 0;
	const fileContentChars = input.fileContentChars ?? 0;
	const inheritedJunk = transcriptChars + inlineSkillChars + fileContentChars;
	const totalChars = baselineChars + packetChars + inheritedJunk;
	const tokens = tokensFromChars(totalChars, cpt);
	const percent = (tokens / budget.context_window) * 100;
	const packetTokens = tokensFromChars(packetChars, cpt);
	const packetCap = Math.floor((budget.context_window * budget.packet_budget_percent) / 100);
	const pollution: PollutionKind[] = [];
	if (transcriptChars > 0) pollution.push("transcript");
	if (inlineSkillChars > 0) pollution.push("inline_skill");
	if (fileContentChars > 0) pollution.push("file_contents");
	if (packetTokens > packetCap) pollution.push("over_packet");
	if (percent > budget.successor_target_percent) pollution.push("over_target");
	if (percent > budget.successor_ceiling_percent) pollution.push("over_ceiling");
	if (percent > budget.successor_force_percent) pollution.push("over_force");
	if (pollution.length === 0) pollution.push("ok");
	return {
		percent,
		tokens,
		packet_tokens: packetTokens,
		baseline_tokens: tokensFromChars(baselineChars, cpt),
		pollution,
		may_switch: !pollution.includes("over_ceiling") && !pollution.includes("transcript"),
	};
}

export function successorPromptBudgetLines(budget: SuccessorBudget = defaultSuccessorBudget()): string[] {
	return [
		`packet_budget: ${budget.packet_budget_percent}%`,
		`successor_target: ${budget.successor_target_percent}%`,
		`successor_ceiling: ${budget.successor_ceiling_percent}%`,
		`successor_force: ${budget.successor_force_percent}%`,
		"Do not reload transcripts, inline SKILL.md, or parent-read file contents.",
	];
}

export function trimPacketFields<T extends {
	last_assistant?: string;
	last_user?: string[];
	files_read?: string[];
	files_modified?: string[];
	jobs?: string[];
	prs?: string[];
}>(item: T): T {
	return {
		...item,
		last_assistant: undefined,
		last_user: (item.last_user ?? []).slice(-1),
		files_read: (item.files_read ?? []).slice(0, 8),
		files_modified: (item.files_modified ?? []).slice(0, 8),
		jobs: (item.jobs ?? []).slice(0, 3),
		prs: (item.prs ?? []).slice(0, 2),
	};
}
