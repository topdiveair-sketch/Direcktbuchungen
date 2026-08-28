export function windisSignals({ partners = [], kpis = [] } = {}) {
  const open = partners.filter((row) => row.status === 'Offen');
  const priorityA = open.filter((row) => row.priority === 'A');
  const overdue = open.filter((row) => row.targetDate && new Date(`${row.targetDate}T23:59:59Z`) < new Date());
  const qualifiedRecipients = open.filter((row) => row.email && row.emailVerified === true);
  const nextPartner = [...qualifiedRecipients].sort((a,b) => String(a.priority).localeCompare(String(b.priority)) || String(a.targetDate || '').localeCompare(String(b.targetDate || '')))[0] || null;

  return {
    partnerContacts: partners.length,
    openPartnerActions: open.length,
    priorityAOpen: priorityA.length,
    overdueOpen: overdue.length,
    partnerReplies: partners.filter((row) => row.status && row.status !== 'Offen').length,
    qualifiedRecipients: qualifiedRecipients.length,
    nextPartner,
    kpis,
  };
}

// Public-safe planning seed. Contact addresses are deliberately absent until a
// recipient has been verified from an authoritative public source.
export const WINDIS_PARTNER_SEED = [
  { priority: 'A', partner: 'Donau Niederoesterreich Tourismus GmbH / Wachau-Nibelungengau-Kremstal', category: 'Tourismus', approach: 'regionale Familienmarke und Content fuer Familiengaeste', nextStep: 'Kontakt verifizieren und Erstkontakt senden', status: 'Offen', targetDate: '2026-08-20' },
  { priority: 'A', partner: 'Donau Niederoesterreich - Welterbesteig Wachau', category: 'Tourismus / Wandern', approach: 'Familien-Wandertipp mit Buchbezug', nextStep: 'Kontakt verifizieren und Erstkontakt senden', status: 'Offen', targetDate: '2026-08-20' },
  { priority: 'A', partner: 'Thalia Krems - ALEX', category: 'Buchhandel', approach: 'Regionalflaeche fuer Hero-Titel', nextStep: 'Kontakt verifizieren und Erstkontakt senden', status: 'Offen', targetDate: '2026-08-21' },
  { priority: 'A', partner: 'Stadtbuecherei & Mediathek Krems', category: 'Bibliothek', approach: 'regionale Kinderbuchtipps und Lesefoerderung', nextStep: 'Kontakt verifizieren und Erstkontakt senden', status: 'Offen', targetDate: '2026-08-21' },
  { priority: 'A', partner: 'Burgruine Aggstein', category: 'Ausflugsziel', approach: 'Burgshop plus Windis-Raetselkarte oder Entdeckerpass', nextStep: 'Kontakt verifizieren und Erstkontakt senden', status: 'Offen', targetDate: '2026-08-22' },
  { priority: 'B', partner: 'Wachau Info-Center Krems', category: 'Tourismus / Gaesteservice', approach: 'Familien-Tipp fuer Gaeste vor Ort', nextStep: 'Kontakt verifizieren und Erstkontakt senden', status: 'Offen', targetDate: '2026-08-27' },
  { priority: 'B', partner: 'Treffpunkt Bibliothek - Service des Landes NOe', category: 'Bibliotheksnetzwerk', approach: 'regionales Lesefoerderungsangebot', nextStep: 'Kontakt verifizieren und Erstkontakt senden', status: 'Offen', targetDate: '2026-08-28' },
  { priority: 'B', partner: 'Fremdenverkehrsverein / Stadtgemeinde Duernstein', category: 'Tourismus', approach: 'Duernstein-Geschichte und saisonale Familienaktion', nextStep: 'Kontakt verifizieren und senden', status: 'Offen', targetDate: '2026-09-01' },
];

export const WINDIS_KPI_SEED = [
  { metric: 'Qualifizierte Partnerkontakte', start: 0, targetOct: 15, targetDec: 30 },
  { metric: 'Partner-Zusagen / Kooperationen', start: 0, targetOct: 3, targetDec: 6 },
  { metric: 'Sichtplatzierungen / Partneraktionen bestaetigt', start: 0, targetOct: 2, targetDec: 4 },
  { metric: 'Unabhaengige Rezensionen (neu)', start: 0, targetOct: 40, targetDec: 100 },
  { metric: 'Hero-Titel mit klarer Landingpage', start: 0, targetOct: 4, targetDec: 4 },
  { metric: 'Regionale Verkaufsstellen mit Sichtplatzierung', start: 0, targetOct: 3, targetDec: 6 },
  { metric: 'Tourismus-/Partnerseiten mit Windis-Verweis', start: 1, targetOct: 3, targetDec: 5 },
];
