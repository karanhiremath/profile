/** Bounded recovery for the observed empty Cursor error immediately after a successful tool.
 * This signature is evidence of a failed continuation, not proof of its SDK root cause.
 */
export const CURSOR_ABORT_RETRY_PROMPT =
  "The Cursor continuation failed after a completed tool. Continue from the recorded result. Do not repeat completed tools. If a mutation outcome is uncertain, stop and ask the user.";
export const CURSOR_ABORT_RETRY_MAX_LATENCY_MS = 8000;
export type CursorAbortRetryMessage = {
  role?: string; stopReason?: string; errorMessage?: string; provider?: string; api?: string;
  timestamp?: number; usage?: {totalTokens?: number}; content?: unknown; isError?: boolean;
};
export function isCursorAbortError(input: CursorAbortRetryMessage): boolean {
  // Never reinterpret Pi's explicit aborted/cancelled stop reason as retryable.
  return input.stopReason === "error" && /^(?:This operation was aborted|Operation (?:was )?aborted)\.?$/i.test(input.errorMessage?.trim() || "");
}
export function isCursorProvider(input: CursorAbortRetryMessage): boolean {
  return input.provider === "cursor" || input.api === "cursor-sdk";
}
function hasContent(content: unknown): boolean {
  if (!Array.isArray(content)) return content !== undefined && content !== "";
  return content.some(part => {
    if (!part || typeof part !== "object") return true;
    const item = part as {type?: string; text?: string; thinking?: string};
    return item.type === "toolCall" || Boolean(item.text?.trim() || item.thinking?.trim()) || !["text", "thinking"].includes(item.type || "");
  });
}
export function inspectCursorAbortRetry(messages: readonly CursorAbortRetryMessage[], extras: {
  lastToolSucceeded?: boolean; lastSuccessfulToolAt?: number; alreadyRetried?: boolean;
  signalAborted?: boolean; now?: number;
} = {}): {shouldRetry: boolean; abortLatencyMs?: number} {
  const last = messages.at(-1);
  if (!last || last.role !== "assistant" || !isCursorProvider(last) || !isCursorAbortError(last) ||
      extras.alreadyRetried || extras.signalAborted || hasContent(last.content) || last.usage?.totalTokens !== 0) return {shouldRetry:false};
  let toolSucceeded = extras.lastToolSucceeded === true;
  let toolAt = extras.lastSuccessfulToolAt;
  for (const message of messages.slice(0,-1)) {
    if (message.role === "toolResult") { toolSucceeded = message.isError !== true; toolAt = message.timestamp; }
  }
  const abortAt = last.timestamp ?? extras.now;
  if (!toolSucceeded || !Number.isFinite(toolAt) || !Number.isFinite(abortAt)) return {shouldRetry:false};
  const latency = abortAt! - toolAt!;
  return {shouldRetry:latency >= 0 && latency <= CURSOR_ABORT_RETRY_MAX_LATENCY_MS, abortLatencyMs:latency};
}
