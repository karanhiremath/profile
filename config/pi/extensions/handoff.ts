/**
 * Handoff extension - transfer context to a new focused session in the same TUI.
 *
 * Usage:
 *   /handoff continue with the next validation step
 *   /handoff-bg continue autonomously from the handoff
 *
 * Flow (/handoff):
 *   1. Generate a focused handoff prompt from the current branch.
 *   2. Let the user review/edit it.
 *   3. Ask for explicit approval.
 *   4. Switch to a new session in the same TUI and place the prompt in the editor.
 *
 * Flow (/handoff-bg):
 *   1. Let the user review/edit the handoff generator prompt.
 *   2. Generate a focused handoff prompt from the current branch.
 *   3. Let the user review/edit the final prompt.
 *   4. Ask for explicit approval.
 *   5. Switch to a new child session and submit the prompt immediately.
 */

import type { AgentMessage } from "@earendil-works/pi-agent-core";
import { complete, type Message } from "@earendil-works/pi-ai/compat";
import type { ExtensionAPI, ExtensionCommandContext, SessionEntry } from "@earendil-works/pi-coding-agent";
import { BorderedLoader, convertToLlm, serializeConversation } from "@earendil-works/pi-coding-agent";

const STANDARD_SYSTEM_PROMPT = `You are a context transfer assistant. Given a conversation history and the user's goal for a new thread, generate a focused prompt that:

1. Summarizes relevant context from the conversation: decisions made, approaches taken, key findings.
2. Lists relevant files discussed or modified.
3. Clearly states the next task based on the user's goal.
4. Is self-contained so the new session can proceed without the old conversation.

Format your response as a prompt the user can send to start the new thread. Be concise but include all necessary context. Do not include a preamble like "Here's the prompt"; output the prompt itself.`;

const BACKGROUND_SYSTEM_PROMPT = `${STANDARD_SYSTEM_PROMPT}

The generated prompt will be submitted immediately in a new child session while the current session is preserved as the parent/background session. Make the prompt operational: include current objective, exact next steps, paths/branches, validation already run, known blockers, and any commands that should or should not be rerun. If there is uncommitted work, make that state explicit. The replacement session should be able to continue without asking for the old chat unless a fact is genuinely unknown.`;

type HandoffMode = "editor" | "background";

function entryToMessage(entry: SessionEntry): AgentMessage | undefined {
	if (entry.type === "message") {
		return entry.message;
	}
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

function buildGenerationRequest(conversationText: string, goal: string): Message {
	return {
		role: "user",
		content: [
			{
				type: "text",
				text: `## Conversation History\n\n${conversationText}\n\n## User's Goal for New Session\n\n${goal}`,
			},
		],
		timestamp: Date.now(),
	};
}

async function generatePrompt(
	ctx: ExtensionCommandContext,
	conversationText: string,
	goal: string,
	systemPrompt: string,
): Promise<string | null> {
	return ctx.ui.custom<string | null>((tui, theme, _kb, done) => {
		const loader = new BorderedLoader(tui, theme, "Generating handoff prompt...");
		loader.onAbort = () => done(null);

		const doGenerate = async () => {
			const auth = await ctx.modelRegistry.getApiKeyAndHeaders(ctx.model!);
			if (!auth.ok || !auth.apiKey) {
				throw new Error(auth.ok ? `No API key for ${ctx.model!.provider}` : auth.error);
			}

			const response = await complete(
				ctx.model!,
				{ systemPrompt, messages: [buildGenerationRequest(conversationText, goal)] },
				{ apiKey: auth.apiKey, headers: auth.headers, env: auth.env, signal: loader.signal },
			);

			if (response.stopReason === "aborted") {
				return null;
			}

			return response.content
				.filter((content): content is { type: "text"; text: string } => content.type === "text")
				.map((content) => content.text)
				.join("\n");
		};

		doGenerate()
			.then(done)
			.catch((error) => {
				console.error("Handoff generation failed:", error);
				done(null);
			});

		return loader;
	});
}

async function runHandoff(args: string, ctx: ExtensionCommandContext, mode: HandoffMode): Promise<void> {
	const command = mode === "background" ? "/handoff-bg" : "/handoff";

	if (ctx.mode !== "tui") {
		ctx.ui.notify(`${command} requires interactive TUI mode`, "error");
		return;
	}

	if (!ctx.model) {
		ctx.ui.notify("No model selected", "error");
		return;
	}

	const goal = args.trim();
	if (!goal) {
		ctx.ui.notify(`Usage: ${command} <goal for the new session>`, "error");
		return;
	}

	const messages = getHandoffMessages(ctx.sessionManager.getBranch());
	if (messages.length === 0) {
		ctx.ui.notify("No conversation to hand off", "error");
		return;
	}

	let systemPrompt = mode === "background" ? BACKGROUND_SYSTEM_PROMPT : STANDARD_SYSTEM_PROMPT;
	if (mode === "background") {
		const editedSystemPrompt = await ctx.ui.editor("Customize handoff generator prompt", systemPrompt);
		if (editedSystemPrompt === undefined) {
			ctx.ui.notify("Handoff cancelled", "info");
			return;
		}
		systemPrompt = editedSystemPrompt;
	}

	const llmMessages = convertToLlm(messages);
	const conversationText = serializeConversation(llmMessages);
	const currentSessionFile = ctx.sessionManager.getSessionFile();
	const generatedPrompt = await generatePrompt(ctx, conversationText, goal, systemPrompt);

	if (generatedPrompt === null) {
		ctx.ui.notify("Handoff cancelled", "info");
		return;
	}

	const editedPrompt = await ctx.ui.editor("Review handoff prompt", generatedPrompt);
	if (editedPrompt === undefined) {
		ctx.ui.notify("Handoff cancelled", "info");
		return;
	}

	if (mode === "editor") {
		const approved = await ctx.ui.confirm(
			"Switch to new session?",
			"This will keep the same TUI process, create a new Pi session linked to the current one, and place the handoff prompt in the editor.",
		);

		if (!approved) {
			ctx.ui.setEditorText(editedPrompt);
			ctx.ui.notify("Kept handoff prompt in current editor; no session switch.", "info");
			return;
		}

		const newSessionResult = await ctx.newSession({
			parentSession: currentSessionFile,
			withSession: async (replacementCtx) => {
				replacementCtx.ui.setEditorText(editedPrompt);
				replacementCtx.ui.notify("Switched to new handoff session. Submit when ready.", "info");
			},
		});

		if (newSessionResult.cancelled) {
			ctx.ui.notify("New session cancelled", "info");
		}
		return;
	}

	const approved = await ctx.ui.confirm(
		"Start background handoff session?",
		"This preserves the current session as the parent/background session, creates a new child session, and submits the reviewed handoff prompt immediately.",
	);

	if (!approved) {
		ctx.ui.setEditorText(editedPrompt);
		ctx.ui.notify("Kept handoff prompt in current editor; no session switch.", "info");
		return;
	}

	const newSessionResult = await ctx.newSession({
		parentSession: currentSessionFile,
		withSession: async (replacementCtx) => {
			replacementCtx.ui.notify("Started handoff session. Submitting prompt...", "info");
			await replacementCtx.sendUserMessage(editedPrompt);
		},
	});

	if (newSessionResult.cancelled) {
		ctx.ui.notify("New session cancelled", "info");
	}
}

export default function (pi: ExtensionAPI) {
	pi.registerCommand("handoff", {
		description: "Generate a handoff and switch to a new focused session after approval",
		handler: async (args, ctx) => {
			await runHandoff(args, ctx, "editor");
		},
	});

	pi.registerCommand("handoff-bg", {
		description: "Generate a custom handoff, switch to a child session, and submit it immediately",
		handler: async (args, ctx) => {
			await runHandoff(args, ctx, "background");
		},
	});
}
