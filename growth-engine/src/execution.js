const now = () => new Date().toISOString();

export function buildExecution(approval = {}) {
  if (!approval.id || approval.status !== 'approved') throw new Error('approved_action_required');
  return {
    id: crypto.randomUUID(),
    approvalId: approval.id,
    brand: approval.brand,
    kind: approval.kind,
    task: approval.task,
    channel: approval.channel || null,
    reviewedContent: String(approval.note || '').trim(),
    status: 'queued',
    createdAt: now(),
    attempts: 0,
  };
}

export async function executeApprovedAction(execution, approval, env = {}) {
  if (!execution || !approval || execution.approvalId !== approval.id) throw new Error('execution_mismatch');
  const webhook = approval.kind === 'publish' ? env.PUBLISH_WEBHOOK_URL : approval.kind === 'sendExternalMessage' ? env.OUTREACH_WEBHOOK_URL : null;
  if (!webhook) return { ...execution, status: 'blocked', blockedReason: 'channel_not_configured', updatedAt: now() };
  const message = String(approval.note || execution.reviewedContent || '').trim();
  if (!message) return { ...execution, status: 'blocked', blockedReason: 'reviewed_content_required', updatedAt: now() };
  if (approval.kind === 'sendExternalMessage' && !approval.recipient) return { ...execution, status: 'blocked', blockedReason: 'verified_recipient_required', updatedAt: now() };
  try {
    const response = await fetch(webhook, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(env.CHANNEL_WEBHOOK_TOKEN ? { Authorization: `Bearer ${env.CHANNEL_WEBHOOK_TOKEN}` } : {}) },
      body: JSON.stringify({
        approvalId: approval.id,
        brand: approval.brand,
        kind: approval.kind,
        task: approval.task,
        channel: approval.channel || null,
        rationale: approval.rationale || null,
        approvedAt: approval.decidedAt || null,
        message,
        recipient: approval.recipient || null,
        subject: approval.subject || null,
      }),
    });
    const detail = await response.json().catch(() => ({}));
    if (!response.ok) return { ...execution, status: 'failed', attempts: Number(execution.attempts || 0) + 1, lastHttpStatus: response.status, lastError: detail.error || `http_${response.status}`, updatedAt: now() };
    return { ...execution, reviewedContent: message, status: 'executed', attempts: Number(execution.attempts || 0) + 1, executedAt: now(), updatedAt: now(), result: detail };
  } catch (error) {
    return { ...execution, status: 'failed', attempts: Number(execution.attempts || 0) + 1, lastError: error?.message || String(error), updatedAt: now() };
  }
}

export async function deliverNotification(notification, env = {}) {
  if (!env.NOTIFICATION_WEBHOOK_URL) return { delivered: false, reason: 'notification_channel_not_configured' };
  try {
    const response = await fetch(env.NOTIFICATION_WEBHOOK_URL, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(env.NOTIFICATION_WEBHOOK_TOKEN ? { Authorization: `Bearer ${env.NOTIFICATION_WEBHOOK_TOKEN}` } : {}) }, body: JSON.stringify(notification) });
    return response.ok ? { delivered: true, deliveredAt: now() } : { delivered: false, reason: `http_${response.status}` };
  } catch (error) {
    return { delivered: false, reason: error?.message || 'notification_network_error' };
  }
}
