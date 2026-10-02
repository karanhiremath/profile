/**
 * Handoff: transfer to a new session via a pointer snapshot, not a transcript dump.
 *
 *   /handoff [--type implementation|monitoring|planning] [--budget 5] [--llm] <goal>
 *   /handoff-bg ...   (sibling prepare; does not replace this session)
 *   /handoff-now ...  (non-interactive switch; used at ~75% or as fallback)
 *
 * Default path writes ~/.pi/agent/snapshots/<sid>.json and puts a pointer
 * ≤5% of the model window in the new session. Pull-up: subagent wait=false.
 * --llm is optional and still capped. History is not sent to grok-4.6:fast.
 */
import type { AgentMessage } from "@earendil-works/pi-agent-core";
import type { Message } from "@earendil-works/pi-ai/compat";
import type { ExtensionAPI, ExtensionCommandContext, SessionEntry } from "@earendil-works/pi-coding-agent";
import { BorderedLoader, convertToLlm, serializeConversation } from "@earendil-works/pi-coding-agent";
import {
	buildSnapshot,
	capText,
	formatHandoffAlignPrompt,
	formatHandoffPreparePrompt,
	formatHandoffPrompt,
	handoffPrepIsInFlight,
	handoffSwitchPresentation,
	handoffSwitchTarget,
	shouldFallbackHandoffPrompt,
	shouldInjectHandoffPrompt,
	shouldPushOwnerEditorOnDefer,
	ownerSessionIds,
	parseHandoffArgs,
	persistSnapshot,
	readHandoffPrepAny,
	resolveLimits,
	sessionSteerMode,
	shouldCreateHandoffSibling,
	shouldOpenNewHandoffSession,
	keepLiveHandoffChild,
	isHandoffChildSession,
	resolveLiveHandoffPrep,
	tryClaimHandoffPrep,
	writeHandoffPrepAliases,
	HANDOFF_PREP_SCHEMA,
	type CompactLimits,
	type SnapshotEntry,
} from "./lib/compact-snapshot.ts";
import { createSiblingHandoffSession, spawnHandoffPrintTurn } from "./lib/handoff-sibling.ts";
import { existsSync } from "node:fs";
import { dirname } from "node:path";

const LLM_SYSTEM_PROMPT = `You write a NEW-SESSION prompt. You do NOT continue the conversation. You do NOT take tools.

Output ONLY:
Read this compact snapshot first. Do not restate it. Do not reload transcripts.

snapshot: <path>
kind: implementation | monitoring | planning
Goal: <one line>
budget: <n>% of context window

On pull-up: spawn worker wait=false to execute snapshot next/objective. Parent does not read listed files. Parent also executes next in the same turn.

Execute Goal/next now. Do not ask. Do not explain this compact.

Rules:
- Keep the whole prompt under 12 lines.
- Do not paste snapshot JSON, transcripts, or file contents.`;

type HandoffMode = "editor" | "background" | "now" | "prepare" | "align";

function entryToMessage(entry: SessionEntry): AgentMessage | undefined {
	if (entry.type === "message") return entry.message;
	if (entry.type === "compaction") {
		return {
			role: "compactionSummary",
			summary: entry.summary,
			tokensBefore: entry.tokensBefore,
			timestamp: new Date(entry.timestamp).getTime(),
		};
	}
	return undefined;
}

function getHandoffMessages(branch: SessionEntry[]): AgentMessage[] {
	let compactionIndex = -1;
	for (let i = branch.length - 1; i >= 0; i--) {
		if (branch[i].type === "compaction") {
			compactionIndex = i;
			break;
		}
	}
	if (compactionIndex < 0) {
		return branch.map(entryToMessage).filter((message) => message !== undefined);
	}
	const compaction = branch[compactionIndex];
	const firstKeptIndex =
		compaction.type === "compaction" ? branch.findIndex((entry) => entry.id === compaction.firstKeptEntryId) : -1;
	const compactedBranch = [
		compaction,
		...(firstKeptIndex >= 0 ? branch.slice(firstKeptIndex, compactionIndex) : []),
		...branch.slice(compactionIndex + 1),
	];
	return compactedBranch.map(entryToMessage).filter((message) => message !== undefined);
}

function errorMessage(error: unknown): string {
	return error instanceof Error ? error.message : String(error);
}

function persistFromBranch(
	ctx: ExtensionCommandContext,
	goal: string,
	kind?: CompactLimits["kind"],
	budgetPercent?: number,
) {
	const sessionFile = ctx.sessionManager.getSessionFile();
	const snapshot = buildSnapshot({
		branch: ctx.sessionManager.getBranch() as SnapshotEntry[],
		sessionFile,
		cwd: ctx.cwd,
		goal,
		kind,
		budgetPercent,
		contextWindow: ctx.getContextUsage()?.contextWindow,
		sessionId: ownerSessionIds({
			sessionFile,
			sessionId: ctx.sessionManager.getSessionId?.(),
			env: process.env,
		}).canonical,
	});
	return { snapshot, ...persistSnapshot(snapshot), limits: resolveLimits({
		kind: snapshot.kind,
		goal,
		budgetPercent: snapshot.budget_percent,
		contextWindow: ctx.getContextUsage()?.contextWindow,
	}) };
}

function capConversationExtract(text: string, maxChars: number): string {
	if (text.length <= maxChars) return text;
	const head = Math.floor(maxChars * 0.35);
	const tail = maxChars - head - 40;
	return `${text.slice(0, head)}\n\n[... omitted ...]\n\n${text.slice(-Math.max(0, tail))}`;
}

async function streamLlmPrompt(
	ctx: ExtensionCommandContext,
	conversationText: string,
	goal: string,
	snapshotPath: string,
	kind: string,
	signal?: AbortSignal,
): Promise<string | null> {
	const model = ctx.model;
	if (!model) throw new Error("No model selected");
	const auth = await ctx.modelRegistry.getApiKeyAndHeaders(model);
	if (!auth.ok) throw new Error(auth.error);
	const provider = ctx.modelRegistry.getProvider(model.provider);
	if (!provider) throw new Error(`No provider registered for ${model.provider}`);

	const stream = provider.stream(
		model,
		{
			systemPrompt: LLM_SYSTEM_PROMPT,
			messages: [
				{
					role: "user",
					content: [
						{
							type: "text",
							text: `Snapshot path: ${snapshotPath}\nkind: ${kind}\nUser goal: ${goal}\n\nExtract only if the snapshot is missing a needed next step. Keep the prompt under 12 lines. Require worker wait=false to execute next/objective, not deltas-only gather. The next session must continue immediately.\n\n## Capped extract\n\n${conversationText}`,
						},
					],
					timestamp: Date.now(),
				} satisfies Message,
			],
		},
		{ apiKey: auth.apiKey ?? "", headers: auth.headers, env: auth.env, signal },
	);
	const response = await stream.result();
	if (response.stopReason === "aborted") return null;
	return response.content
		.filter((content): content is { type: "text"; text: string } => content.type === "text")
		.map((content) => content.text)
		.join("\n")
		.trim();
}

async function maybeLlmPrompt(
	ctx: ExtensionCommandContext,
	goal: string,
	snapshotPath: string,
	kind: string,
	fallback: string,
	limits: CompactLimits,
): Promise<string | null> {
	const messages = getHandoffMessages(ctx.sessionManager.getBranch());
	const conversationText = capConversationExtract(
		serializeConversation(convertToLlm(messages)),
		limits.extractMaxChars,
	);
	if (ctx.mode === "tui") {
		return ctx.ui.custom<string | null>((tui, theme, _kb, done) => {
			const loader = new BorderedLoader(tui, theme, "Rewriting handoff pointer...");
			loader.onAbort = () => done(null);
			streamLlmPrompt(ctx, conversationText, goal, snapshotPath, kind, loader.signal)
				.then((text) => done(capText(text || fallback, limits.promptMaxChars)))
				.catch((error) => {
					console.error("Handoff LLM rewrite failed:", error);
					ctx.ui.notify(`Handoff LLM rewrite failed, using pointer: ${errorMessage(error)}`, "warning");
					done(fallback);
				});
			return loader;
		});
	}
	try {
		const text = (await streamLlmPrompt(ctx, conversationText, goal, snapshotPath, kind)) || fallback;
		return capText(text, limits.promptMaxChars);
	} catch (error) {
		ctx.ui.notify(`Handoff LLM rewrite failed, using pointer: ${errorMessage(error)}`, "warning");
		return fallback;
	}
}

async function runHandoff(
	pi: ExtensionAPI,
	args: string,
	ctx: ExtensionCommandContext,
	mode: HandoffMode,
): Promise<void> {
	const command =
		mode === "background"
			? "/handoff-bg"
			: mode === "now"
				? "/handoff-now"
				: mode === "prepare"
					? "/handoff-prepare"
					: mode === "align"
						? "/handoff-align"
						: "/handoff";
	if (mode === "editor" && !ctx.hasUI) {
		ctx.ui.notify(`${command} requires TUI or RPC UI (Cursor SDK is OK)`, "error");
		return;
	}
	if (!ctx.model) {
		ctx.ui.notify("No model selected", "error");
		return;
	}

	const parsed = parseHandoffArgs(args);
	const persisted = persistFromBranch(ctx, parsed.goal, parsed.kind, parsed.budgetPercent);
	const autoGoal = mode === "now" || mode === "prepare" || mode === "align" || parsed.silent;
	const goal = parsed.goal || (autoGoal ? persisted.snapshot.objective : "");
	if (!goal) {
		ctx.ui.notify(
			`Usage: ${command} [--type implementation|monitoring|planning] [--budget 5] [--llm] <goal>`,
			"error",
		);
		return;
	}

	const { snapshot, path, limits } = parsed.goal
		? persisted
		: persistFromBranch(ctx, goal, parsed.kind, parsed.budgetPercent);
	let prompt = formatHandoffPrompt(snapshot, goal, limits.promptMaxChars);
	if (parsed.llm && mode === "editor" && !parsed.silent) {
		const rewritten = await maybeLlmPrompt(ctx, goal, path, snapshot.kind, prompt, limits);
		if (rewritten === null) {
			ctx.ui.notify("Handoff cancelled", "info");
			return;
		}
		prompt = rewritten;
	}

	if (mode === "prepare" || mode === "align" || (mode === "background" && (parsed.silent || !ctx.hasUI))) {
		await prepareOrAlignSibling(ctx, snapshot, path, mode === "align" ? "align" : "prepare");
		return;
	}

	if (mode === "now" || parsed.silent) {
		if (await switchPreparedOrNew(pi, ctx, snapshot, path, prompt)) return;
		const steerMode = sessionSteerMode({ hasUI: ctx.hasUI, mode: ctx.mode });
		const prep = currentOwnerPrep(ctx);
		if (shouldPushOwnerEditorOnDefer({ mode: steerMode, hasUI: ctx.hasUI, prep })) {
			ctx.ui.setEditorText(prompt);
			persistOwnerPrep(ctx, {
				...prep,
				schema: HANDOFF_PREP_SCHEMA,
				source_session_id: sourceSessionId(ctx),
				snapshot_path: path,
				prompt_sent_at: new Date().toISOString(),
			});
			ctx.ui.notify(`Kept pointer in editor. Snapshot: ${path}`, "info");
			return;
		}
		if (shouldFallbackHandoffPrompt({ prep, mode: steerMode })) {
			pi.sendUserMessage(prompt, { deliverAs: "followUp", triggerTurn: true });
			if (ctx.hasUI) ctx.ui.notify(`Fallback continue in this session. Snapshot: ${path}`, "info");
		}
		return;
	}

	if (mode === "background") {
		const approved = await ctx.ui.confirm(
			"Start background handoff session?",
			`Snapshot: ${path}\nPreserves this session and warms a sibling session. No switch yet.`,
		);
		if (!approved) {
			ctx.ui.setEditorText(prompt);
			ctx.ui.notify(`Kept pointer prompt. Snapshot: ${path}`, "info");
			return;
		}
		await prepareOrAlignSibling(ctx, snapshot, path, "prepare");
		return;
	}

	const editedPrompt = await ctx.ui.editor("Review handoff prompt", prompt);
	if (editedPrompt === undefined) {
		ctx.ui.notify("Handoff cancelled", "info");
		return;
	}

	const currentSessionFile = ctx.sessionManager.getSessionFile();
	const approved = await ctx.ui.confirm(
		"Switch to new session?",
		`Snapshot: ${path}\nCreates a linked Pi session and places the pointer prompt in the editor.`,
	);
	if (!approved) {
		ctx.ui.setEditorText(editedPrompt);
		ctx.ui.notify(`Kept pointer prompt. Snapshot: ${path}`, "info");
		return;
	}
	const newSessionResult = await ctx.newSession({
		parentSession: currentSessionFile,
		withSession: async (replacementCtx) => {
			replacementCtx.ui.setEditorText(editedPrompt);
			replacementCtx.ui.notify(`Switched. Snapshot: ${path}`, "info");
		},
	});
	if (newSessionResult.cancelled) ctx.ui.notify("New session cancelled", "info");
}

function ownerIds(ctx: ExtensionCommandContext) {
	return ownerSessionIds({
		sessionFile: ctx.sessionManager.getSessionFile(),
		sessionId: ctx.sessionManager.getSessionId?.(),
		env: process.env,
	});
}

function sourceSessionId(ctx: ExtensionCommandContext): string {
	return ownerIds(ctx).canonical;
}

function persistOwnerPrep(ctx: ExtensionCommandContext, prep: Parameters<typeof writeHandoffPrepAliases>[0]) {
	const ids = ownerIds(ctx);
	const previous = readHandoffPrepAny(ids.aliases);
	return writeHandoffPrepAliases(
		{ ...prep, ...keepLiveHandoffChild(previous, ctx.sessionManager.getSessionFile()), source_session_id: ids.canonical },
		ids.aliases,
	);
}

function currentOwnerPrep(ctx: ExtensionCommandContext) {
	return resolveLiveHandoffPrep({
		prep: readHandoffPrepAny(ownerIds(ctx).aliases),
		currentSessionFile: ctx.sessionManager.getSessionFile(),
	});
}

async function prepareOrAlignSibling(
	ctx: ExtensionCommandContext,
	snapshot: ReturnType<typeof persistFromBranch>["snapshot"],
	path: string,
	kind: "prepare" | "align",
): Promise<void> {
	const ids = ownerIds(ctx);
	const sourceId = ids.canonical;
	const existing = currentOwnerPrep(ctx);
	let childFile = existing?.child_session_file;
	let childId = existing?.child_session_id;
	const sessionFile = ctx.sessionManager.getSessionFile();
	const childExists = Boolean(
		childFile &&
			existsSync(childFile) &&
			!isHandoffChildSession({ childFile, currentFile: sessionFile }),
	);

	if (kind === "align" && childExists && childFile) {
		spawnHandoffPrintTurn({
			cwd: ctx.cwd,
			sessionFile: childFile,
			prompt: formatHandoffAlignPrompt(snapshot, snapshot.objective),
			source: "handoff-align",
		});
		persistOwnerPrep(ctx, {
			schema: HANDOFF_PREP_SCHEMA,
			source_session_id: sourceId,
			source_session_file: ctx.sessionManager.getSessionFile(),
			snapshot_path: path,
			child_session_id: childId,
			child_session_file: childFile,
			child_job_id: existing?.child_job_id,
			phase: "aligned",
			mode: sessionSteerMode({ hasUI: ctx.hasUI, mode: ctx.mode }),
			prepared_at: existing?.prepared_at || new Date().toISOString(),
			aligned_at: new Date().toISOString(),
			prompt_sent_at: existing?.prompt_sent_at,
		});
		if (ctx.hasUI) ctx.ui.notify(`Handoff aligned: ${childFile}`, "info");
		return;
	}

	if (childExists) {
		persistOwnerPrep(ctx, {
			schema: HANDOFF_PREP_SCHEMA,
			source_session_id: sourceId,
			source_session_file: existing?.source_session_file || ctx.sessionManager.getSessionFile(),
			snapshot_path: path,
			child_session_id: childId,
			child_session_file: childFile,
			child_job_id: existing?.child_job_id,
			phase: existing?.phase === "switched" ? "switched" : "prepared",
			mode: existing?.mode || sessionSteerMode({ hasUI: ctx.hasUI, mode: ctx.mode }),
			prepared_at: existing?.prepared_at || new Date().toISOString(),
			aligned_at: existing?.aligned_at,
			switched_at: existing?.switched_at,
			prompt_sent_at: existing?.prompt_sent_at,
		});
		if (ctx.hasUI) ctx.ui.notify(`Handoff already prepared: ${childFile}`, "info");
		return;
	}

	if (
		!shouldCreateHandoffSibling({
			childFile,
			fileExists: childExists,
			preparedAt: existing?.prepared_at,
			currentSessionFile: sessionFile,
		})
	) {
		if (ctx.hasUI) ctx.ui.notify("Handoff prepare already in flight", "info");
		return;
	}

	if (!existing) {
		const claim = tryClaimHandoffPrep({
			schema: HANDOFF_PREP_SCHEMA,
			source_session_id: sourceId,
			source_session_file: ctx.sessionManager.getSessionFile(),
			snapshot_path: path,
			phase: "prepared",
			prepared_at: new Date().toISOString(),
		}, ids.aliases);
		if (!claim.claimed) {
			if (ctx.hasUI) ctx.ui.notify("Handoff prepare already claimed", "info");
			return;
		}
	}

	let promptSentAt = existing?.prompt_sent_at;
	let jobId = existing?.child_job_id;
	try {
		const parentFile = ctx.sessionManager.getSessionFile();
		const sibling = createSiblingHandoffSession({
			cwd: ctx.cwd,
			sessionDir: ctx.sessionManager.getSessionDir?.() || (parentFile ? dirname(parentFile) : undefined),
			parentSessionFile: parentFile,
			sourceSessionId: sourceId,
			snapshotPath: path,
		});
		childFile = sibling.sessionFile;
		childId = sibling.sessionId;
		persistOwnerPrep(ctx, {
			schema: HANDOFF_PREP_SCHEMA,
			source_session_id: sourceId,
			source_session_file: ctx.sessionManager.getSessionFile(),
			snapshot_path: path,
			child_session_id: childId,
			child_session_file: childFile,
			phase: "prepared",
			mode: sessionSteerMode({ hasUI: ctx.hasUI, mode: ctx.mode }),
			prepared_at: existing?.prepared_at || new Date().toISOString(),
			aligned_at: existing?.aligned_at,
			prompt_sent_at: promptSentAt,
		});
		const spawned = spawnHandoffPrintTurn({
			cwd: ctx.cwd,
			sessionFile: childFile,
			prompt: formatHandoffPreparePrompt(snapshot, snapshot.objective),
			source: "handoff-prepare",
		});
		jobId = spawned.jobId;
		promptSentAt = new Date().toISOString();
	} catch (error) {
		ctx.ui.notify(`Handoff prepare failed: ${errorMessage(error)}`, "warning");
		return;
	}
	persistOwnerPrep(ctx, {
		schema: HANDOFF_PREP_SCHEMA,
		source_session_id: sourceId,
		source_session_file: ctx.sessionManager.getSessionFile(),
		snapshot_path: path,
		child_session_id: childId,
		child_session_file: childFile,
		child_job_id: jobId,
		phase: "prepared",
		mode: sessionSteerMode({ hasUI: ctx.hasUI, mode: ctx.mode }),
		prepared_at: existing?.prepared_at || new Date().toISOString(),
		aligned_at: existing?.aligned_at,
		prompt_sent_at: promptSentAt,
	});
	if (ctx.hasUI) {
		ctx.ui.notify(`Handoff prepared in background: ${childFile}`, "info");
	}
}

async function switchPreparedOrNew(
	pi: ExtensionAPI,
	ctx: ExtensionCommandContext,
	snapshot: ReturnType<typeof persistFromBranch>["snapshot"],
	path: string,
	prompt: string,
): Promise<boolean> {
	const prep = currentOwnerPrep(ctx);
	const steerMode = sessionSteerMode({ hasUI: ctx.hasUI, mode: ctx.mode });
	const sessionFile = ctx.sessionManager.getSessionFile();
	const siblingIsCurrent = isHandoffChildSession({
		childFile: prep?.child_session_file,
		currentFile: sessionFile,
	});
	const siblingExists = Boolean(
		prep?.child_session_file && existsSync(prep.child_session_file) && !siblingIsCurrent,
	);
	const prepInFlight = handoffPrepIsInFlight(prep, { fileExists: siblingExists, currentSessionFile: sessionFile });
	const target = handoffSwitchTarget({
		siblingFileExists: siblingExists,
		switchSessionAvailable: typeof ctx.switchSession === "function",
		prepInFlight,
		siblingIsCurrent,
	});
	let promptDelivered = !shouldInjectHandoffPrompt(prep);
	if (target === "switch-sibling" && prep?.child_session_file) {
		try {
			const result = await ctx.switchSession(prep.child_session_file, {
				withSession: async (replacementCtx) => {
					const presentation = handoffSwitchPresentation({
						mode: steerMode,
						hasUI: ctx.hasUI,
						replacementHasUI: replacementCtx.hasUI,
						prepared: true,
						promptAlreadySent: promptDelivered,
					});
					if (presentation.replacement.notify) {
						replacementCtx.ui.notify(`Handoff switch. Snapshot: ${path}`, "info");
					}
					if (presentation.replacement.setEditorText) {
						replacementCtx.ui.setEditorText(prompt);
						promptDelivered = true;
					}
					if (presentation.sendUserMessage) {
						await replacementCtx.sendUserMessage(prompt, { deliverAs: presentation.sendDeliverAs });
						promptDelivered = true;
					}
				},
			});
			persistOwnerPrep(ctx, {
				...prep,
				schema: "pi.handoff-prep.v1",
				source_session_id: sourceSessionId(ctx),
				snapshot_path: path,
				phase: "switched",
				switched_at: new Date().toISOString(),
				prompt_sent_at: promptDelivered ? new Date().toISOString() : prep.prompt_sent_at,
			});
			return promptDelivered || !result.cancelled;
		} catch (error) {
			if (ctx.hasUI) ctx.ui.notify(`Handoff switch failed: ${errorMessage(error)}`, "warning");
		}
		return promptDelivered;
	}
	if (target === "defer") {
		if (shouldPushOwnerEditorOnDefer({ mode: steerMode, hasUI: ctx.hasUI, prep })) {
			ctx.ui.setEditorText(prompt);
			persistOwnerPrep(ctx, {
				...prep,
				schema: "pi.handoff-prep.v1",
				source_session_id: sourceSessionId(ctx),
				snapshot_path: path,
				prompt_sent_at: new Date().toISOString(),
			});
			promptDelivered = true;
		}
		if (ctx.hasUI) ctx.ui.notify("Handoff sibling exists; not creating a second session", "warning");
		return promptDelivered;
	}
	if (
		!shouldOpenNewHandoffSession({
			target,
			siblingFileExists,
			childFile: prep?.child_session_file,
			childJobId: prep?.child_job_id,
			preparedAt: prep?.prepared_at,
			currentSessionFile: sessionFile,
		})
	) {
		if (shouldPushOwnerEditorOnDefer({ mode: steerMode, hasUI: ctx.hasUI, prep })) {
			ctx.ui.setEditorText(prompt);
			persistOwnerPrep(ctx, {
				...prep,
				schema: "pi.handoff-prep.v1",
				source_session_id: sourceSessionId(ctx),
				snapshot_path: path,
				prompt_sent_at: new Date().toISOString(),
			});
			promptDelivered = true;
		}
		if (ctx.hasUI) ctx.ui.notify("Handoff sibling exists; not creating a second session", "warning");
		return promptDelivered;
	}
	try {
		const result = await ctx.newSession({
			withSession: async (replacementCtx) => {
				const presentation = handoffSwitchPresentation({
					mode: steerMode,
					hasUI: ctx.hasUI,
					replacementHasUI: replacementCtx.hasUI,
					prepared: false,
					promptAlreadySent: promptDelivered,
				});
				if (presentation.replacement.notify) {
					replacementCtx.ui.notify(`Handoff-now. Snapshot: ${path}`, "info");
				}
				if (presentation.replacement.setEditorText) {
					replacementCtx.ui.setEditorText(prompt);
					promptDelivered = true;
				}
				if (presentation.sendUserMessage) {
					await replacementCtx.sendUserMessage(prompt, { deliverAs: presentation.sendDeliverAs });
					promptDelivered = true;
				}
			},
		});
		if (promptDelivered) {
			persistOwnerPrep(ctx, {
				...prep,
				schema: "pi.handoff-prep.v1",
				source_session_id: sourceSessionId(ctx),
				snapshot_path: path,
				phase: "switched",
				switched_at: new Date().toISOString(),
				prompt_sent_at: new Date().toISOString(),
			});
		}
		return promptDelivered || !result.cancelled;
	} catch (error) {
		if (ctx.hasUI) ctx.ui.notify(`Handoff-now session failed: ${errorMessage(error)}`, "warning");
		if (promptDelivered) {
			persistOwnerPrep(ctx, {
				...prep,
				schema: "pi.handoff-prep.v1",
				source_session_id: sourceSessionId(ctx),
				snapshot_path: path,
				phase: "switched",
				switched_at: new Date().toISOString(),
				prompt_sent_at: new Date().toISOString(),
			});
		}
		return promptDelivered;
	}
}

export default function (pi: ExtensionAPI) {
	pi.registerCommand("handoff", {
		description: "Pointer-snapshot handoff. Preferred over /compact. --type --budget --llm",
		handler: async (args, ctx) => {
			await runHandoff(pi, args, ctx, "editor");
		},
	});
	pi.registerCommand("handoff-prepare", {
		description: "Silent background sibling prepare. No switch. --type --budget",
		handler: async (args, ctx) => {
			await runHandoff(pi, args, ctx, "prepare");
		},
	});
	pi.registerCommand("handoff-align", {
		description: "Refresh the prepared sibling from the current snapshot.",
		handler: async (args, ctx) => {
			await runHandoff(pi, args, ctx, "align");
		},
	});
	pi.registerCommand("handoff-bg", {
		description: "Background sibling prepare. Does not replace this session. --type --budget --yes",
		handler: async (args, ctx) => {
			await runHandoff(pi, args, ctx, "background");
		},
	});
	pi.registerCommand("handoff-now", {
		description: "Non-interactive switch to the prepared sibling, or a new session.",
		handler: async (args, ctx) => {
			await runHandoff(pi, args, ctx, "now");
		},
	});
}
