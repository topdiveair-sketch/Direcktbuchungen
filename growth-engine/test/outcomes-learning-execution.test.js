import test from 'node:test';
import assert from 'node:assert/strict';
import { buildOutcome, summarizeOutcomes } from '../src/outcomes.js';
import { buildLearningProfile, learnedProbability } from '../src/learning.js';
import { buildExecution, executeApprovedAction } from '../src/execution.js';

test('records actual contribution and portfolio economics', () => {
  const approval={id:'a1',status:'approved',brand:'zuhause_am_bach',kind:'publish',task:'campaign',expectedRevenue:300,expectedCost:50,successProbability:.5};
  const outcome=buildOutcome({approval,actualRevenue:240,actualCost:40});
  assert.equal(outcome.actualContribution,200);
  assert.equal(outcome.varianceToExpected,100);
  assert.equal(summarizeOutcomes([outcome]).totalContribution,200);
});

test('learning adjusts probability only from measured outcomes', () => {
  const outcomes=Array.from({length:4},(_,i)=>({brand:'windis',kind:'sendExternalMessage',channel:'default',actualContribution:i<3?50:-10}));
  const profile=buildLearningProfile(outcomes);
  const probability=learnedProbability({brand:'windis',kind:'sendExternalMessage',successProbability:.5},profile);
  assert.ok(probability>.5);
  assert.ok(probability<.95);
});

test('approved action is safely blocked when execution channel is not configured', async () => {
  const approval={id:'a2',status:'approved',brand:'windis',kind:'sendExternalMessage',task:'outreach'};
  const queued=buildExecution(approval);
  const result=await executeApprovedAction(queued,approval,{});
  assert.equal(result.status,'blocked');
  assert.equal(result.blockedReason,'channel_not_configured');
});
