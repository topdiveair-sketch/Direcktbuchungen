export const BRANDS = {
  zuhause_am_bach: {
    objective: 'Profitable direct bookings for the available double room',
    primaryMetric: 'confirmed_direct_booking',
    approvalRequired: ['publish', 'send_external_message', 'spend_money'],
  },
  windis: {
    objective: 'Grow the regional family brand, book demand and qualified partnerships',
    primaryMetric: 'qualified_conversion',
    approvalRequired: ['publish', 'send_external_message', 'spend_money'],
  },
};

export const MAX_AUTONOMY = {
  research: true,
  analyze: true,
  draft: true,
  proposeExperiment: true,
  publish: false,
  sendExternalMessage: false,
  spendMoney: false,
};
