import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import {
	DEFAULT_CONTINUATION,
	applyTts,
	contextFromEnv,
	filterCatalog,
	publicStatus,
	transformText,
	type PolicyContext,
	type ResolvedBundle,
} from "../lib/engine.ts";

function resolvedPath(): string {
	const override = (process.env.AOS_POLICY_RESOLVED || "").trim();
	if (override) return override;
	const xdg = (process.env.XDG_DATA_HOME || "").trim();
	const home = xdg ? join(xdg, "aos/policy/compiled/resolved.json") : join(homedir(), ".local/share/aos/policy/compiled/resolved.json");
	return home;
}

function loadResolved(): ResolvedBundle | undefined {
	const path = resolvedPath();
	if (!existsSync(path)) return undefined;
	try {
		return JSON.parse(readFileSync(path, "utf8")) as ResolvedBundle;
	} catch {
		return undefined;
	}
}

function ctxFrom(pi: ExtensionAPI, ext: ExtensionContext): PolicyContext {
	let tools: string[] = [];
	try {
		tools = typeof pi.getActiveTools === "function" ? pi.getActiveTools() : [];
	} catch {
		tools = [];
	}
	return contextFromEnv(process.env, {
		class: process.env.PI_PROFILE_CLASS,
		agent: process.env.PI_PROFILE_AGENT || process.env.PI_AGENT,
		bridge_tools: tools.filter((name) => name.startsWith("pi__") || name === "subagent"),
		wrapper: process.env.AOS_WRAPPER || process.env.HERMES_WRAPPER || (process.env.HERMES_TUI ? "herm-tui" : "pi"),
	});
}

function applyCatalog(pi: ExtensionAPI, bundle: ResolvedBundle, ctx: PolicyContext): void {
	try {
		const active = typeof pi.getActiveTools === "function" ? pi.getActiveTools() : [];
		if (!Array.isArray(active) || !active.length) return;
		const kept = filterCatalog(bundle, "catalog.tools", active, ctx).map(String);
		pi.setActiveTools(kept);
	} catch {
		/* tools API unavailable */
	}
}

export default function (pi: ExtensionAPI) {
	let bundle = loadResolved();

	pi.registerTool({
		name: "aos_policy",
		label: "AOS policy",
		description: "Show the active AOS policy count. Silent rule bodies are never returned.",
		parameters: Type.Object({}),
		async execute() {
			if (!bundle) bundle = loadResolved();
			if (!bundle) return { content: [{ type: "text", text: "aos.policy=missing-resolved" }] };
			const ctx = contextFromEnv();
			const status = publicStatus(bundle, ctx);
			const text = [`aos.policy=active`, `active=${status.active}`, `silent=${status.silent}`].join("\n");
			return { content: [{ type: "text", text }] };
		},
	});

	pi.registerTool({
		name: "aos_voice_brief",
		label: "AOS voice brief",
		description:
			"Current a-top / a-top vi fleet snapshot as a short spoken brief. Use before voice replies. Never say you are working on it or that the chief of staff did not reply.",
		parameters: Type.Object({}),
		async execute() {
			try {
				const out = execFileSync("aos-policy", ["voice", "brief"], { encoding: "utf8", timeout: 4000 });
				return { content: [{ type: "text", text: out.trim() }] };
			} catch {
				return { content: [{ type: "text", text: DEFAULT_CONTINUATION }] };
			}
		},
	});

	pi.registerTool({
		name: "aos_voice_filter",
		label: "AOS voice filter",
		description: "Rewrite a TTS transcript. Exact stall or Cos-timeout sentences become continuation phrases.",
		parameters: Type.Object({ text: Type.String() }),
		async execute(_toolCall, args) {
			const text = String((args as { text?: string }).text || "");
			if (!bundle) bundle = loadResolved();
			if (bundle) {
				return { content: [{ type: "text", text: applyTts(bundle, text, contextFromEnv()) }] };
			}
			try {
				const out = execFileSync("aos-policy", ["voice", "filter"], {
					input: text,
					encoding: "utf8",
					timeout: 4000,
				});
				return { content: [{ type: "text", text: out.trim() }] };
			} catch {
				return { content: [{ type: "text", text: text.trim() || DEFAULT_CONTINUATION }] };
			}
		},
	});

	pi.on("session_start", async (_event, ext) => {
		bundle = loadResolved();
		if (!bundle) return;
		applyCatalog(pi, bundle, ctxFrom(pi, ext));
	});

	pi.on("before_agent_start", async (event, ext) => {
		if (!bundle) bundle = loadResolved();
		if (!bundle) return;
		const ctx = ctxFrom(pi, ext);
		applyCatalog(pi, bundle, ctx);
		const prompt = transformText(bundle, "stream.outbound", event.systemPrompt || "", ctx);
		if (prompt !== event.systemPrompt) return { systemPrompt: prompt };
	});
}
