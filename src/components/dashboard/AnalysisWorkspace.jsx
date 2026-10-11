import { useState } from "react";
import DashboardLayout from "./DashboardLayout";
import CompanyHeader from "./CompanyHeader";
import ValuationSummary from "./ValuationSummary";
import ModelComparison from "./ModelComparison";
import AssumptionEditor from "./AssumptionEditor";
import ScenarioAnalysis from "./ScenarioAnalysis";
import FinancialStatements from "./FinancialStatements";
import SensitivityTable from "./SensitivityTable";
import ReverseDCF from "./ReverseDCF";
import ResearchInsights from "./ResearchInsights";
import useValuation from "@/hooks/useValuation";
import { scenarioNames } from "@/valuation/scenarios";
import DataModeControl from "./DataModeControl";
import DataQualityNotice from "./DataQualityNotice";

export default function AnalysisWorkspace({ company }) {
  const valuation = useValuation(company);
  const [selectedModel, setSelectedModel] = useState(
    () => valuation.results.find((result) => result.applicable)?.id ?? "fcff",
  );
  return (
    <DashboardLayout>
      <DataModeControl />
      <CompanyHeader company={company} />
      {company.dataMode === "provider" && (
        <DataQualityNotice company={company} />
      )}
      <div className="research-context-row">
        <span>
          Analysis workspace{" "}
          <span className="research-caption">· USD per share</span>
        </span>
        <div
          className="research-segmented"
          role="group"
          aria-label="Active valuation scenario"
        >
          {scenarioNames.map((name) => (
            <button
              key={name}
              aria-pressed={valuation.activeScenario === name}
              onClick={() => valuation.setActiveScenario(name)}
            >
              {name[0].toUpperCase() + name.slice(1)}
            </button>
          ))}
        </div>
      </div>
      <ValuationSummary company={company} valuation={valuation} />
      <ModelComparison
        company={company}
        valuation={valuation}
        setSelectedModel={setSelectedModel}
      />
      <AssumptionEditor
        selectedModel={selectedModel}
        setSelectedModel={setSelectedModel}
        valuation={valuation}
        providerMode={company.dataMode === "provider"}
      />
      <ScenarioAnalysis valuation={valuation} />
      <FinancialStatements company={company} />
      <SensitivityTable company={company} valuation={valuation} />
      <ReverseDCF company={company} valuation={valuation} />
      <ResearchInsights company={company} />
    </DashboardLayout>
  );
}
