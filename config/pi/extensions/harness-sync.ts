/**
 * /harness-sync — personal atop toolkit for pi/herm profiles, extensions, skills, packages.
 *
 *   /harness-sync
 *   /harness-sync status
 *   /harness-sync apply
 *   /harness-sync pull
 *   /harness-sync pull home-mac-mini
 *   /harness-sync pull --all
 *   /harness-sync pull --all tc2
 *   /harness-sync diff-host tc2
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function resolveBin(): string {
	const here = fileURLToPath(new URL(".", import.meta.url));
	const candidates = [
		join(here, "../../../bin/atop/harness-sync"),
		join(homedir(), "src/profile/bin/atop/harness-sync"),
	];
	for (const path of candidates) {
		if (existsSync(path)) return path;
	}
	return candidates[candidates.length - 1];
}

function run(args: string[]): Promise<{ exitCode: number; stdout: string; stderr: string }> {
	const bin = resolveBin();
	return new Promise((resolve, reject) => {
		const proc = spawn("bash", [bin, ...args], { stdio: ["ignore", "pipe", "pipe"] });
		let stdout = "";
		let stderr = "";
		const timer = setTimeout(() => {
			proc.kill("SIGTERM");
			reject(new Error("harness-sync timed out"));
		}, 180_000);
		proc.stdout.on("data", (chunk) => {
			stdout += String(chunk);
		});
		proc.stderr.on("data", (chunk) => {
			stderr += String(chunk);
		});
		proc.on("close", (code) => {
			clearTimeout(timer);
			resolve({ exitCode: code ?? 1, stdout, stderr });
		});
		proc.on("error", (err) => {
			clearTimeout(timer);
			reject(err);
		});
	});
}

export default function (pi: ExtensionAPI) {
	pi.registerCommand("harness-sync", {
		description: "Sync pi/herm profiles, extensions, skills, and packages (atop toolkit)",
		handler: async (raw, ctx) => {
			const argv = (raw || "").trim().split(/\s+/).filter(Boolean);
			const args = argv.length === 0 ? ["status"] : argv;
			try {
				const result = await run(args);
				const text = (result.stdout || result.stderr || `exit ${result.exitCode}`).slice(0, 4000);
				if (ctx.hasUI) ctx.ui.notify(text, result.exitCode === 0 ? "info" : "error");
				else console.log(text);
			} catch (err) {
				if (ctx.hasUI) ctx.ui.notify(String(err), "error");
				else console.error(err);
			}
		},
	});
}
