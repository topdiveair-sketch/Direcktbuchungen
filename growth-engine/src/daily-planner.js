import { GrowthOrchestrator } from './orchestrator.js';
import { ApprovalQueue } from './approval-queue.js';

export class DailyPlanner {
  constructor({ orchestrator = new GrowthOrchestrator(), approvals = new ApprovalQueue() } = {}) {
    this.orchestrator = orchestrator;
    this.approvals = approvals;
  }

  buildDay({ zuhauseSignals = {}, windisSignals = {} } = {}) {
    const generatedAt = new Date().toISOString();
    const plans = {
      zuhause_am_bach: this.orchestrator.plan('zuhause_am_bach', zuhauseSignals),
      windis: this.orchestrator.plan('windis', windisSignals),
    };

    const execution = [];
    for (const [brand, actions] of Object.entries(plans)) {
      for (const action of actions) {
        const guard = this.orchestrator.guard(action);
        if (guard.allowed && action.autonomous) {
          execution.push({ brand, ...action, status: 'ready' });
        } else {
          const approval = this.approvals.enqueue({ brand, ...action, reason: guard.reason || 'approval_required' });
          execution.push({ brand, ...action, status: 'approval_pending', approvalId: approval.id });
        }
      }
    }

    return {
      generatedAt,
      plans,
      execution,
      approvalsPending: this.approvals.pending(),
    };
  }
}
