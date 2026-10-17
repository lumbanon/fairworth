import { Link, useLocation } from "react-router";
import { UserRound } from "lucide-react";
import StockSearch from "@/components/landing/StockSearch";
import { useDataMode } from "@/context/dataMode";

export function DashboardNavbar() {
  return (
    <header className="site-header research-header">
      <div className="research-nav">
        <Link to="/" className="wordmark" aria-label="Fairworth home">
          fairworth<span className="wordmark-period">.</span>
        </Link>
        <StockSearch compact dashboard />
        <nav aria-label="Research navigation">
          <Link to="/">Home</Link>
          <Link to="/dashboard">Dashboard</Link>
          <Link
            className="account-link"
            to="/signin"
            aria-label="Account placeholder"
          >
            <UserRound size={16} aria-hidden="true" />
            <span>Account</span>
          </Link>
        </nav>
      </div>
    </header>
  );
}

const sections = [
  ["Overview", "overview"],
  ["Valuation Models", "models"],
  ["Financials", "financials"],
  ["Scenarios", "scenarios"],
  ["Sensitivity Analysis", "sensitivity"],
  ["Research Insights", "insights"],
];

export default function DashboardLayout({ children, showAIResearch = false }) {
  const { pathname, hash } = useLocation();
  const { mode } = useDataMode();
  return (
    <div className="research-shell">
      <aside className="research-sidebar">
        <span className="research-sidebar-label">RESEARCH WORKSPACE</span>
        <nav aria-label="Dashboard sections">
          {sections.map(([label, id]) => (
            <Link
              key={id}
              to={`${pathname}#${id}`}
              aria-current={
                (hash || "#overview") === `#${id}` ? "location" : undefined
              }
            >
              {label}
            </Link>
          ))}
          {showAIResearch && <Link to={`${pathname}#ai-research`} aria-current={hash === "#ai-research" ? "location" : undefined}>AI Research</Link>}
        </nav>
        <div className="sidebar-note">
          {mode === "provider" ? "Provider workspace" : "Demonstration preview"}
          <p>
            Local calculations.
            <br />
            {mode === "provider"
              ? "Reported financials."
              : "Fictional financials."}
          </p>
        </div>
      </aside>
      <div className="research-content">{children}</div>
    </div>
  );
}
