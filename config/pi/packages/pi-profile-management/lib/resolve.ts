import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export type GranolaPolicy = "deny" | "allow-on-skill";

export type ProfileClassConfig = {
	granola?: GranolaPolicy;
	mcpDeny?: string[];
	skillsDeny?: string[];
	skillsAllow?: string[];
};

export type ProfileManifest = {
	schema: string;
	defaultClass: string;
	granolaClasses?: string[];
	classes: Record<string, ProfileClassConfig>;
	agents: Record<string, string>;
	projects?: Array<{ match: string; defaultClass?: string; granola?: GranolaPolicy }>;
};

export type ResolvedProfile = {
	agent: string;
	className: string;
	granola: GranolaPolicy;
	mcpDeny: string[];
	skillsDeny: string[];
	skillsAllow: string[];
	cwd: string;
};

const GRANOLA_TOOL_MARKERS = [
	"granola",
	"query_granola_meetings",
	"list_meetings",
	"get_meetings",
	"get_meeting_transcript",
	"list_meeting_folders",
];

export function defaultManifestPath(): string {
	return join(dirname(fileURLToPath(import.meta.url)), "..", "manifests", "profiles.json");
}

export function loadManifest(path = defaultManifestPath()): ProfileManifest {
	const data = JSON.parse(readFileSync(path, "utf8")) as ProfileManifest;
	if (!data?.classes || !data.agents) {
		throw new Error(`invalid profile manifest: ${path}`);
	}
	return data;
}

export function resolveAgentName(env: NodeJS.ProcessEnv = process.env): string {
	for (const key of ["PI_PROFILE_AGENT", "PI_AGENT", "PI_SUBAGENT_NAME"]) {
		const value = (env[key] || "").trim();
		if (value) return value;
	}
	return "";
}

export function resolveClassName(
	manifest: ProfileManifest,
	opts: { agent?: string; className?: string; cwd?: string } = {},
): string {
	const explicit = (opts.className || process.env.PI_PROFILE_CLASS || "").trim();
	if (explicit) return explicit;
	const agent = (opts.agent || "").trim();
	if (agent && manifest.agents[agent]) return manifest.agents[agent];
	const cwd = opts.cwd || "";
	for (const project of manifest.projects || []) {
		if (project.match && cwd.includes(project.match) && project.defaultClass) {
			return project.defaultClass;
		}
	}
	return manifest.defaultClass || "implementor";
}

export function resolveProfile(
	manifest: ProfileManifest,
	opts: { agent?: string; className?: string; cwd?: string } = {},
): ResolvedProfile {
	const agent = (opts.agent || "").trim();
	const className = resolveClassName(manifest, opts);
	const cls = manifest.classes[className] || manifest.classes[manifest.defaultClass] || {};
	const granolaClasses = manifest.granolaClasses || ["librarian", "notetaker"];
	const granola: GranolaPolicy = granolaClasses.includes(className)
		? (cls.granola || "allow-on-skill")
		: "deny";
	const cwd = opts.cwd || "";
	return {
		agent,
		className,
		granola,
		mcpDeny: [...(cls.mcpDeny || [])],
		skillsDeny: [...(cls.skillsDeny || [])],
		skillsAllow: [...(cls.skillsAllow || [])],
		cwd,
	};
}

export function isGranolaTool(name: string): boolean {
	const n = name.toLowerCase();
	return GRANOLA_TOOL_MARKERS.some(
		(marker) => n === marker || n.includes(marker) || n.endsWith(`__${marker}`) || n.endsWith(`/${marker}`),
	);
}

export function isGranolaSkill(name: string): boolean {
	return name.toLowerCase().includes("granola");
}

export function filterTools(profile: ResolvedProfile, tools: string[]): string[] {
	if (profile.granola !== "deny") return tools;
	return tools.filter((name) => !isGranolaTool(name) && !profile.mcpDeny.some((deny) => name.toLowerCase().includes(deny.toLowerCase())));
}

export function granolaAllowed(profile: ResolvedProfile): boolean {
	return profile.granola === "allow-on-skill";
}

export function profilePrompt(profile: ResolvedProfile): string {
	if (granolaAllowed(profile)) {
		return [
			`profile.class=${profile.className} agent=${profile.agent || "(default)"}`,
			"Granola MCP/skills are allowed only after the granola-lookup skill is explicitly loaded for this librarian/notetaker profile.",
			"Do not preload plugin granola-context / granola-prep / granola-review / granola-engineer.",
		].join("\n");
	}
	return [
		`profile.class=${profile.className} agent=${profile.agent || "(default)"}`,
		"Granola MCP and granola skills are denied for this profile class.",
		"Meeting lookup belongs to librarian/notetaker profiles only. Do not call query_granola_meetings, list_meetings, get_meetings, or get_meeting_transcript.",
	].join("\n");
}
