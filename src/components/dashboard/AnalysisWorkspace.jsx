import { useState } from "react";
import { useLocation, useNavigate } from "react-router";
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
import useProviderValuation from "@/hooks/useProviderValuation";
import { scenarioNames } from "@/valuation/scenarios";
import DataModeControl from "./DataModeControl";
import DataQualityNotice from "./DataQualityNotice";
import ProviderAssumptionEditor from "./ProviderAssumptionEditor";
import ProviderValuationStatus from "./ProviderValuationStatus";
import ProviderValuationDiagnostics from "./ProviderValuationDiagnostics";
import ProviderDataCompleteness from "./ProviderDataCompleteness";
import AIResearchWorkspace from "./AIResearchWorkspace";

function Workspace({ company, valuation }) {
  const [selectedModel, setSelectedModel] = useState(() => valuation.providerMode ? "pe" : valuation.results.find((result) => result.applicable)?.id ?? "fcff");
  const { pathname, hash } = useLocation();
  const navigate = useNavigate();
  const researchActive = valuation.providerMode && hash === "#ai-research";
  return (
    <DashboardLayout showAIResearch={valuation.providerMode}>
      <DataModeControl />
      <CompanyHeader company={company} />
      {company.dataMode === "provider" && (
        <><DataQualityNotice company={company} /><div className="ai-view-tabs" role="group" aria-label="Company workspace view"><button type="button" aria-pressed={!researchActive} onClick={() => navigate(`${pathname}#overview`)}>Valuation</button><button type="button" aria-pressed={researchActive} onClick={() => navigate(`${pathname}#ai-research`)}>AI Research</button></div></>
      )}
      <div hidden={researchActive}>
      {valuation.providerMode && <ProviderValuationStatus company={company} valuation={valuation} />}
      <div className="research-context-row">
        <span>
          Analysis workspace{" "}
          <span className="research-caption">· {company.dataMode === "provider" ? company.currency || "Currency unavailable" : "USD"} per share</span>
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
      {valuation.providerMode && <><ProviderValuationDiagnostics valuation={valuation} currency={company.currency} /><ProviderDataCompleteness valuation={valuation} /></>}
      <ModelComparison
        company={company}
        valuation={valuation}
        setSelectedModel={setSelectedModel}
      />
      {valuation.providerMode ? <ProviderAssumptionEditor selectedModel={selectedModel} setSelectedModel={setSelectedModel} valuation={valuation} currency={company.currency} /> : <AssumptionEditor
        selectedModel={selectedModel}
        setSelectedModel={setSelectedModel}
        valuation={valuation}
        providerMode={company.dataMode === "provider"}
      />}
      <ScenarioAnalysis valuation={valuation} />
      <FinancialStatements company={company} />
      <SensitivityTable company={company} valuation={valuation} />
      <ReverseDCF company={company} valuation={valuation} />
      <ResearchInsights company={company} />
      </div>
      {valuation.providerMode && <AIResearchWorkspace key={JSON.stringify([company.ticker, valuation.valuationRequest])} company={company} valuation={valuation} active={researchActive} />}
    </DashboardLayout>
  );
}

function DemoWorkspace({ company }) {
  const valuation = useValuation(company);
  return <Workspace company={company} valuation={valuation} />;
}

function ProviderWorkspace({ company }) {
  const valuation = useProviderValuation(company);
  return <Workspace company={company} valuation={valuation} />;
}

export default function AnalysisWorkspace({ company }) {
  return company.dataMode === "provider" ? <ProviderWorkspace company={company} /> : <DemoWorkspace company={company} />;
}
