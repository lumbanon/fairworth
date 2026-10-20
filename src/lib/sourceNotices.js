const issueNames = {
  restated_fact: "Restated financial facts",
  conflicting_concept_aliases: "Conflicting reported concepts",
  missing_debt_components: "Missing debt components",
  incomplete_debt_components: "Incomplete debt components",
  missing_operating_cash_flow: "Missing operating cash flow",
  incompatible_ytd_basis: "Incompatible year-to-date reporting bases",
  inconsistent_balance_sheet: "Balance-sheet reconciliation issues",
  missing_financial_field: "Missing financial fields",
  missing_share_count: "Current share count unavailable",
  missing_capex: "Capital expenditures unavailable",
  ambiguous_fiscal_period: "Ambiguous fiscal periods",
  historical_diluted_share_denominator: "Historical diluted-share denominator",
};

export function noticeMessage(notice) {
  return typeof notice === "string" ? notice : notice?.message ?? "Source diagnostic";
}

function periodMatch(notice) {
  return noticeMessage(notice).match(/^(FY\s?(\d{4})\s+(?:FY|Q[1-4])\s+\((\d{4}-\d{2}-\d{2})\)):\s*/);
}

export function isHistoricalNotice(notice) {
  return Boolean(periodMatch(notice));
}

export function groupSourceNotices(notices = []) {
  const groups = new Map();
  for (const notice of notices) {
    const match = periodMatch(notice);
    const message = noticeMessage(notice).slice(match?.[0].length ?? 0);
    const code = typeof notice === "object" && notice !== null ? notice.code : null;
    const key = code || message;
    if (!groups.has(key)) groups.set(key, {
      key, title: issueNames[code] || (code ? code.replaceAll("_", " ") : message),
      message, notices: [], periods: [], fields: [],
    });
    const group = groups.get(key);
    // Retain every original diagnostic, including metadata and repeated records.
    group.notices.push(notice);
    if (match && !group.periods.some((period) => period.label === match[1])) {
      group.periods.push({ label: match[1], year: Number(match[2]), date: match[3] });
    }
    if (notice?.field && !group.fields.includes(notice.field)) group.fields.push(notice.field);
  }
  return [...groups.values()].map((group) => ({
    ...group, periods: group.periods.sort((a, b) => a.date.localeCompare(b.date)),
  }));
}

export function noticePeriodSummary(periods = []) {
  if (!periods.length) return "No reporting period specified";
  const years = [...new Set(periods.map((period) => period.year))].sort((a, b) => a - b);
  const ranges = [];
  let start = years[0];
  let end = start;
  for (const year of years.slice(1)) {
    if (year === end + 1) end = year;
    else { ranges.push(start === end ? `${start}` : `${start}–${end}`); start = end = year; }
  }
  ranges.push(start === end ? `${start}` : `${start}–${end}`);
  return `FY ${ranges.join(", ")} · ${periods.length} reporting period${periods.length === 1 ? "" : "s"}`;
}

export function companyDescriptionPreview(description, limit = 280) {
  const full = String(description ?? "").trim();
  if (full.length <= limit) return { preview: full, full, expandable: false };
  const slice = full.slice(0, limit - 1);
  const boundary = slice.lastIndexOf(" ");
  const preview = (boundary > limit * 0.6 ? slice.slice(0, boundary) : slice).trimEnd();
  return { preview: `${preview}…`, full, expandable: true };
}
