import { test } from 'node:test';
import assert from 'node:assert/strict';
import { argumentsFor, summarize } from './toolcall-probe.mjs';
const marker = 'synthetic-fixture';
function events(id = 'cursor-pi-bridge-run-test-tool-1') {
  return [
    {type: 'tool_execution_start', toolCallId:id, toolName:'read'},
    {type: 'tool_execution_end', toolCallId:id, toolName:'read', isError:false, result:{content:[{type:'text',text:marker}]}},
    {type: 'message_end', message:{role:'assistant',stopReason:'stop',content:[{type:'text',text:marker}]}},
    {type:'agent_end'}
  ];
}
test('requires real paired bridge execution and observed fixture', () => {
  assert.equal(summarize(events(), marker, true).status, 'passed');
  assert.equal(summarize(events('cursor-replay-read-1'), marker, true).status, 'failed');
  assert.equal(summarize(events('native-id'), marker, true).status, 'failed');
  assert.equal(summarize(events().slice(2), marker, true).status, 'failed');
});
test('rejects duplicates, errors, missing completion, wrong marker', () => {
  const rows = events();
  assert.equal(summarize([rows[0], ...rows], marker).status, 'failed');
  assert.equal(summarize([...rows, rows[1]], marker).status, 'failed');
  assert.equal(summarize(rows.slice(0, -1), marker).status, 'failed');
  assert.equal(summarize(rows, 'different').status, 'failed');
  rows[1].isError = true;
  assert.equal(summarize(rows, marker).status, 'failed');
});
test('does not emit raw sensitive content or errors', () => {
  const rows = events();
  rows[2].message.errorMessage = 'network API_KEY=secret-fixture';
  rows[2].message.stopReason = 'error';
  const result = summarize(rows, marker);
  assert.equal(result.status, 'failed');
  assert.equal(JSON.stringify(result).includes('secret-fixture'), false);
});
test('isolates discovery and never bypasses project trust', () => {
  const args = argumentsFor({pi:'pi', extension:'/fixture', model:'cursor/grok-4.6:fast', bridge:true});
  assert.ok(args.includes('--no-approve'));
  assert.ok(args.includes('--no-context-files'));
  assert.ok(args.includes('--no-extensions'));
  assert.ok(!args.includes('--approve'));
});
