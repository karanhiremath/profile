import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

export const LEDGER_SCHEMA = "kh.together-spend.v1";
export const DEFAULT_BUDGET_USD = 150;
export const TOGETHER_PROVIDER = "together";
const MAX_ENTRIES = 80;

export class TogetherSpendBlockedError extends Error {
	readonly remainingUsd: number;
	readonly budgetUsd: number;
	readonly spentUsd: number;

	constructor(ledger: TogetherSpendLedger) {
		super(
			`Together spend cap hit: $${ledger.spentUsd.toFixed(2)} / $${ledger.budgetUsd.toFixed(2)}. Switch model or raise with /together-spend set <usd>.`,
		);
		this.name = "TogetherSpendBlockedError";
		this.budgetUsd = ledger.budgetUsd;
		this.spentUsd = ledger.spentUsd;
		this.remainingUsd = remainingUsd(ledger);
	}
}

export type TogetherSpendEntry = {
	at: string;
	provider: string;
	model: string;
	costUsd: number;
	key: string;
};

export type TogetherSpendLedger = {
	schema: typeof LEDGER_SCHEMA;
	budgetUsd: number;
	spentUsd: number;
	entries: TogetherSpendEntry[];
};

export type RecordCostInput = {
	provider?: string;
	model?: string;
	costUsd?: number;
	key?: string;
	at?: string;
};

export function emptyLedger(budgetUsd = DEFAULT_BUDGET_USD): TogetherSpendLedger {
	return {
		schema: LEDGER_SCHEMA,
		budgetUsd,
		spentUsd: 0,
		entries: [],
	};
}

export function remainingUsd(ledger: TogetherSpendLedger): number {
	return Math.max(0, roundUsd(ledger.budgetUsd - ledger.spentUsd));
}

export function isOverBudget(ledger: TogetherSpendLedger): boolean {
	return ledger.spentUsd >= ledger.budgetUsd - 1e-9;
}

export function assertUnderBudget(ledger: TogetherSpendLedger): void {
	if (isOverBudget(ledger)) throw new TogetherSpendBlockedError(ledger);
}

export function formatStatus(ledger: TogetherSpendLedger): string {
	const pct = ledger.budgetUsd > 0 ? (100 * ledger.spentUsd) / ledger.budgetUsd : 100;
	return `Together spend $${ledger.spentUsd.toFixed(2)} / $${ledger.budgetUsd.toFixed(2)} (${pct.toFixed(1)}%), $${remainingUsd(ledger).toFixed(2)} left`;
}

export function setBudget(ledger: TogetherSpendLedger, budgetUsd: number): TogetherSpendLedger {
	if (!Number.isFinite(budgetUsd) || budgetUsd < 0) {
		throw new Error("budget must be a non-negative number");
	}
	return { ...ledger, budgetUsd: roundUsd(budgetUsd) };
}

export function recordCost(ledger: TogetherSpendLedger, input: RecordCostInput): {
	ledger: TogetherSpendLedger;
	added: boolean;
} {
	const provider = input.provider ?? "";
	if (provider !== TOGETHER_PROVIDER) return { ledger, added: false };
	const costUsd = roundUsd(input.costUsd ?? 0);
	if (costUsd <= 0) return { ledger, added: false };
	const key = input.key?.trim();
	if (key && ledger.entries.some((entry) => entry.key === key)) {
		return { ledger, added: false };
	}
	const entry: TogetherSpendEntry = {
		at: input.at ?? new Date().toISOString(),
		provider,
		model: input.model ?? "unknown",
		costUsd,
		key: key || `anon-${Date.now()}-${ledger.entries.length}`,
	};
	const entries = [...ledger.entries, entry].slice(-MAX_ENTRIES);
	const spentUsd = roundUsd(ledger.spentUsd + costUsd);
	return { ledger: { ...ledger, spentUsd, entries }, added: true };
}

export function loadLedger(path: string, fallbackBudgetUsd = DEFAULT_BUDGET_USD): TogetherSpendLedger {
	if (!existsSync(path)) return emptyLedger(fallbackBudgetUsd);
	const raw = JSON.parse(readFileSync(path, "utf8")) as Partial<TogetherSpendLedger>;
	const budgetUsd = Number.isFinite(raw.budgetUsd) ? Number(raw.budgetUsd) : fallbackBudgetUsd;
	const entries = Array.isArray(raw.entries) ? raw.entries.filter(isEntry) : [];
	const spentUsd = Number.isFinite(raw.spentUsd)
		? Number(raw.spentUsd)
		: entries.reduce((sum, entry) => sum + entry.costUsd, 0);
	return {
		schema: LEDGER_SCHEMA,
		budgetUsd: roundUsd(budgetUsd),
		spentUsd: roundUsd(spentUsd),
		entries: entries.slice(-MAX_ENTRIES),
	};
}

export function saveLedger(path: string, ledger: TogetherSpendLedger): void {
	mkdirSync(dirname(path), { recursive: true });
	writeFileSync(path, `${JSON.stringify(ledger, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
}

function isEntry(value: unknown): value is TogetherSpendEntry {
	if (!value || typeof value !== "object") return false;
	const entry = value as TogetherSpendEntry;
	return (
		typeof entry.at === "string" &&
		typeof entry.provider === "string" &&
		typeof entry.model === "string" &&
		typeof entry.key === "string" &&
		Number.isFinite(entry.costUsd)
	);
}

function roundUsd(value: number): number {
	return Math.round(value * 1e6) / 1e6;
}
