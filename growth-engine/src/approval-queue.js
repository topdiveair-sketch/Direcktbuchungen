export class ApprovalQueue {
  constructor(items = []) {
    this.items = [...items];
  }

  enqueue(action) {
    const item = {
      id: crypto.randomUUID(),
      createdAt: new Date().toISOString(),
      status: 'pending',
      ...action,
    };
    this.items.push(item);
    return item;
  }

  pending(brand = null) {
    return this.items.filter((item) => item.status === 'pending' && (!brand || item.brand === brand));
  }

  decide(id, decision, note = '') {
    if (!['approved', 'rejected'].includes(decision)) throw new Error('Invalid decision');
    const item = this.items.find((entry) => entry.id === id);
    if (!item) throw new Error('Approval item not found');
    item.status = decision;
    item.decidedAt = new Date().toISOString();
    item.note = note;
    return item;
  }
}
