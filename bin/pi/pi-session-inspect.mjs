#!/usr/bin/env node
// Structural Pi session inspection. No prompts, arguments, results, or raw errors leave stdout.
import { readFileSync } from 'node:fs';

if (process.argv.includes('--help') || process.argv.length < 3) {
  process.stdout.write('Usage: pi-session-inspect.mjs <session.jsonl>...\n');
  process.exit(0);
}
for (const file of process.argv.slice(2)) {
  const rows = [];
  let invalid = 0;
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    if (!line.trim()) continue;
    let record;
    try { record = JSON.parse(line); } catch { invalid++; continue; }
    const message = record.message;
    if (!message || !['assistant', 'toolResult'].includes(message.role)) continue;
    const content = Array.isArray(message.content) ? message.content : [];
    const text = content.filter(b => b.type === 'text').map(b => b.text).join('\n');
    const error = String(message.errorMessage || '');
    const toolCalls = content.filter(b => b.type === 'toolCall');
    rows.push({
      role: message.role,
      provider: message.provider,
      model: message.model,
      stopReason: message.stopReason,
      isError: message.isError === true,
      toolCalls: toolCalls.map(b => ({ name: b.name, kind: String(b.id).startsWith('cursor-replay-') ? 'replay' : 'execution' })),
      textChars: text.length,
      echo: /Tool call \(|<tool_call>|pi__\w+\s*\(/.test(text),
      errorClass: error === 'Cancelled: prompt interrupted.' ? 'caller_interrupted' : error === 'Cancelled: Cursor SDK run was cancelled.' ? 'sdk_cancelled' : /invalid_grant|refresh token/i.test(error) ? 'oauth_refresh' : /Tool .*not found/i.test(error + (message.isError ? text : '')) ? 'missing_tool' : /pipeline|abort/i.test(error) ? 'pipeline_or_abort' : /timeout|ETIMEDOUT/i.test(error) ? 'timeout' : error ? 'other' : null,
    });
  }
  process.stdout.write(JSON.stringify({schema:'harness.pi-session.v1',invalid,rows:rows.slice(-20)})+'\n');
}
