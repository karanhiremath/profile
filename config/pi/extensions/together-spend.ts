/**
 * Local Together spend cap. Together has no API budget; this ledger blocks
 * new Together calls once spentUsd reaches budgetUsd.
 *
 *   /together-spend
 *   /together-spend set 150
 */
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
	TogetherSpendBlockedError,
	assertUnderBudget,
	formatStatus,
	loadLedger,
	recordCost,
	saveLedger,
	setBudget,
	TOGETHER_PROVIDER,
	type TogetherSpendLedger,
} from "./lib/together-spend.ts";

const LEDGER_PATH = join(homedir(), ".pi/agent/together-spend.json");

function readLedger(): TogetherSpendLedger {
	return loadLedger(LEDGER_PATH);
}

function writeLedger(ledger: TogetherSpendLedger): TogetherSpendLedger {
	saveLedger(LEDGER_PATH, ledger);
	return ledger;
}

function isTogether(ctx: ExtensionContext, provider?: string): boolean {
	return (provider ?? ctx.model?.provider) === TOGETHER_PROVIDER;
}

function blockIfTogetherOverCap(ctx: ExtensionContext, provider?: string): void {
	if (!isTogether(ctx, provider)) return;
	const ledger = readLedger();
	try {
		assertUnderBudget(ledger);
	} catch (err) {
		if (err instanceof TogetherSpendBlockedError && ctx.hasUI) {
			ctx.ui.notify(err.message, "error");
		}
		throw err;
	}
}

function costFromMessage(message: {
	role?: string;
	provider?: string;
	model?: string;
	timestamp?: number;
	usage?: { cost?: { total?: number } };
}): { provider?: string; model?: string; costUsd?: number; key?: string } | undefined {
	if (message.role !== "assistant" || message.provider !== TOGETHER_PROVIDER) return;
	const costUsd = message.usage?.cost?.total;
	if (!costUsd || costUsd <= 0) return;
	return {
		provider: message.provider,
		model: message.model,
		costUsd,
		key: `${message.timestamp ?? "t"}:${message.model ?? "m"}:${costUsd}`,
	};
}

export default function (pi: ExtensionAPI) {
	pi.on("before_agent_start", (_event, ctx) => {
		blockIfTogetherOverCap(ctx);
	});

	pi.on("before_provider_request", (_event, ctx) => {
		blockIfTogetherOverCap(ctx);
	});

	pi.on("message_end", (event, ctx) => {
		const recorded = costFromMessage(event.message as {
			role?: string;
			provider?: string;
			model?: string;
			timestamp?: number;
			usage?: { cost?: { total?: number } };
		});
		if (!recorded) return;
		const result = recordCost(readLedger(), recorded);
		if (!result.added) return;
		writeLedger(result.ledger);
		if (ctx.hasUI) ctx.ui.notify(formatStatus(result.ledger), "info");
	});

	pi.registerCommand("together-spend", {
		description: "Show or set the local Together spend cap",
		handler: async (raw, ctx) => {
			const argv = (raw || "").trim().split(/\s+/).filter(Boolean);
			let ledger = readLedger();
			if (argv[0] === "set") {
				const budgetUsd = Number(argv[1]);
				ledger = writeLedger(setBudget(ledger, budgetUsd));
			}
			const text = formatStatus(ledger);
			if (ctx.hasUI) ctx.ui.notify(text, "info");
			else console.log(text);
		},
	});
}
