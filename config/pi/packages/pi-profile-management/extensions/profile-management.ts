import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import {
	filterTools,
	granolaAllowed,
	loadManifest,
	profilePrompt,
	resolveAgentName,
	resolveProfile,
	type ProfileManifest,
	type ResolvedProfile,
} from "../lib/resolve.ts";

let manifest: ProfileManifest;
let current: ResolvedProfile | undefined;

function applyProfile(pi: ExtensionAPI, ctx: ExtensionContext): ResolvedProfile {
	if (!manifest) manifest = loadManifest();
	current = resolveProfile(manifest, {
		agent: resolveAgentName(),
		className: process.env.PI_PROFILE_CLASS,
		cwd: ctx.cwd || process.cwd(),
	});
	try {
		const active = typeof pi.getActiveTools === "function" ? pi.getActiveTools() : [];
		if (Array.isArray(active) && active.length) {
			pi.setActiveTools(filterTools(current, active));
		}
	} catch {
		/* tools API unavailable in this host */
	}
	if (ctx.hasUI) {
		ctx.ui.setStatus(
			"profile",
			ctx.ui.theme.fg("dim", `profile ${current.className}${granolaAllowed(current) ? " granola=skill" : " granola=off"}`),
		);
	}
	return current;
}

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "profile_manifest",
		label: "Profile manifest",
		description:
			"Show the loaded pi profile class, granola policy, and denied MCP/skills. Data-driven from manifests/profiles.json.",
		parameters: Type.Object({}),
		async execute() {
			const profile = current;
			const text = profile
				? [
						`class=${profile.className}`,
						`agent=${profile.agent || "(default)"}`,
						`granola=${profile.granola}`,
						`cwd=${profile.cwd}`,
						`mcpDeny=${profile.mcpDeny.join(",") || "(none)"}`,
						`skillsDeny=${profile.skillsDeny.join(",") || "(none)"}`,
					].join("\n")
				: "profile not resolved yet";
			return { content: [{ type: "text", text }] };
		},
	});

	pi.registerCommand("profile-class", {
		description: "Show or set PI_PROFILE_CLASS for this session (implementor|reviewer|planner|librarian|notetaker|...)",
		handler: async (args, ctx) => {
			const requested = args.trim();
			if (requested) process.env.PI_PROFILE_CLASS = requested;
			const profile = applyProfile(pi, ctx);
			if (ctx.hasUI) ctx.ui.notify(`profile.class=${profile.className} granola=${profile.granola}`, "info");
			else console.log(`profile.class=${profile.className} granola=${profile.granola}`);
		},
	});

	pi.on("session_start", async (_event, ctx) => {
		applyProfile(pi, ctx);
	});

	pi.on("before_agent_start", async (event, ctx) => {
		const profile = applyProfile(pi, ctx);
		return {
			systemPrompt: `${event.systemPrompt}\n\n${profilePrompt(profile)}`,
		};
	});
}
