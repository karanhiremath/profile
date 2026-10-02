/**
 * Pointer handoff lane: prepare a sibling session at ~60%, align near ~70%,
 * and switch at ~75%. In-place /compact is fallback only.
 *
 * session_before_compact still returns `{ cancel: true }` when preferHandoff.
 * Any compact that still runs is immediately triaged as a new handoff candidate.
 * /snapshot [--type] [--budget] writes the pointer file without compacting.
 */
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
	buildSnapshot,
	continueInjectOptions,
	formatHandoffAlignPrompt,
	formatHandoffNowCommand,
	formatHandoffPrepareCommand,
	formatHandoffPreparePrompt,
	formatHandoffPrompt,
	formatPointerSummary,
	inCompactCooldown,
	loadCompactHandoffConfig,
	parseHandoffArgs,
	persistSnapshot,
	handoffPrepIsInFlight,
	handoffSwitchPresentation,
	handoffSwitchTarget,
	planHandoffLane,
	estimateContextPercent,
	handoffLaneSettled,
	shouldFallbackNewSession,
	shouldInjectContinueAfterLane,
	shouldInjectHandoffPrompt,
	shouldPushOwnerEditorOnDefer,
	shouldQueueHandoffNowAfterSwitch,
	shouldSpawnHandoffWarmup,
	preferHandoffAfterCompact,
	ownerSessionIds,
	readHandoffPrepAny,
	readSnapshot,
	shouldCancelInPlaceCompact,
	resolveLimits,
	sessionSteerMode,
	shouldAutoContinue,
	snapshotPathForSession,
	shouldCreateHandoffSibling,
	shouldOpenNewHandoffSession,
	keepLiveHandoffChild,
	isHandoffChildSession,
	resolveLiveHandoffPrep,
	tryClaimHandoffPrep,
	writeHandoffPrepAliases,
	HANDOFF_PREP_SCHEMA,
	type CompactSnapshot,
	type FileOpsLike,
	type HandoffKind,
	type HandoffPrepState,
	type SnapshotEntry,
} from "./lib/compact-snapshot.ts";
import { createSiblingHandoffSession, spawnHandoffPrintTurn } from "./lib/handoff-sibling.ts";
import { persistSuccessorLineage, spawnSuccessorWorker } from "./lib/handoff-successor.ts";
import { readHandoffLineage } from "./lib/handoff-lineage.ts";
import { existsSync, statSync } from "node:fs";
import { dirname } from "node:path";

let previousPercent: number | null = null;
let compacting = false;
let lastSnapshot: CompactSnapshot | undefined;
let lastCompactAt = 0;
let handoffQueued = false;
let handoffInFlight = false;

function ownerIds(ctx: ExtensionContext) {
	return ownerSessionIds({
		sessionFile: ctx.sessionManager.getSessionFile(),
		sessionId: ctx.sessionManager.getSessionId?.(),
		env: process.env,
	});
}

function resolveSessionId(ctx: ExtensionContext): string {
	return ownerIds(ctx).canonical;
}

function persistFromContext(
	ctx: ExtensionContext,
	opts?: {
		fileOps?: FileOpsLike;
		previousSummary?: string;
		goal?: string;
		kind?: HandoffKind;
		budgetPercent?: number;
	},
) {
	const sessionFile = ctx.sessionManager.getSessionFile();
	const snapshot = buildSnapshot({
		branch: ctx.sessionManager.getBranch() as SnapshotEntry[],
		fileOps: opts?.fileOps,
		previousSummary: opts?.previousSummary,
		sessionFile,
		cwd: ctx.cwd,
		goal: opts?.goal,
		kind: opts?.kind,
		budgetPercent: opts?.budgetPercent,
		sessionId: resolveSessionId(ctx),
		contextWindow: ctx.getContextUsage()?.contextWindow,
	});
	lastSnapshot = snapshot;
	return { snapshot, ...persistSnapshot(snapshot) };
}

function loadPersistedSnapshot(ctx: ExtensionContext): CompactSnapshot | undefined {
	if (lastSnapshot) return lastSnapshot;
	for (const id of ownerIds(ctx).aliases) {
		const snapshot = readSnapshot(snapshotPathForSession(id));
		if (snapshot) return snapshot;
	}
	return undefined;
}

function injectContinue(
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	snapshot: CompactSnapshot,
	opts?: { willRetry?: boolean },
): void {
	if (!shouldInjectContinueAfterLane({ handoffQueued, prep: currentPrep(ctx) })) return;
	const config = loadCompactHandoffConfig();
	if (!shouldAutoContinue({ autoContinue: config.autoContinue })) return;
	const idle = typeof ctx.isIdle === "function" ? ctx.isIdle() : true;
	const delivery = continueInjectOptions({ willRetry: opts?.willRetry, idle });
	const prompt = formatHandoffPrompt(snapshot, snapshot.objective);
	try {
		pi.sendUserMessage(prompt, {
			deliverAs: delivery.deliverAs,
			triggerTurn: delivery.triggerTurn,
		} as { deliverAs: "steer" | "followUp" });
		if (ctx.hasUI) {
			ctx.ui.notify(`Continuing after compact: ${snapshot.snapshot_path}`, "info");
		}
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		if (ctx.hasUI) ctx.ui.notify(`Compact continue failed: ${message}`, "warning");
	}
}

async function trySilentHandoff(ctx: ExtensionContext, snapshot: CompactSnapshot): Promise<boolean> {
	const newSession = (ctx as ExtensionCommandContext).newSession;
	if (typeof newSession !== "function") return false;
	const prep = currentPrep(ctx);
	if (
		!shouldOpenNewHandoffSession({
			target: "new-session",
			siblingFileExists: prepIsReady(prep, currentSessionFile(ctx)),
			childFile: prep?.child_session_file,
			childJobId: prep?.child_job_id,
			preparedAt: prep?.prepared_at,
			currentSessionFile: currentSessionFile(ctx),
		})
	) {
		return false;
	}
	const prompt = formatHandoffPrompt(snapshot, snapshot.objective);
	const steerMode = sessionSteerMode({ hasUI: ctx.hasUI, mode: ctx.mode });
	let promptDelivered = !shouldInjectHandoffPrompt(currentPrep(ctx));
	try {
		const result = await newSession({
			withSession: async (replacementCtx) => {
				const live = handoffSwitchPresentation({
					mode: steerMode,
					hasUI: ctx.hasUI,
					replacementHasUI: replacementCtx.hasUI,
					prepared: false,
					promptAlreadySent: promptDelivered,
				});
				if (live.replacement.notify) {
					replacementCtx.ui.notify(`Handoff-now. Snapshot: ${snapshot.snapshot_path}`, "info");
				}
				if (live.replacement.setEditorText) {
					replacementCtx.ui.setEditorText(prompt);
					promptDelivered = true;
				}
				if (live.sendUserMessage) {
					await replacementCtx.sendUserMessage(prompt, { deliverAs: live.sendDeliverAs });
					promptDelivered = true;
				}
			},
		});
		if (result.cancelled && !promptDelivered) return false;
		handoffQueued = true;
		lastCompactAt = Date.now();
		if (ctx.hasUI) {
			ctx.ui.notify(`Prefer handoff-now over compact: ${snapshot.snapshot_path}`, "info");
		}
		return true;
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		if (ctx.hasUI) ctx.ui.notify(`Handoff-now failed: ${message}`, "warning");
		return promptDelivered;
	}
}

async function preferHandoffOrContinue(
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	snapshot: CompactSnapshot,
	opts?: { willRetry?: boolean },
): Promise<void> {
	if (handoffQueued) return;
	const config = loadCompactHandoffConfig();
	persistPrep(ctx, snapshot, { phase: "compacted-triage" });
	if (preferHandoffAfterCompact({ preferHandoff: config.preferHandoff, willRetry: opts?.willRetry })) {
		await runHandoffLane(pi, ctx, snapshot, { compactedInsteadOfHandoff: true, willRetry: opts?.willRetry });
		return;
	}
	await runHandoffLane(pi, ctx, snapshot, { compactedInsteadOfHandoff: true, willRetry: opts?.willRetry });
	injectContinue(pi, ctx, snapshot, opts);
}

function queueHandoffNow(pi: ExtensionAPI, ctx: ExtensionContext, snapshot: CompactSnapshot): boolean {
	if (handoffQueued) return true;
	try {
		pi.sendUserMessage(formatHandoffNowCommand(snapshot), {
			deliverAs: "followUp",
			triggerTurn: true,
			expandPromptTemplates: true,
		} as { deliverAs: "steer" | "followUp"; expandPromptTemplates: boolean });
		handoffQueued = true;
		lastCompactAt = Date.now();
		if (ctx.hasUI) {
			ctx.ui.notify(`Queued /handoff-now: ${snapshot.snapshot_path}`, "info");
		}
		return true;
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		if (message.includes("already processing")) {
			try {
				pi.sendUserMessage(formatHandoffNowCommand(snapshot), {
					deliverAs: "steer",
					expandPromptTemplates: true,
				});
				handoffQueued = true;
				lastCompactAt = Date.now();
				return true;
			} catch {
				/* fall through */
			}
		}
		if (ctx.hasUI) ctx.ui.notify(`Handoff-now queue failed: ${message}`, "warning");
		return false;
	}
}

function currentSessionFile(ctx: ExtensionContext): string | undefined {
	return ctx.sessionManager.getSessionFile();
}

function currentPrep(ctx: ExtensionContext): HandoffPrepState | undefined {
	return resolveLiveHandoffPrep({
		prep: readHandoffPrepAny(ownerIds(ctx).aliases),
		currentSessionFile: currentSessionFile(ctx),
	});
}

function currentLineage(ctx: ExtensionContext) {
	for (const id of ownerIds(ctx).aliases) {
		const lineage = readHandoffLineage(id);
		if (lineage) return lineage;
	}
	return undefined;
}

function laneIsSettled(ctx: ExtensionContext, prep?: HandoffPrepState): boolean {
	const lineage = currentLineage(ctx);
	return handoffLaneSettled({
		prep,
		currentSessionFile: currentSessionFile(ctx),
		lineageSuccessorAt: lineage?.successor_at,
		lineageJobId: lineage?.child_job_id,
	});
}

function estimateLanePercent(ctx: ExtensionContext): { percent: number; source: string } {
	const usage = ctx.getContextUsage();
	const sessionFile = currentSessionFile(ctx);
	let sessionBytes = 0;
	if (sessionFile && existsSync(sessionFile)) {
		try {
			sessionBytes = statSync(sessionFile).size;
		} catch {
			sessionBytes = 0;
		}
	}
	return estimateContextPercent({
		usage,
		sessionBytes,
		contextWindow: usage?.contextWindow,
	});
}

function spawnSuccessorIfNeeded(
	ctx: ExtensionContext,
	snapshot: CompactSnapshot,
	prep?: HandoffPrepState,
): boolean {
	if (laneIsSettled(ctx, prep)) return false;
	try {
		const spawned = spawnSuccessorWorker({
			cwd: ctx.cwd,
			snapshot,
			sourceSessionId: resolveSessionId(ctx),
			sessionFile: prep?.child_session_file,
			sessionId: prep?.child_session_id,
		});
		const now = new Date().toISOString();
		const { path } = persistSuccessorLineage({
			ownerId: resolveSessionId(ctx),
			aliases: ownerIds(ctx).aliases,
			snapshot,
			ownerSessionFile: currentSessionFile(ctx),
			childSessionId: spawned.sessionId,
			childSessionFile: spawned.sessionFile,
			childJobId: spawned.jobId,
			phase: "successor",
			previous: currentLineage(ctx),
		});
		persistPrep(ctx, snapshot, {
			phase: "successor",
			child_session_id: spawned.sessionId,
			child_session_file: spawned.sessionFile,
			child_job_id: spawned.jobId,
			successor_job_id: spawned.jobId,
			successor_at: now,
			lineage_path: path,
		});
		if (ctx.hasUI) {
			ctx.ui.notify(`Handoff successor spawned: ${spawned.jobId}`, "info");
		}
		handoffQueued = true;
		lastCompactAt = Date.now();
		return true;
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		if (ctx.hasUI) ctx.ui.notify(`Handoff successor failed: ${message}`, "warning");
		return false;
	}
}

function prepIsReady(prep?: HandoffPrepState, currentFile?: string): boolean {
	if (!prep?.child_session_file) return false;
	if (isHandoffChildSession({ childFile: prep.child_session_file, currentFile })) return false;
	return existsSync(prep.child_session_file);
}

function resetHandoffLaneState(): void {
	previousPercent = null;
	compacting = false;
	lastSnapshot = undefined;
	lastCompactAt = 0;
	handoffQueued = false;
	handoffInFlight = false;
}

function persistPrep(
	ctx: ExtensionContext,
	snapshot: CompactSnapshot,
	patch: Partial<HandoffPrepState>,
): HandoffPrepState {
	const ids = ownerIds(ctx);
	const previous = readHandoffPrepAny(ids.aliases);
	const next: HandoffPrepState = {
		schema: "pi.handoff-prep.v1",
		source_session_id: ids.canonical,
		source_session_file: ctx.sessionManager.getSessionFile(),
		snapshot_path: snapshot.snapshot_path,
		...previous,
		...patch,
		...keepLiveHandoffChild(previous, currentSessionFile(ctx)),
		source_session_id: ids.canonical,
		snapshot_path: snapshot.snapshot_path,
	};
	writeHandoffPrepAliases(next, ids.aliases);
	return next;
}

function prepareSibling(
	ctx: ExtensionContext,
	snapshot: CompactSnapshot,
	opts?: { spawnWarmup?: boolean },
): HandoffPrepState | undefined {
	const existing = currentPrep(ctx);
	const sessionFile = currentSessionFile(ctx);
	const childExists = Boolean(
		existing?.child_session_file &&
			existsSync(existing.child_session_file) &&
			!isHandoffChildSession({ childFile: existing.child_session_file, currentFile: sessionFile }),
	);
	if (childExists && existing) {
		return persistPrep(ctx, snapshot, { phase: existing.phase || "prepared" });
	}
	if (
		!shouldCreateHandoffSibling({
			childFile: existing?.child_session_file,
			fileExists: childExists,
			preparedAt: existing?.prepared_at,
			currentSessionFile: sessionFile,
		})
	) {
		return existing;
	}
	if (!existing) {
		const claim = tryClaimHandoffPrep({
			schema: HANDOFF_PREP_SCHEMA,
			source_session_id: resolveSessionId(ctx),
			source_session_file: ctx.sessionManager.getSessionFile(),
			snapshot_path: snapshot.snapshot_path,
			phase: "prepared",
			prepared_at: new Date().toISOString(),
		}, ownerIds(ctx).aliases);
		if (!claim.claimed) {
			const other = claim.existing;
			if (other?.child_session_file && existsSync(other.child_session_file)) {
				return persistPrep(ctx, snapshot, { phase: other.phase || "prepared" });
			}
			return other;
		}
	}
	const spawnWarmup = opts?.spawnWarmup !== false;
	try {
		const parentFile = ctx.sessionManager.getSessionFile();
		const sibling = createSiblingHandoffSession({
			cwd: ctx.cwd,
			sessionDir: typeof ctx.sessionManager.getSessionDir === "function" ? ctx.sessionManager.getSessionDir() : parentFile ? dirname(parentFile) : undefined,
			parentSessionFile: parentFile,
			sourceSessionId: resolveSessionId(ctx),
			snapshotPath: snapshot.snapshot_path,
		});
		persistPrep(ctx, snapshot, {
			child_session_id: sibling.sessionId,
			child_session_file: sibling.sessionFile,
			phase: "prepared",
			mode: sessionSteerMode({ hasUI: ctx.hasUI, mode: ctx.mode }),
			prepared_at: existing?.prepared_at || new Date().toISOString(),
		});
		const spawned = spawnWarmup
			? spawnHandoffPrintTurn({
					cwd: ctx.cwd,
					sessionFile: sibling.sessionFile,
					prompt: formatHandoffPreparePrompt(snapshot, snapshot.objective),
					source: "handoff-prepare",
				})
			: undefined;
		const prep = persistPrep(ctx, snapshot, {
			child_session_id: sibling.sessionId,
			child_session_file: sibling.sessionFile,
			child_job_id: spawned?.jobId,
			phase: "prepared",
			mode: sessionSteerMode({ hasUI: ctx.hasUI, mode: ctx.mode }),
			prepared_at: existing?.prepared_at || new Date().toISOString(),
			...(spawned ? { prompt_sent_at: new Date().toISOString() } : {}),
		});
		if (ctx.hasUI) {
			ctx.ui.notify(`Handoff prepared in background: ${sibling.sessionFile}`, "info");
		}
		return prep;
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		if (ctx.hasUI) ctx.ui.notify(`Handoff prepare failed: ${message}`, "warning");
		persistPrep(ctx, snapshot, { phase: "prepared", prepared_at: new Date().toISOString() });
		return undefined;
	}
}

function alignSibling(ctx: ExtensionContext, snapshot: CompactSnapshot): void {
	const prep = currentPrep(ctx);
	if (!prepIsReady(prep, currentSessionFile(ctx)) || !prep?.child_session_file) return;
	try {
		spawnHandoffPrintTurn({
			cwd: ctx.cwd,
			sessionFile: prep.child_session_file,
			prompt: formatHandoffAlignPrompt(snapshot, snapshot.objective),
			source: "handoff-align",
		});
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		if (ctx.hasUI) ctx.ui.notify(`Handoff align spawn failed: ${message}`, "warning");
	}
	persistPrep(ctx, snapshot, { phase: "aligned", aligned_at: new Date().toISOString() });
	if (ctx.hasUI) {
		ctx.ui.notify(`Handoff aligned: ${prep.child_session_file}`, "info");
	}
}

async function switchToPrepared(
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	snapshot: CompactSnapshot,
	opts?: { willRetry?: boolean; sameTickPrepare?: boolean; spawnWarmup?: boolean },
): Promise<boolean> {
	const prep = currentPrep(ctx);
	const sessionFile = currentSessionFile(ctx);
	const siblingIsCurrent = isHandoffChildSession({
		childFile: prep?.child_session_file,
		currentFile: sessionFile,
	});
	const siblingExists = prepIsReady(prep, sessionFile);
	const prepInFlight = handoffPrepIsInFlight(prep, { fileExists: siblingExists, currentSessionFile: sessionFile });
	const steerMode = sessionSteerMode({ hasUI: ctx.hasUI, mode: ctx.mode });
	const prompt = formatHandoffPrompt(snapshot, snapshot.objective);
	const cmd = ctx as ExtensionCommandContext;
	const switchSessionAvailable = typeof cmd.switchSession === "function";
	const target = handoffSwitchTarget({
		siblingFileExists: siblingExists,
		switchSessionAvailable,
		prepInFlight,
		sameTickPrepare: opts?.sameTickPrepare,
		spawnWarmup: opts?.spawnWarmup,
		siblingIsCurrent,
	});
	let promptDelivered = !shouldInjectHandoffPrompt(prep);
	if (target === "switch-sibling" && prep?.child_session_file) {
		try {
			const result = await cmd.switchSession(prep.child_session_file, {
				withSession: async (replacementCtx) => {
					const presentation = handoffSwitchPresentation({
						mode: steerMode,
						hasUI: ctx.hasUI,
						replacementHasUI: replacementCtx.hasUI,
						prepared: true,
						promptAlreadySent: promptDelivered,
					});
					if (presentation.replacement.notify) {
						replacementCtx.ui.notify(`Handoff switch. Snapshot: ${snapshot.snapshot_path}`, "info");
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
			if (!result.cancelled) {
				persistPrep(ctx, snapshot, {
					phase: "switched",
					switched_at: new Date().toISOString(),
					mode: steerMode,
					prompt_sent_at: new Date().toISOString(),
				});
				handoffQueued = true;
				lastCompactAt = Date.now();
				const ownerPresentation = handoffSwitchPresentation({
					mode: steerMode,
					hasUI: ctx.hasUI,
					prepared: true,
					promptAlreadySent: true,
				});
				if (ownerPresentation.owner.notify) {
					ctx.ui.notify(`Pushed handoff session to you. Coordinate steering with ${prep.child_session_id || prep.child_session_file}`, "info");
				}
				if (!isHandoffChildSession({ childFile: prep.child_session_file, currentFile: currentSessionFile(ctx) })) {
					spawnSuccessorIfNeeded(ctx, snapshot, currentPrep(ctx));
				}
				return true;
			}
			if (promptDelivered) {
				persistPrep(ctx, snapshot, {
					phase: "switched",
					switched_at: new Date().toISOString(),
					mode: steerMode,
					prompt_sent_at: new Date().toISOString(),
				});
			}
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			if (ctx.hasUI) ctx.ui.notify(`Handoff switch failed: ${message}`, "warning");
		}
		if (
			shouldQueueHandoffNowAfterSwitch({ promptDelivered, mode: steerMode, switchSessionAvailable }) &&
			queueHandoffNow(pi, ctx, snapshot)
		) {
			persistPrep(ctx, snapshot, { phase: "queued", queued_at: new Date().toISOString(), mode: steerMode });
			spawnSuccessorIfNeeded(ctx, snapshot, currentPrep(ctx));
			return true;
		}
		spawnSuccessorIfNeeded(ctx, snapshot, currentPrep(ctx));
		return promptDelivered;
	}
	if (target === "defer") {
		if (
			siblingExists &&
			shouldQueueHandoffNowAfterSwitch({ promptDelivered, mode: steerMode, switchSessionAvailable }) &&
			queueHandoffNow(pi, ctx, snapshot)
		) {
			persistPrep(ctx, snapshot, { phase: "queued", queued_at: new Date().toISOString(), mode: steerMode });
			spawnSuccessorIfNeeded(ctx, snapshot, currentPrep(ctx));
			return true;
		}
		if (shouldPushOwnerEditorOnDefer({ mode: steerMode, hasUI: ctx.hasUI, prep })) {
			ctx.ui.setEditorText(prompt);
			promptDelivered = true;
			persistPrep(ctx, snapshot, { prompt_sent_at: new Date().toISOString(), mode: steerMode });
		}
		if (ctx.hasUI) ctx.ui.notify("Handoff sibling ready; waiting for switchSession", "info");
		spawnSuccessorIfNeeded(ctx, snapshot, currentPrep(ctx));
		return promptDelivered;
	}
	if (
		shouldOpenNewHandoffSession({
			target,
			siblingFileExists: siblingExists,
			childFile: prep?.child_session_file,
			childJobId: prep?.child_job_id,
			preparedAt: prep?.prepared_at,
			sameTickPrepare: opts?.sameTickPrepare,
			spawnWarmup: opts?.spawnWarmup,
			currentSessionFile: sessionFile,
		}) &&
		(await trySilentHandoff(ctx, snapshot))
	) {
		persistPrep(ctx, snapshot, {
			phase: "switched",
			switched_at: new Date().toISOString(),
			mode: steerMode,
			prompt_sent_at: new Date().toISOString(),
		});
		return true;
	}
	if (
		shouldFallbackNewSession({
			siblingFileExists: siblingExists,
			prepInFlight,
			sameTickPrepare: opts?.sameTickPrepare,
			spawnWarmup: opts?.spawnWarmup,
			siblingIsCurrent,
		}) &&
		shouldQueueHandoffNowAfterSwitch({ promptDelivered, mode: steerMode, switchSessionAvailable }) &&
		queueHandoffNow(pi, ctx, snapshot)
	) {
		persistPrep(ctx, snapshot, { phase: "queued", queued_at: new Date().toISOString(), mode: steerMode });
		spawnSuccessorIfNeeded(ctx, snapshot, currentPrep(ctx));
		return true;
	}
	if (spawnSuccessorIfNeeded(ctx, snapshot, currentPrep(ctx))) return true;
	if (steerMode !== "interactive") {
		injectContinue(pi, ctx, snapshot, opts);
	}
	return false;
}

async function runHandoffLane(
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	snapshot: CompactSnapshot,
	opts?: { compactedInsteadOfHandoff?: boolean; willRetry?: boolean },
): Promise<void> {
	if (handoffInFlight) return;
	handoffInFlight = true;
	try {
		const config = loadCompactHandoffConfig();
		const prep = currentPrep(ctx);
		const estimated = estimateLanePercent(ctx);
		const percent = estimated.percent;
		const plan = planHandoffLane({
			percent,
			previousPercent,
			prepared: prepIsReady(prep, currentSessionFile(ctx)),
			aligned: Boolean(prep?.aligned_at),
			switched: laneIsSettled(ctx, prep),
			compactedInsteadOfHandoff: opts?.compactedInsteadOfHandoff,
			preparePercent: config.handoffPreparePercent,
			alignPercent: config.handoffAlignPercent,
			switchPercent: config.handoffSwitchPercent,
			overflowPercent: config.overflowPercent,
			hasUI: ctx.hasUI,
			mode: ctx.mode,
		});
		if (plan.actions.length === 0) return;
		const spawnWarmup = shouldSpawnHandoffWarmup(plan.actions);
		const sameTickPrepare = plan.actions.includes("prepare") && plan.actions.includes("switch");
		if (plan.actions.includes("prepare")) {
			prepareSibling(ctx, snapshot, { spawnWarmup });
		}
		if (plan.actions.includes("align") && !plan.actions.includes("switch")) {
			alignSibling(ctx, snapshot);
		}
		if (plan.actions.includes("switch")) {
			const presentation = handoffSwitchPresentation({
				mode: plan.steerMode,
				hasUI: ctx.hasUI,
				prepared: prepIsReady(currentPrep(ctx), currentSessionFile(ctx)),
			});
			if (presentation.owner.notify) {
				ctx.ui.notify(`Context ${Math.round(percent)}% — pushing prepared handoff`, "info");
			}
			await switchToPrepared(pi, ctx, snapshot, {
				willRetry: opts?.willRetry,
				sameTickPrepare,
				spawnWarmup,
			});
			return;
		}
		if (plan.actions.includes("prepare") && !prepIsReady(currentPrep(ctx), currentSessionFile(ctx))) {
			queueHandoffPrepare(pi, ctx, snapshot);
		}
	} finally {
		handoffInFlight = false;
	}
}

function queueHandoffPrepare(pi: ExtensionAPI, ctx: ExtensionContext, snapshot: CompactSnapshot): boolean {
	const prep = currentPrep(ctx);
	if (prepIsReady(prep, currentSessionFile(ctx))) return false;
	if (
		!shouldFallbackNewSession({
			siblingFileExists: prepIsReady(prep, currentSessionFile(ctx)),
			prepInFlight: handoffPrepIsInFlight(prep, {
				fileExists: prepIsReady(prep, currentSessionFile(ctx)),
				currentSessionFile: currentSessionFile(ctx),
			}),
			siblingIsCurrent: isHandoffChildSession({
				childFile: prep?.child_session_file,
				currentFile: currentSessionFile(ctx),
			}),
		})
	) {
		return false;
	}
	try {
		pi.sendUserMessage(formatHandoffPrepareCommand(snapshot), {
			deliverAs: "followUp",
			triggerTurn: true,
			expandPromptTemplates: true,
		} as { deliverAs: "steer" | "followUp"; expandPromptTemplates: boolean });
		return true;
	} catch {
		return false;
	}
}

async function maybeHandoffLane(pi: ExtensionAPI, ctx: ExtensionContext): Promise<void> {
	const estimated = estimateLanePercent(ctx);
	if (estimated.source === "unknown") return;
	const usage = ctx.getContextUsage();
	const config = loadCompactHandoffConfig();
	const limits = resolveLimits({
		contextWindow: usage?.contextWindow,
		config,
	});
	const percent = estimated.percent;
	const prep = currentPrep(ctx);
	const plan = planHandoffLane({
		percent,
		previousPercent,
		prepared: prepIsReady(prep, currentSessionFile(ctx)),
		aligned: Boolean(prep?.aligned_at),
		switched: laneIsSettled(ctx, prep),
		preparePercent: limits.handoffPreparePercent,
		alignPercent: limits.handoffAlignPercent,
		switchPercent: limits.handoffSwitchPercent,
		overflowPercent: limits.overflowPercent,
		hasUI: ctx.hasUI,
		mode: ctx.mode,
	});
	previousPercent = percent;
	if (handoffQueued && inCompactCooldown(lastCompactAt, config.compactCooldownMs)) return;
	if (plan.actions.includes("switch")) handoffQueued = false;
	if (compacting || plan.actions.length === 0) return;
	if (plan.phase !== "prepare" && inCompactCooldown(lastCompactAt, config.compactCooldownMs)) return;
	const { snapshot } = persistFromContext(ctx);
	if (shouldCancelInPlaceCompact({ preferHandoff: config.preferHandoff })) {
		void runHandoffLane(pi, ctx, snapshot);
		return;
	}
	if (percent < limits.autoCompactPercent) {
		void runHandoffLane(pi, ctx, snapshot);
		return;
	}
	compacting = true;
	ctx.compact({
		onComplete: () => {
			compacting = false;
		},
		onError: (error) => {
			compacting = false;
			if (ctx.hasUI) ctx.ui.notify(`Pointer compact failed: ${error.message}`, "error");
		},
	});
}

export default function (pi: ExtensionAPI) {
	pi.on("session_start", () => {
		resetHandoffLaneState();
	});

	pi.on("session_before_compact", async (event, ctx) => {
		const { preparation } = event;
		try {
			const { snapshot, path } = persistFromContext(ctx, {
				fileOps: preparation.fileOps as FileOpsLike,
				previousSummary: preparation.previousSummary,
			});
			const config = loadCompactHandoffConfig();
			if (shouldCancelInPlaceCompact({ preferHandoff: config.preferHandoff })) {
				lastCompactAt = Date.now();
				if (ctx.hasUI) ctx.ui.notify(`Abort in-place compact; handoff lane: ${path}`, "info");
				return { cancel: true };
			}
			const summary = formatPointerSummary(snapshot, resolveLimits({
				kind: snapshot.kind,
				budgetPercent: snapshot.budget_percent,
				contextWindow: ctx.getContextUsage()?.contextWindow,
			}).pointerMaxChars);
			if (ctx.hasUI) ctx.ui.notify(`Compact snapshot: ${path}`, "info");
			return {
				compaction: {
					summary,
					firstKeptEntryId: preparation.firstKeptEntryId,
					tokensBefore: preparation.tokensBefore,
					details: {
						schema: snapshot.schema,
						snapshot_path: path,
						readFiles: snapshot.files_read,
						modifiedFiles: snapshot.files_modified,
					},
				},
			};
		} catch (error) {
			lastSnapshot = undefined;
			const message = error instanceof Error ? error.message : String(error);
			const config = loadCompactHandoffConfig();
			if (shouldCancelInPlaceCompact({ preferHandoff: config.preferHandoff })) {
				if (ctx.hasUI) ctx.ui.notify(`Abort in-place compact after snapshot failure: ${message}`, "warning");
				return { cancel: true };
			}
			if (ctx.hasUI) ctx.ui.notify(`Pointer compact failed, using default: ${message}`, "warning");
			return;
		}
	});

	pi.on("session_compact", (event, ctx) => {
		const config = loadCompactHandoffConfig();
		if (!shouldAutoContinue({ autoContinue: config.autoContinue })) return;
		const snapshot = loadPersistedSnapshot(ctx);
		if (!snapshot) {
			if (ctx.hasUI) ctx.ui.notify("Compact continue skipped: no snapshot on disk", "warning");
			return;
		}
		lastCompactAt = Date.now();
		persistPrep(ctx, snapshot, { phase: "compacted-triage" });
		if (config.preferHandoff) {
			void preferHandoffOrContinue(pi, ctx, snapshot, { willRetry: event.willRetry });
			return;
		}
		void runHandoffLane(pi, ctx, snapshot, {
			compactedInsteadOfHandoff: true,
			willRetry: event.willRetry,
		});
		injectContinue(pi, ctx, snapshot, { willRetry: event.willRetry });
	});

	pi.on("session_compact_failed", (event, ctx) => {
		const config = loadCompactHandoffConfig();
		const snapshot = loadPersistedSnapshot(ctx);
		if (!snapshot) return;
		if (handoffQueued) return;
		if (event.aborted && preferHandoffAfterCompact({ preferHandoff: config.preferHandoff, aborted: true })) {
			void preferHandoffOrContinue(pi, ctx, snapshot, { willRetry: false });
			return;
		}
		if (!shouldAutoContinue({ autoContinue: config.autoContinue })) return;
		if (config.preferHandoff) {
			void preferHandoffOrContinue(pi, ctx, snapshot, { willRetry: event.willRetry });
			return;
		}
		injectContinue(pi, ctx, snapshot, { willRetry: event.willRetry });
	});

	pi.on("turn_end", (_event, ctx) => {
		void maybeHandoffLane(pi, ctx);
	});

	pi.registerCommand("snapshot", {
		description: "Write a pointer compact snapshot. --type implementation|monitoring|planning --budget 5",
		handler: async (args, ctx) => {
			try {
				const parsed = parseHandoffArgs(args);
				const { path, snapshot } = persistFromContext(ctx, {
					goal: parsed.goal,
					kind: parsed.kind,
					budgetPercent: parsed.budgetPercent,
				});
				const config = loadCompactHandoffConfig();
				const pointer = formatPointerSummary(
					snapshot,
					resolveLimits({
						config,
						kind: snapshot.kind,
						budgetPercent: snapshot.budget_percent,
						contextWindow: ctx.getContextUsage()?.contextWindow,
					}).pointerMaxChars,
				);
				if (ctx.hasUI) {
					ctx.ui.notify(`Snapshot: ${path} (${snapshot.kind}, ${snapshot.budget_percent}%)`, "info");
					ctx.ui.setEditorText(pointer);
				}
			} catch (error) {
				const message = error instanceof Error ? error.message : String(error);
				ctx.ui.notify(`Snapshot failed: ${message}`, "error");
			}
		},
	});
}
