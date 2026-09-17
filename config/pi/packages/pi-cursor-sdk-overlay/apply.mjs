#!/usr/bin/env node
/**
 * Replayable routing patch for installed npm:pi-cursor-sdk.
 * There is no writable 0.3.6 source checkout; this re-applies contract +
 * wait=false injection after `pnpm update` overwrites dist.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createRequire } from "node:module";

const PREFERENCE =
	"When pi__subagent is exposed, delegate only through pi__subagent (wait defaults to false / background job). Do not call Cursor-native Task/subagents as a fallback while pi__subagent is exposed. When pi__mcp is exposed, prefer it for MCP work. Use Cursor-configured MCP or Cursor-native subagents only when the matching pi__ tool is not exposed or unavailable.";

const INJECT_HELPER = `function applyBridgedSubagentWait(piToolName, args) {
    if (piToolName !== "subagent")
        return args;
    const hasChain = Array.isArray(args.chain) && args.chain.length > 0;
    if (hasChain) {
        args.wait = true;
        return args;
    }
    args.wait = false;
    return args;
}
`;

function replaceOnce(haystack, needle, replacement, label) {
	if (haystack.includes(replacement) && !haystack.includes(needle)) return haystack;
	if (!haystack.includes(needle)) {
		throw new Error(`patch miss: ${label}`);
	}
	return haystack.replace(needle, replacement);
}

function patchContract(src) {
	return src.replace(
		/export const CURSOR_PI_BRIDGE_PREFERENCE_TEXT = "[\s\S]*?";/,
		`export const CURSOR_PI_BRIDGE_PREFERENCE_TEXT = ${JSON.stringify(PREFERENCE)};`,
	);
}

function patchManifest(src) {
	const needle = `            lines.push(\`- Pi bridge: call exposed pi__* MCP names (\${names}); pi shows real pi names.\`);
        }
    }
    lines.push("- Not callable: cursor-replay-* IDs, pi history names, transcript labels.");`;
	const replacement = `            lines.push(\`- Pi bridge: call exposed pi__* MCP names (\${names}); pi shows real pi names.\`);
            if (bridgeTools.some((tool) => tool.piToolName === "subagent" || tool.mcpToolName === "pi__subagent")) {
                lines.push("- When pi__subagent is exposed, do not call Cursor-native Task/subagents; they block the parent loop.");
            }
        }
    }
    lines.push("- Not callable: cursor-replay-* IDs, pi history names, transcript labels.");`;
	if (src.includes("do not call Cursor-native Task/subagents")) return src;
	return replaceOnce(src, needle, replacement, "cursor-tool-manifest.js");
}

function patchBridgeRun(src) {
	let next = src;
	if (!next.includes("function applyBridgedSubagentWait")) {
		const marker = `const MCP_SERVER_VERSION = "0.1.0";\n`;
		next = replaceOnce(next, marker, `${marker}${INJECT_HELPER}`, "inject helper");
	}
	const oldArgs = `            args: normalizeMcpArgs(argsValue),`;
	const newArgs = `            args: applyBridgedSubagentWait(piToolName, normalizeMcpArgs(argsValue)),`;
	if (!next.includes(newArgs)) {
		next = replaceOnce(next, oldArgs, newArgs, "enqueueToolRequest args");
	}
	return next;
}

function patchDocs(src) {
	const oldLine =
		"- When exposed, `pi__mcp` is preferred for MCP work and `pi__subagent` is preferred for delegation. Cursor-configured MCP and Cursor-native subagents are fallbacks when the matching pi tool is not exposed or is unavailable.";
	const newLine =
		"- When `pi__subagent` is exposed, it is the only valid delegation path (wait defaults to false). Cursor-native Task/subagents are not a fallback while it is exposed. When `pi__mcp` is exposed, prefer it for MCP work. Cursor-configured MCP and Cursor-native subagents are fallbacks only when the matching pi tool is not exposed or is unavailable.";
	if (src.includes("only valid delegation path")) return src;
	return replaceOnce(src, oldLine, newLine, "cursor-tool-surfaces.md");
}

const require = createRequire(import.meta.url);
const pkgJson = require(join(process.env.HOME, ".pi/agent/npm/node_modules/pi-cursor-sdk/package.json"));
if (pkgJson.name !== "pi-cursor-sdk") throw new Error("unexpected package");
const root = join(process.env.HOME, ".pi/agent/npm/node_modules/pi-cursor-sdk");

const files = [
	["dist/cursor-bridge-contract.js", patchContract],
	["dist/cursor-tool-manifest.js", patchManifest],
	["dist/cursor-pi-tool-bridge-run.js", patchBridgeRun],
	["docs/cursor-tool-surfaces.md", patchDocs],
];

for (const [rel, patch] of files) {
	const path = join(root, rel);
	const before = readFileSync(path, "utf8");
	const after = patch(before);
	if (after === before) continue;
	writeFileSync(path, after);
	console.log(`patched ${rel} (${pkgJson.version})`);
}

console.log(`pi-cursor-sdk-overlay applied to ${pkgJson.version} at ${root}`);
