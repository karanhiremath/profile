/**
 * Cursor stop / preCompact runner. Estimates usage, writes lineage, spawns successor.
 */
import { readFileSync } from "node:fs";
import { cursorHookResponse, runCursorHandoffHook } from "./handoff-successor.ts";
import type { CursorHandoffHookPayload } from "./handoff-lineage.ts";

function readStdin(): string {
	try {
		return readFileSync(0, "utf8");
	} catch {
		return "";
	}
}

function parsePayload(raw: string): CursorHandoffHookPayload {
	if (!raw.trim()) return {};
	try {
		return JSON.parse(raw) as CursorHandoffHookPayload;
	} catch {
		return {};
	}
}

export function main(raw = readStdin()): Record<string, string> {
	const payload = parsePayload(raw);
	const event = payload.hook_event_name || "";
	if (event && event !== "stop" && event !== "preCompact") {
		process.stdout.write("{}\n");
		return {};
	}
	if (event === "stop" && payload.status && payload.status !== "completed") {
		process.stdout.write("{}\n");
		return {};
	}
	try {
		const result = runCursorHandoffHook({ ...payload, hook_event_name: event || "stop" });
		const response = cursorHookResponse(result);
		process.stdout.write(`${JSON.stringify(response)}\n`);
		return response;
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		process.stderr.write(`handoff-cursor-hook: ${message}\n`);
		process.stdout.write("{}\n");
		return {};
	}
}

if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith("handoff-cursor-hook.ts")) {
	main();
}
