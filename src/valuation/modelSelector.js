import { modelDefinitions } from "../data/modelDefinitions.js";
import { assumptionDefinitions } from "../data/assumptionDefinitions.js";
import { unavailable } from "./validation.js";

export function modelEligibility(model, company) {
  const { latest, isBank, isREIT } = company;
  const id = model.id;
  const incompatibility =
    company.modelCompatibility?.all ?? company.modelCompatibility?.[id];
  if (incompatibility) return unavailable("insufficient-data", incompatibility);
  if (
    company.dataMode === "provider" &&
    ((["fcff", "fcfe", "pe", "evEbitda", "evRevenue", "peg"].includes(id) &&
      (isBank == null || isREIT == null)) ||
      (["residual", "pb"].includes(id) && isBank == null) ||
      (id === "affo" && isREIT == null))
  )
    return unavailable(
      "insufficient-data",
      "Business classification is unavailable; applicability cannot be confirmed for this method.",
    );
  if (
    ["fcff", "fcfe", "pe", "evEbitda", "evRevenue", "peg"].includes(id) &&
    (isBank || isREIT)
  )
    return unavailable(
      "not-applicable",
      "This engine uses equity models for banks and AFFO for REITs.",
    );
  if (["residual", "pb"].includes(id) && !isBank)
    return unavailable(
      "not-applicable",
      "Book-equity models are reserved for banking businesses in this engine.",
    );
  if (id === "affo" && !isREIT)
    return unavailable(
      "not-applicable",
      "AFFO valuation requires a REIT with meaningful AFFO data.",
    );
  if (id === "dividend" && (!company.stableDividend || isREIT))
    return unavailable(
      "not-applicable",
      "A stable dividend policy is required; this REIT example uses AFFO.",
    );
  if (id === "graham" && !company.grahamSuitable)
    return unavailable(
      "not-applicable",
      "This company is not marked as suitable for the Graham book-value heuristic.",
    );
  const data = { ...latest, otherClaims: company.otherClaims };
  const missing = model.requiredInputs.filter((key) => data[key] == null);
  if (missing.length)
    return unavailable(
      "insufficient-data",
      `Missing financial inputs: ${missing.join(", ")}.`,
    );
  const positiveFields = {
    fcff: ["fcff"],
    fcfe: ["fcfe"],
    pe: ["netIncome"],
    peg: ["netIncome"],
    evEbitda: ["ebitda"],
    evRevenue: ["revenue"],
    graham: ["netIncome", "bookEquity"],
    dividend: ["dividends"],
    residual: ["bookEquity"],
    pb: ["bookEquity"],
    affo: ["affo"],
  };
  if (positiveFields[id].some((key) => data[key] <= 0))
    return unavailable(
      "not-applicable",
      `This simplified method requires positive ${positiveFields[id].join(" and ")}. Turnaround cash-flow projections are outside this demo.`,
    );
  return { status: "applicable", warnings: [] };
}

export function calculationInputs(company, assumptions) {
  return {
    ...company.latest,
    otherClaims: company.otherClaims,
    ...assumptions,
  };
}
export function validateModelAssumptions(modelId, assumptions) {
  const model = modelDefinitions.find((item) => item.id === modelId);
  if (!model) return unavailable("invalid-input", "Unknown valuation method.");
  const warnings = model.assumptions.flatMap((key) => {
    const definition = assumptionDefinitions[key];
    const value = assumptions[key];
    const displayValue = definition.unit === "%" ? value * 100 : value;
    return typeof value !== "number" ||
      !Number.isFinite(value) ||
      displayValue < definition.min ||
      displayValue > definition.max ||
      (key === "forecastYears" && !Number.isInteger(value))
      ? [
          `${definition.label} must be a finite value from ${definition.min} to ${definition.max} ${definition.unit}${key === "forecastYears" ? ", in whole years" : ""}.`,
        ]
      : [];
  });
  return warnings.length ? unavailable("invalid-input", warnings) : null;
}
export function evaluateModels(company, assumptions) {
  const inputs = calculationInputs(company, assumptions);
  return modelDefinitions.map((model) => {
    const eligibility = modelEligibility(model, company);
    const result =
      eligibility.status !== "applicable"
        ? eligibility
        : validateModelAssumptions(model.id, assumptions) ||
          model.calculate(inputs);
    return {
      ...result,
      id: model.id,
      name: model.name,
      shortName: model.shortName,
      applicable: eligibility.status === "applicable",
    };
  });
}
