export type PolicyContext = {
	wrapper?: string;
	provider?: string;
	class?: string;
	agent?: string;
	host_class?: string;
	bridge_tools?: string[];
};

export type PolicyRule = {
	id: string;
	surface: string[];
	action: string;
	visibility?: string;
	match?: { kind?: string; any?: string[] };
	replace?: string | string[];
	remap_to?: string;
};

export type Policy = {
	id: string;
	priority: number;
	enabled: boolean;
	mode: string;
	when?: Record<string, unknown>;
	surfaces?: string[];
	rules: PolicyRule[];
};

export type ResolvedBundle = {
	schema: string;
	name?: string;
	policies: Policy[];
};

function asList(value: unknown): unknown[] {
	if (value == null) return [];
	return Array.isArray(value) ? value : [value];
}

function lowerSet(values: unknown[]): Set<string> {
	return new Set(asList(values).map((item) => String(item).trim().toLowerCase()).filter(Boolean));
}

function matchAny(value: string, candidates: unknown): boolean {
	return lowerSet(asList(candidates)).has(value.trim().toLowerCase());
}

function whenClause(clause: unknown, ctx: PolicyContext): boolean {
	if (!clause || typeof clause !== "object") return true;
	const rec = clause as Record<string, unknown>;
	if ("all" in rec) return asList(rec.all).every((item) => whenClause(item, ctx));
	if ("any" in rec) return asList(rec.any).some((item) => whenClause(item, ctx));
	if ("class_not" in rec) {
		const current = String(ctx.class || "").trim().toLowerCase();
		return !lowerSet(asList(rec.class_not)).has(current);
	}
	const keys: Array<[string, keyof PolicyContext]> = [
		["wrapper", "wrapper"],
		["provider", "provider"],
		["class", "class"],
		["agent", "agent"],
		["host_class", "host_class"],
	];
	for (const [key, ctxKey] of keys) {
		if (!(key in rec)) continue;
		if (!matchAny(String(ctx[ctxKey] || ""), rec[key])) return false;
	}
	if ("bridge_tools" in rec) {
		const have = lowerSet(asList(ctx.bridge_tools));
		const want = lowerSet(asList(rec.bridge_tools));
		let hit = false;
		for (const item of want) if (have.has(item)) hit = true;
		if (!hit) return false;
	}
	return true;
}

export function policyApplies(policy: Policy, ctx: PolicyContext): boolean {
	if (policy.enabled === false) return false;
	return whenClause(policy.when || {}, ctx);
}

export function applicablePolicies(bundle: ResolvedBundle, ctx: PolicyContext): Policy[] {
	return bundle.policies
		.filter((policy) => policyApplies(policy, ctx))
		.sort((a, b) => b.priority - a.priority || a.id.localeCompare(b.id));
}

export function normalizeUtterance(text: string): string {
	return (text || "")
		.trim()
		.toLowerCase()
		.replace(/[\u2018\u2019]/g, "'")
		.replace(/["\u201c\u201d]/g, "")
		.replace(/[.!?…,;:]+$/g, "")
		.replace(/\s+/g, " ")
		.trim();
}

export function splitSentences(text: string): string[] {
	if (!(text || "").trim()) return [];
	const parts = text.match(/[\s\S]+?(?:[.!?]+(?:\s+|$)|$)/g);
	return parts && parts.some((part) => part.trim()) ? parts.filter((part) => part.trim()) : [text];
}

function pickReplace(rule: PolicyRule, seed: string): string {
	const raw = rule.replace;
	const phrases = (Array.isArray(raw) ? raw : raw ? [raw] : []).map((item) => String(item).trim()).filter(Boolean);
	if (!phrases.length) return "";
	const turn = process.env.AOS_VOICE_TURN || "";
	let sum = 0;
	const key = `${seed}\n${turn}`;
	for (let i = 0; i < key.length; i++) sum = (sum + key.charCodeAt(i) * (i + 1)) % 2147483647;
	return phrases[sum % phrases.length];
}

function rewriteSentences(text: string, needles: Set<string>, replacement: string): string {
	if (!replacement) return text;
	let changed = false;
	const out = splitSentences(text).map((part) => {
		if (!needles.has(normalizeUtterance(part))) return part;
		changed = true;
		const gap = part.match(/(\s*)$/)?.[1] || "";
		let repl = replacement.trim();
		if (repl && !/[.!?]$/.test(repl)) repl += ".";
		return repl + gap;
	});
	return changed ? out.join("") : text;
}

function nameMatches(name: string, match: PolicyRule["match"]): boolean {
	if (!match) return true;
	const kind = String(match.kind || "name").toLowerCase();
	const needles = (match.any || []).map(String);
	const lowered = name.toLowerCase();
	if (kind === "all") return true;
	if (kind === "name") return needles.some((item) => item.toLowerCase() === lowered);
	if (kind === "prefix") return needles.some((item) => lowered.startsWith(item.toLowerCase()));
	if (kind === "contains" || kind === "text") return needles.some((item) => lowered.includes(item.toLowerCase()));
	if (kind === "regex") return needles.some((item) => new RegExp(item, "i").test(name));
	if (kind === "exact") {
		const key = normalizeUtterance(name);
		return needles.some((item) => normalizeUtterance(item) === key);
	}
	if (kind === "sentence") {
		const keys = new Set(needles.map(normalizeUtterance));
		return splitSentences(name).some((part) => keys.has(normalizeUtterance(part)));
	}
	return false;
}

function applyRewrite(text: string, rule: PolicyRule): string {
	const match = rule.match || {};
	const kind = String(match.kind || "text").toLowerCase();
	const patterns = (match.any || []).map(String);
	if (!nameMatches(text, match)) return text;
	const replacement = pickReplace(rule, text);
	if (kind === "exact") return replacement || text;
	if (kind === "sentence") return rewriteSentences(text, new Set(patterns.map(normalizeUtterance)), replacement);
	if (!patterns.length) return replacement || text;
	if (!replacement) return stripPatterns(text, patterns);
	let out = text;
	for (const pattern of patterns) {
		out = out.replace(new RegExp(pattern.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), replacement);
	}
	return out;
}

function itemName(item: unknown): string {
	if (item && typeof item === "object" && "name" in item) return String((item as { name: string }).name);
	return String(item);
}

export function filterCatalog(bundle: ResolvedBundle, surface: string, items: unknown[], ctx: PolicyContext): unknown[] {
	const names = items.map(itemName);
	let exclusive = false;
	const allow = new Set<string>();
	const deny = new Set<string>();
	for (const policy of applicablePolicies(bundle, ctx)) {
		if (policy.mode === "exclusive") exclusive = true;
		for (const rule of policy.rules || []) {
			if (!rule.surface.includes(surface)) continue;
			const matched = names.filter((name) => nameMatches(name, rule.match));
			if (rule.action === "allow") matched.forEach((name) => allow.add(name));
			if (rule.action === "deny" || rule.action === "drop") {
				if (rule.match?.kind === "all") names.forEach((name) => deny.add(name));
				else matched.forEach((name) => deny.add(name));
			}
		}
	}
	if (exclusive) return items.filter((item) => allow.has(itemName(item)) && !deny.has(itemName(item)));
	return items.filter((item) => !deny.has(itemName(item)));
}

function stripPatterns(text: string, patterns: string[]): string {
	let out = text;
	for (const pattern of patterns) {
		if (!pattern) continue;
		out = out.replace(new RegExp(pattern.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), "");
	}
	return out.replace(/[ \t]{2,}/g, " ").replace(/\n{3,}/g, "\n\n");
}

export function transformText(bundle: ResolvedBundle, surface: string, text: string, ctx: PolicyContext): string {
	let out = text;
	for (const policy of applicablePolicies(bundle, ctx)) {
		for (const rule of policy.rules || []) {
			if (!rule.surface.includes(surface)) continue;
			if (!["strip", "redact", "rewrite", "drop"].includes(rule.action)) continue;
			const patterns = (rule.match?.any || []).map(String);
			if (rule.action === "drop" && nameMatches(out, rule.match)) return "";
			if (rule.action === "strip" || rule.action === "redact") {
				out = stripPatterns(out, patterns);
			}
			if (rule.action === "rewrite") {
				out = applyRewrite(out, rule);
			}
		}
	}
	return out;
}

export const DEFAULT_CONTINUATION =
	"Still with the last confirmed fleet snapshot. Next I'll check the live panes.";

export function applyTts(bundle: ResolvedBundle, text: string, ctx: PolicyContext, fallback = DEFAULT_CONTINUATION): string {
	const spoken = transformText(bundle, "stream.tts", text || "", ctx).trim();
	return spoken || fallback;
}

export function publicStatus(bundle: ResolvedBundle, ctx: PolicyContext): {
	schema: string;
	active: number;
	silent: number;
	ids: string[];
} {
	const applied = applicablePolicies(bundle, ctx);
	const silent = applied.filter((policy) => policy.rules.some((rule) => rule.visibility === "silent")).length;
	return { schema: "aos.policy.status.v1", active: applied.length, silent, ids: applied.map((p) => p.id) };
}

export function contextFromEnv(env: NodeJS.ProcessEnv = process.env, extra: PolicyContext = {}): PolicyContext {
	const wrapper =
		env.AOS_WRAPPER ||
		env.HERMES_WRAPPER ||
		(env.HERMES_TUI ? "herm-tui" : "") ||
		env.PI_WRAPPER ||
		"";
	const bridge = (env.AOS_BRIDGE_TOOLS || env.PI_BRIDGE_TOOLS || "")
		.split(",")
		.map((item) => item.trim())
		.filter(Boolean);
	return {
		wrapper,
		provider: env.AOS_PROVIDER || env.HERMES_PROVIDER || env.PI_PROVIDER || "",
		class: env.AOS_POLICY_CLASS || env.PI_PROFILE_CLASS || "",
		agent: env.AOS_POLICY_AGENT || env.PI_PROFILE_AGENT || env.PI_AGENT || env.HERMES_AGENT || "",
		host_class: env.AOS_HOST_CLASS || env.HARNESS_HOST_CLASS || "",
		bridge_tools: bridge,
		...extra,
	};
}
