import type { ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
	HANDOFF_PREP_SCHEMA,
	handoffSwitchPresentation,
	keepLiveHandoffChild,
	ownerSessionIds,
	readHandoffPrepAny,
	sessionSteerMode,
	writeHandoffPrepAliases,
	type HandoffPrepState,
} from "./compact-snapshot.ts";

/** Capture owner identity before replacement; the returned writer never touches ctx. */
export function captureHandoffPrepWriter(
	ctx: ExtensionContext,
	snapshotPath: string,
): (patch: Partial<HandoffPrepState>) => void {
	const sourceFile = ctx.sessionManager.getSessionFile();
	const ids = ownerSessionIds({
		sessionFile: sourceFile,
		sessionId: ctx.sessionManager.getSessionId?.(),
		env: process.env,
	});
	return (patch) => {
		const previous = readHandoffPrepAny(ids.aliases);
		writeHandoffPrepAliases({
			...previous,
			...patch,
			...keepLiveHandoffChild(previous, sourceFile),
			schema: HANDOFF_PREP_SCHEMA,
			source_session_id: ids.canonical,
			source_session_file: sourceFile,
			snapshot_path: snapshotPath,
		}, ids.aliases);
	};
}

/** All session-bound work after replacement belongs to withSession's fresh context. */
export async function replaceHandoffSession(
	ctx: ExtensionCommandContext,
	options: {
		childFile?: string;
		prompt: string;
		snapshotPath: string;
		promptAlreadySent: boolean;
		onSwitched: (promptDelivered: boolean) => void;
	},
): Promise<boolean> {
	const hasUI = ctx.hasUI;
	const mode = sessionSteerMode({ hasUI, mode: ctx.mode });
	let promptDelivered = options.promptAlreadySent;
	const withSession: NonNullable<Parameters<ExtensionCommandContext["newSession"]>[0]>["withSession"] =
		async (replacementCtx) => {
			try {
				const presentation = handoffSwitchPresentation({
					mode,
					hasUI,
					replacementHasUI: replacementCtx.hasUI,
					prepared: Boolean(options.childFile),
					promptAlreadySent: promptDelivered,
				});
				if (presentation.replacement.notify) {
					replacementCtx.ui.notify(`Handoff switch. Snapshot: ${options.snapshotPath}`, "info");
				}
				if (presentation.replacement.setEditorText) {
					replacementCtx.ui.setEditorText(options.prompt);
					promptDelivered = true;
				}
				if (presentation.sendUserMessage) {
					await replacementCtx.sendUserMessage(options.prompt, { deliverAs: presentation.sendDeliverAs });
					promptDelivered = true;
				}
			} finally {
				// Even failed presentation must record the actual switch, not trigger an owner fallback.
				options.onSwitched(promptDelivered);
			}
		};
	// A replacement may invalidate ctx even if initialization fails before withSession.
	// Let failures reach the harness; never attempt an owner-context notification/fallback.
	const result = options.childFile
		? await ctx.switchSession(options.childFile, { withSession })
		: await ctx.newSession({ withSession });
	return !result.cancelled;
}
