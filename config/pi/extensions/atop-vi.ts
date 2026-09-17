/**
 * atop_vi — coordinate via a live nvim prompt buffer.
 * Wraps ~/src/profile/bin/atop/vi. Never send-keys.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { spawn } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";

const VI = join(homedir(), "src/profile/bin/atop/vi");

function run(args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
	return new Promise((resolve, reject) => {
		const child = spawn(VI, args, { stdio: ["ignore", "pipe", "pipe"] });
		const stdout: Buffer[] = [];
		const stderr: Buffer[] = [];
		child.stdout.on("data", (d) => stdout.push(d));
		child.stderr.on("data", (d) => stderr.push(d));
		child.on("error", reject);
		child.on("close", (code) => {
			resolve({
				code: code ?? 1,
				stdout: Buffer.concat(stdout).toString("utf8"),
				stderr: Buffer.concat(stderr).toString("utf8"),
			});
		});
	});
}

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "atop_vi",
		label: "atop vi",
		description:
			"Read or write a live herm/pi nvim prompt buffer. Use instead of tmux send-keys. sessionId is herm-<ms> or omit to list.",
		parameters: Type.Object({
			sessionId: Type.Optional(Type.String({ description: "herm-<ms>, path, or nvim pid" })),
			op: Type.Unsafe<"list" | "get" | "set">({
				type: "string",
				enum: ["list", "get", "set"],
				description: "list open buffers, get text, or set from file",
			}),
			file: Type.Optional(Type.String({ description: "Absolute packet path for set" })),
		}),
		async execute(_id, params) {
			const op = params.op ?? (params.sessionId ? "get" : "list");
			const args: string[] = [];
			if (params.sessionId) args.push(params.sessionId);
			args.push(op);
			if (op === "set") {
				if (!params.file) {
					return { content: [{ type: "text", text: "set requires file" }], details: { ok: false } };
				}
				args.push("--file", params.file);
			}
			const result = await run(args);
			const text = [result.stdout, result.stderr].filter(Boolean).join("\n");
			return {
				content: [{ type: "text", text: text || `(exit ${result.code})` }],
				details: { code: result.code, op, sessionId: params.sessionId ?? "" },
			};
		},
	});

	pi.registerCommand("atop-vi", {
		description: "List live nvim prompt buffers (atop vi)",
		handler: async (_args, ctx) => {
			const result = await run(["list"]);
			ctx.ui.notify(result.stdout.trim() || result.stderr.trim() || "no buffers", "info");
		},
	});
}
