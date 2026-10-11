import { assumptionDefinitions } from "../data/assumptionDefinitions.js";

export const scenarioNames = ["bear", "base", "bull"];
export function createScenarioDefaults(company) {
  const latest = company.latest;
  if (company.dataMode === "provider") {
    const blank = Object.fromEntries(
      Object.keys(assumptionDefinitions).map((key) => [key, null]),
    );
    blank.shares =
      Number.isFinite(latest.shares) && latest.shares > 0
        ? latest.shares
        : null;
    return { bear: { ...blank }, base: { ...blank }, bull: { ...blank } };
  }
  const base = {
    revenueGrowth: company.growth,
    cashFlowGrowth: company.cashGrowth,
    epsGrowth: company.epsGrowth,
    terminalGrowth: 0.025,
    wacc: company.wacc ?? 0.085,
    costOfEquity: company.costOfEquity ?? 0.095,
    targetPE: company.multiples[0],
    targetEVEBITDA: company.multiples[1],
    targetEVRevenue: company.multiples[2],
    targetPB: company.targetPB ?? 2,
    targetPAFFO: company.targetPAFFO ?? 16,
    targetPEG: 2,
    forecastYears: 5,
    dividendGrowth: company.dividendGrowth ?? 0.035,
    shares: latest.shares,
    ebitdaMargin: latest.ebitda == null ? null : latest.ebitda / latest.revenue,
    returnOnEquity: latest.netIncome / latest.bookEquity,
    payoutRatio:
      latest.netIncome > 0
        ? Math.min(latest.dividends / latest.netIncome, 1)
        : 0,
  };
  const bear = {
    ...base,
    revenueGrowth: base.revenueGrowth * 0.5,
    cashFlowGrowth: base.cashFlowGrowth * 0.5,
    epsGrowth: base.epsGrowth * 0.5,
    terminalGrowth: 0.02,
    wacc: base.wacc + 0.015,
    costOfEquity: base.costOfEquity + 0.015,
    dividendGrowth: base.dividendGrowth * 0.6,
    returnOnEquity: base.returnOnEquity * 0.9,
    ebitdaMargin:
      base.ebitdaMargin == null ? null : Math.max(base.ebitdaMargin * 0.9, 0),
  };
  const bull = {
    ...base,
    revenueGrowth: base.revenueGrowth * 1.3,
    cashFlowGrowth: base.cashFlowGrowth * 1.3,
    epsGrowth: base.epsGrowth * 1.3,
    terminalGrowth: 0.028,
    wacc: base.wacc - 0.01,
    costOfEquity: base.costOfEquity - 0.01,
    dividendGrowth: base.dividendGrowth * 1.2,
    returnOnEquity: base.returnOnEquity * 1.1,
    ebitdaMargin:
      base.ebitdaMargin == null ? null : Math.min(base.ebitdaMargin * 1.1, 1),
  };
  for (const key of [
    "targetPE",
    "targetEVEBITDA",
    "targetEVRevenue",
    "targetPB",
    "targetPAFFO",
    "targetPEG",
  ]) {
    bear[key] = base[key] * 0.8;
    bull[key] = base[key] * 1.2;
  }
  return { bear, base, bull };
}
