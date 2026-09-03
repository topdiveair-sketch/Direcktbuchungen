export const BRANDS = {
  zuhause_am_bach: {
    objective: 'Profitable direct bookings for the available double room',
    primaryMetric: 'confirmed_direct_booking',
    autonomyMode: 'zero_cost',
    approvalRequired: ['spend_money', 'change_booking_logic', 'commit_contract'],
  },
  windis: {
    objective: 'Grow the regional family brand, book demand and qualified partnerships',
    primaryMetric: 'qualified_conversion',
    autonomyMode: 'approval_first',
    approvalRequired: ['publish', 'send_external_message', 'spend_money'],
  },
};

export const MAX_AUTONOMY = {
  research: true,
  analyze: true,
  draft: true,
  proposeExperiment: true,
  publish: true,
  sendExternalMessage: true,
  spendMoney: false,
};

export const ZERO_COST_GUARD = {
  maxEstimatedCostEur: 0,
  allowedPublishChannels: ['owned_web'],
  allowedOutreachChannels: ['partner_outreach'],
  requireVerifiedBusinessRecipient: true,
};
