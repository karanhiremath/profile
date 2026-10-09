import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { stripTypeScriptTypes } from "node:module";
import { SourceTextModule, SyntheticModule } from "node:vm";
import { test } from "node:test";
import type { ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import * as snapshotLib from "./compact-snapshot.ts";
import * as replacementLib from "./handoff-replacement.ts";

// Execute the real extension code without loading runtime packages, credentials, or extensions.
async function loadExtension(name: string) {
	const path = fileURLToPath(new URL(`../${name}.ts`, import.meta.url));
	const extra = name === "compact-handoff" ? "\nexport { switchToPrepared, trySilentHandoff };" : "";
	const module = new SourceTextModule(stripTypeScriptTypes(readFileSync(path, "utf8") + extra));
	await module.link(async (specifier) => {
		let exports: Record<string, unknown>;
		if (specifier === "./lib/compact-snapshot.ts") exports = { ...snapshotLib };
		else if (specifier === "./lib/handoff-replacement.ts") exports = { ...replacementLib };
		else if (specifier === "node:fs" || specifier === "node:path") exports = { ...await import(specifier) };
		else if (specifier === "@earendil-works/pi-coding-agent") exports = {
			BorderedLoader: class {}, convertToLlm: () => [], serializeConversation: () => "",
		};
		else if (specifier === "./lib/handoff-lineage.ts") exports = { readHandoffLineage: () => undefined };
		else if (specifier === "./lib/handoff-successor.ts") exports = {
			persistSuccessorLineage: () => { throw new Error("unexpected successor persistence"); },
			spawnSuccessorWorker: () => { throw new Error("unexpected successor spawn"); },
		};
		else if (specifier === "./lib/handoff-sibling.ts") exports = {
			createSiblingHandoffSession: () => { throw new Error("unexpected sibling creation"); },
			spawnHandoffPrintTurn: () => { throw new Error("unexpected warm-up"); },
		};
		else throw new Error(`Unexpected dependency: ${specifier}`);
		return new SyntheticModule(Object.keys(exports), function () {
			for (const [key, value] of Object.entries(exports)) this.setExport(key, value);
		});
	});
	await module.evaluate();
	return module.namespace;
}

function fixture(hasUI: boolean, failure?: "cancel" | "before" | "beforeCallback" | "delivery" | "after") {
	const root = mkdtempSync(join(tmpdir(), "handoff-replacement-"));
	const home = process.env.HOME;
	process.env.HOME = root;
	const ownerFile = join(root, "owner.jsonl");
	const childFile = join(root, "child.jsonl");
	writeFileSync(childFile, "");
	let stale = false;
	const calls: string[] = [];
	const guard = <T extends object>(object: T): T => new Proxy(object, {
		get(target, key, receiver) {
			assert.equal(stale, false, `stale owner access: ${String(key)}`);
			return Reflect.get(target, key, receiver);
		},
	});
	const replace = async (...args: unknown[]) => {
		calls.push(typeof args[0] === "string" ? "switch" : "new");
		if (failure === "cancel") return { cancelled: true };
		if (failure === "before") throw new Error("replacement refused");
		const options = args.at(-1) as { withSession: (ctx: unknown) => Promise<void> };
		stale = true;
		if (failure === "beforeCallback") throw new Error("initialization failed");
		await options.withSession({
			hasUI,
			ui: {
				notify: () => calls.push("replacement.notify"),
				setEditorText: () => {
					if (failure === "delivery") throw new Error("delivery failed");
					calls.push("replacement.editor");
				},
			},
			sendUserMessage: async () => {
				if (failure === "delivery") throw new Error("delivery failed");
				calls.push("replacement.message");
			},
		});
		if (failure === "after") throw new Error("post-replacement failure");
		return { cancelled: false };
	};
	const ctx = guard({
		hasUI, mode: hasUI ? "tui" : "json", cwd: root, model: {},
		getContextUsage: () => ({ contextWindow: 256000 }),
		sessionManager: guard({
			getSessionFile: () => ownerFile, getSessionId: () => "owner", getBranch: () => [],
		}),
		ui: guard({ notify: () => calls.push("owner.notify"), setEditorText: () => calls.push("owner.editor") }),
		newSession: replace, switchSession: replace,
	}) as unknown as ExtensionCommandContext;
	const snapshot = {
		schema: snapshotLib.SNAPSHOT_SCHEMA, ts: new Date().toISOString(), session_id: "owner",
		cwd: root, snapshot_path: join(root, "snapshot.json"), objective: "Continue implementation",
		last_user: [], files_read: [], files_modified: [], jobs: [], prs: [], blockers: [], next: [], do_not: [],
		kind: "implementation", budget_percent: 5,
	} as snapshotLib.CompactSnapshot;
	return { ctx, calls, ownerFile, childFile, snapshot,
		seed() { snapshotLib.writeHandoffPrep({ schema: snapshotLib.HANDOFF_PREP_SCHEMA,
			source_session_id: "owner", source_session_file: ownerFile, snapshot_path: snapshot.snapshot_path,
			phase: "aligned", child_session_file: childFile, child_session_id: "child" }); },
		cleanup() { if (home === undefined) delete process.env.HOME; else process.env.HOME = home;
			rmSync(root, { recursive: true, force: true }); },
	};
}

for (const hasUI of [true, false]) {
	for (const prepared of [true, false]) {
		test(`actual /handoff-now: ${hasUI ? "TUI" : "headless"}, ${prepared ? "sibling" : "new"}`, async () => {
			const f = fixture(hasUI);
			try {
				if (prepared) f.seed();
				const extension = await loadExtension("handoff");
				const commands = new Map<string, { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> }>();
				extension.default({ registerCommand: (name: string, command: never) => commands.set(name, command),
					sendUserMessage: () => { throw new Error("stale owner continuation"); } });
				await commands.get("handoff-now")!.handler("Continue implementation", f.ctx);
				assert.deepEqual(f.calls, hasUI
					? [prepared ? "switch" : "new", "replacement.notify", "replacement.editor"]
					: [prepared ? "switch" : "new", "replacement.message"]);
				const prep = snapshotLib.readHandoffPrep("owner")!;
				assert.equal(prep.phase, "switched");
				assert.equal(prep.source_session_file, f.ownerFile);
				assert.ok(prep.prompt_sent_at);
				assert.equal(snapshotLib.readHandoffPrep("child"), undefined);
			} finally { f.cleanup(); }
		});
	}
	for (const prepared of [true, false]) {
		test(`automatic lane: ${hasUI ? "TUI" : "headless"}, ${prepared ? "sibling" : "new"}`, async () => {
			const f = fixture(hasUI);
			try {
				if (prepared) f.seed();
				const extension = await loadExtension("compact-handoff");
				const result = prepared
					? await extension.switchToPrepared({}, f.ctx, f.snapshot)
					: await extension.trySilentHandoff(f.ctx, f.snapshot);
				assert.equal(result, true);
				assert.equal(snapshotLib.readHandoffPrep("owner")?.phase, "switched");
				assert.equal(snapshotLib.readHandoffPrep("child"), undefined);
				assert.equal(f.calls.includes("owner.notify"), false);
			} finally { f.cleanup(); }
		});
	}
}

for (const failure of ["cancel", "beforeCallback", "delivery", "after"] as const) {
	test(`actual command boundary: ${failure}`, async () => {
		const f = fixture(false, failure);
		try {
			f.seed();
			const extension = await loadExtension("handoff");
			const commands = new Map<string, { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> }>();
			extension.default({ registerCommand: (name: string, command: never) => commands.set(name, command),
				sendUserMessage: () => { throw new Error("unexpected owner continuation"); } });
			const result = commands.get("handoff-now")!.handler("Continue implementation", f.ctx);
			if (failure === "cancel") {
				await result;
				assert.equal(snapshotLib.readHandoffPrep("owner")?.phase, "aligned");
			} else {
				await assert.rejects(result, failure === "beforeCallback" ? /initialization failed/
					: failure === "delivery" ? /delivery failed/ : /post-replacement failure/);
				assert.equal(snapshotLib.readHandoffPrep("owner")?.phase,
					failure === "beforeCallback" ? "aligned" : "switched");
			}
		} finally { f.cleanup(); }
	});
}

for (const failure of ["cancel", "before", "beforeCallback", "delivery", "after"] as const) {
	test(`replacement boundary: ${failure}`, async () => {
		const f = fixture(false, failure);
		try {
			const writer = replacementLib.captureHandoffPrepWriter(f.ctx, f.snapshot.snapshot_path);
			const result = replacementLib.replaceHandoffSession(f.ctx, { prompt: "Continue", snapshotPath: f.snapshot.snapshot_path,
				promptAlreadySent: false, onSwitched: (delivered) => writer({ phase: "switched",
					switched_at: new Date().toISOString(), ...(delivered ? { prompt_sent_at: new Date().toISOString() } : {}) }) });
			if (failure === "delivery" || failure === "after") {
				await assert.rejects(result, failure === "delivery" ? /delivery failed/ : /post-replacement failure/);
				assert.equal(snapshotLib.readHandoffPrep("owner")?.phase, "switched");
				assert.equal(Boolean(snapshotLib.readHandoffPrep("owner")?.prompt_sent_at), failure === "after");
			} else {
				if (failure === "cancel") assert.equal(await result, false);
				else await assert.rejects(result, failure === "before" ? /replacement refused/ : /initialization failed/);
				assert.equal(snapshotLib.readHandoffPrep("owner"), undefined);
			}
		} finally { f.cleanup(); }
	});
}
