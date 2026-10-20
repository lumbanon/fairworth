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
import ProviderCoverage from "./ProviderCoverage";
import { ordinaryWorkflowRestriction } from "@/lib/securityIdentity";

function Workspace({ company, valuation }) {
  const [selectedModel, setSelectedModel] = useState(() => valuation.providerMode ? "pe" : valuation.results.find((result) => result.applicable)?.id ?? "fcff");
  const { pathname, search, hash } = useLocation();
  const location = `${pathname}${search}`;
  const navigate = useNavigate();
  const researchActive = valuation.providerMode && hash === "#ai-research";
  return (
    <DashboardLayout showAIResearch={valuation.providerMode}>
      <DataModeControl />
      <CompanyHeader company={company} />
      {valuation.providerMode && <ProviderCoverage company={company} />}
      {company.dataMode === "provider" && (
        <><DataQualityNotice company={company} /><div className="ai-view-tabs" role="group" aria-label="Company workspace view"><button type="button" aria-pressed={!researchActive} onClick={() => navigate(`${location}#overview`)}>Valuation</button><button type="button" aria-pressed={researchActive} onClick={() => navigate(`${location}#ai-research`)}>AI Research</button></div></>
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
      {valuation.providerMode && <AIResearchWorkspace key={JSON.stringify([company.instrumentId ?? company.ticker, company.issuerId, company.listingId, valuation.valuationRequest])} company={company} valuation={valuation} active={researchActive} />}
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

function ProfileWorkspace({ company, reason }) {
  return <DashboardLayout><DataModeControl /><CompanyHeader company={company} /><ProviderCoverage company={company} /><DataQualityNotice company={company} /><section className="research-section" aria-labelledby="security-applicability-heading"><h2 id="security-applicability-heading">Ordinary-stock valuation unavailable</h2><p>{reason}</p><p className="research-caption">Search and profile coverage are separate from financial-model applicability. No ordinary-stock estimate is substituted for this security.</p></section><FinancialStatements company={company} /></DashboardLayout>;
}

export default function AnalysisWorkspace({ company }) {
  const restriction = ordinaryWorkflowRestriction(company.coverage);
  if (company.dataMode === "provider" && restriction) return <ProfileWorkspace company={company} reason={restriction} />;
  return company.dataMode === "provider" ? <ProviderWorkspace company={company} /> : <DemoWorkspace company={company} />;
}
