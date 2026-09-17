import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { CURSOR_ABORT_RETRY_PROMPT, inspectCursorAbortRetry } from "./lib/cursor-abort-retry.ts";

/** One continuation per user request; never retry caller cancellation or replay a tool. */
export default function cursorAbortRetry(pi: ExtensionAPI): void {
  let lastToolSucceeded = false;
  let lastSuccessfulToolAt: number | undefined;
  let retried = false;
  const reset = () => {lastToolSucceeded=false; lastSuccessfulToolAt=undefined; retried=false;};
  pi.on("session_start", reset);
  pi.on("session_shutdown", reset);
  pi.on("input", event => {if (event.source !== "extension") reset();});
  pi.on("tool_result", (event, ctx) => {
    lastToolSucceeded = event.isError !== true && ctx.signal?.aborted !== true;
    lastSuccessfulToolAt = lastToolSucceeded ? Date.now() : undefined;
  });
  pi.on("agent_end", (event, ctx) => {
    if (ctx.hasPendingMessages()) return;
    const inspected = inspectCursorAbortRetry(event.messages, {
      lastToolSucceeded, lastSuccessfulToolAt, alreadyRetried:retried,
      signalAborted:ctx.signal?.aborted, now:Date.now(),
    });
    if (!inspected.shouldRetry) return;
    // Mark before queueing; even a failed queue cannot start a retry loop.
    retried = true;
    try {
      pi.sendMessage({customType:"cursor-abort-retry",content:CURSOR_ABORT_RETRY_PROMPT,display:true},
        {deliverAs:"followUp",triggerTurn:true});
      if (ctx.hasUI) ctx.ui.notify("Continuing once after an empty Cursor post-tool error", "info");
    } catch {
      if (ctx.hasUI) ctx.ui.notify("Cursor continuation could not be queued; retry manually", "warning");
    }
  });
}
