import {test} from 'node:test';
import assert from 'node:assert/strict';
import retry from '../../config/pi/extensions/cursor-abort-retry.ts';
import {inspectCursorAbortRetry} from '../../config/pi/extensions/lib/cursor-abort-retry.ts';
const tool={role:'toolResult',isError:false,timestamp:1000};
const failure={role:'assistant',provider:'cursor',stopReason:'error',errorMessage:'This operation was aborted',timestamp:1002,usage:{totalTokens:0},content:[]};
test('observed Mini signature: completed tool, 2ms, zero tokens, error not caller abort',()=>{
  assert.equal(inspectCursorAbortRetry([tool,failure]).shouldRetry,true);
  for(const text of ['Operation aborted','Operation was aborted','This operation was aborted.'])
    assert.equal(inspectCursorAbortRetry([tool,{...failure,errorMessage:text}]).shouldRetry,true);
});
test('fail closed on caller cancellation, ambiguous evidence, content, or stale tools',()=>{
  for(const patch of [{stopReason:'aborted'},{errorMessage:'Cancelled: prompt interrupted.'},
    {usage:undefined},{usage:{totalTokens:1}},{content:[{type:'toolCall',id:'mutation'}]},
    {content:[{type:'text',text:'partial'}]},{timestamp:999},{timestamp:9001},{provider:'openai-codex'}])
    assert.equal(inspectCursorAbortRetry([tool,{...failure,...patch}]).shouldRetry,false);
  assert.equal(inspectCursorAbortRetry([failure]).shouldRetry,false);
  assert.equal(inspectCursorAbortRetry([{...tool,isError:true},failure]).shouldRetry,false);
  assert.equal(inspectCursorAbortRetry([tool,failure],{signalAborted:true}).shouldRetry,false);
  assert.equal(inspectCursorAbortRetry([tool,failure],{alreadyRetried:true}).shouldRetry,false);
  assert.equal(inspectCursorAbortRetry([tool,failure,{role:'assistant',stopReason:'stop'}]).shouldRetry,false);
});
test('extension queues once, respects pending messages and resets on real user input',()=>{
  const hooks=new Map(),sent=[];
  retry({on:(name,handler)=>hooks.set(name,handler),sendMessage:(...args)=>sent.push(args)});
  const ctx={hasUI:false,hasPendingMessages:()=>false};
  const event={messages:[tool,failure]};
  hooks.get('agent_end')(event,{...ctx,hasPendingMessages:()=>true});
  assert.equal(sent.length,0);
  hooks.get('agent_end')(event,ctx);
  hooks.get('input')({source:'extension'});
  hooks.get('agent_end')(event,ctx);
  assert.equal(sent.length,1);
  assert.equal(sent[0][1].deliverAs,'followUp');
  assert.equal(sent[0][0].customType,'cursor-abort-retry');
  hooks.get('input')({source:'interactive'});
  hooks.get('agent_end')(event,{...ctx,signal:{aborted:true}});
  assert.equal(sent.length,1);
  hooks.get('agent_end')(event,ctx);
  assert.equal(sent.length,2);
});
