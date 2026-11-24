/**
 * Brief-style /handoff: the model writes the new-session prompt from the
 * conversation. Pure helpers only (no pi imports) so the offline suite runs.
 *
 * A reply is rejected only when it is a stub: empty, very short, or an
 * unstructured promise to write the prompt later. Heading names are a
 * preference, never a validity test. Treating a heading mismatch as a stub
 * discarded complete multi-thousand-character prompts twice in a row and
 * failed the command with "returned a stub instead of a prompt".
 */

export const BRIEF_HEADINGS = [
	"Files to read first",
	"Current state",
	"Decisions",
	"Validation already run",
	"Blockers",
	"Do not",
	"Task",
] as const;

const HEADING_BLOCK = BRIEF_HEADINGS.map((heading) => `## ${heading}`).join("\n");

export const BRIEF_SYSTEM_PROMPT = `You are a context transfer assistant. You do NOT continue the conversation. You do NOT act as the next agent. You do NOT take tools. You ONLY write the prompt that will be pasted into a new session.

Do NOT continue the conversation. Do NOT respond to questions in the history. Do NOT say you will draft, measure, gather, inspect, or write a follow-up later. Output the finished prompt now.

The entire reply MUST be the prompt, using these headings exactly:

${HEADING_BLOCK}

Rules:
- Address the next agent in second person ("Continue…", "Read…", "Do not resubmit…").
- Be self-contained: paths, branch/worktree, case files, live job IDs, pins, and exact next steps.
- Be concise. Omit narrative and internal reasoning.
- No preamble such as "Here's the prompt" or "I'll draft".
- Never write a one-line promise. ## Task must contain the actual work, not a plan to write a prompt.`;

export const BRIEF_CONVERSATION_HEAD_CHARS = 20_000;
export const BRIEF_CONVERSATION_TAIL_CHARS = 60_000;
/** Below this, a reply without the expected headings is a stub. */
export const BRIEF_MIN_CHARS = 400;
/** A promise to write the prompt later only counts when it opens the reply. */
const META_OPENING_CHARS = 320;

const META_PROMISE_RE =
	/\b(i['’]?ll|i will|let me|i am going to|i'm going to)\b.{0,80}\b(draft|write|prepare|create|generate)\b.{0,80}\b(prompt|handoff|follow-?up)\b/i;

export function stripAssistantThinking(text: string): string {
	return text.replace(/\[Assistant thinking\]:[\s\S]*?(?=\n\n\[|\n*$)/g, "").trim();
}

export function capConversationText(
	text: string,
	headChars = BRIEF_CONVERSATION_HEAD_CHARS,
	tailChars = BRIEF_CONVERSATION_TAIL_CHARS,
): string {
	const max = headChars + tailChars;
	if (text.length <= max) return text;
	const omitted = text.length - max;
	return `${text.slice(0, headChars)}\n\n[... ${omitted} characters omitted ...]\n\n${text.slice(-tailChars)}`;
}

export function prepareConversationText(raw: string): string {
	return capConversationText(stripAssistantThinking(raw));
}

export type BriefRejection = "empty" | "too-short" | "meta-promise";

export type BriefVerdict =
	| { ok: true; conforms: boolean }
	| { ok: false; reason: BriefRejection };

/** True when the reply uses the requested first and last headings. */
export function conformsToBriefFormat(text: string): boolean {
	return /^##\s+Files to read first\b/m.test(text) && /^##\s+Task\b/m.test(text);
}

function isStructured(text: string): boolean {
	const headings = text.match(/^#{1,6}\s+\S/gm)?.length ?? 0;
	if (headings >= 2) return true;
	const bullets = text.match(/^\s*(?:[-*+]|\d+[.)])\s+\S/gm)?.length ?? 0;
	return bullets >= 5;
}

/**
 * Decide whether a generated reply is usable as a handoff prompt.
 * The operator still reviews it in the editor, so only stubs are rejected.
 */
export function classifyBrief(text: string): BriefVerdict {
	const trimmed = text.trim();
	if (!trimmed) return { ok: false, reason: "empty" };
	if (conformsToBriefFormat(trimmed)) return { ok: true, conforms: true };
	if (trimmed.length < BRIEF_MIN_CHARS) return { ok: false, reason: "too-short" };
	if (!isStructured(trimmed) && META_PROMISE_RE.test(trimmed.slice(0, META_OPENING_CHARS))) {
		return { ok: false, reason: "meta-promise" };
	}
	return { ok: true, conforms: false };
}

const REJECTION_TEXT: Record<BriefRejection, string> = {
	empty: "it was empty",
	"too-short": "it was too short to be a usable prompt",
	"meta-promise": "it promised to write the prompt later instead of being the prompt",
};

export function buildBriefRequestText(conversationText: string, goal: string, rejected?: BriefRejection): string {
	const retryBlock = rejected
		? `\n\nPREVIOUS OUTPUT WAS REJECTED because ${REJECTION_TEXT[rejected]}. Output the full prompt now.`
		: "";
	return `Write the new-session prompt now. Do not continue the conversation below as the assistant.

## Conversation History

${conversationText}

## User's Goal for New Session

${goal}

## Output format

Reply with the finished prompt only, starting with "## ${BRIEF_HEADINGS[0]}". Use exactly these headings, in this order:

${HEADING_BLOCK}${retryBlock}`;
}

export type BriefAttempt = { text: string; stopReason?: string; errorMessage?: string };

export type BriefResult =
	| { status: "ok"; text: string; attempts: number; conforms: boolean }
	| { status: "aborted" }
	| { status: "failed"; reason: string; attempts: number };

function describeFailure(attempt: BriefAttempt, reason: BriefRejection): string {
	if (reason === "empty") {
		const detail = [attempt.stopReason && `stopReason=${attempt.stopReason}`, attempt.errorMessage]
			.filter(Boolean)
			.join(": ");
		return detail ? `no text (${detail})` : "no text";
	}
	const firstLine = attempt.text.trim().split("\n")[0].slice(0, 160);
	return `stub (${reason}, ${attempt.text.trim().length} chars): ${firstLine}`;
}

/**
 * Run up to two generations. `generateOnce` returns null when the operator
 * aborts. The retry happens only for a stub, never for heading names.
 */
export async function generateBrief(
	generateOnce: (rejected?: BriefRejection) => Promise<BriefAttempt | null>,
): Promise<BriefResult> {
	let rejected: BriefRejection | undefined;
	let last: BriefAttempt = { text: "" };
	for (let attempt = 1; attempt <= 2; attempt++) {
		const result = await generateOnce(rejected);
		if (result === null) return { status: "aborted" };
		last = result;
		const verdict = classifyBrief(result.text);
		if (verdict.ok) {
			return { status: "ok", text: result.text.trim(), attempts: attempt, conforms: verdict.conforms };
		}
		rejected = verdict.reason;
	}
	return { status: "failed", reason: describeFailure(last, rejected ?? "empty"), attempts: 2 };
}
