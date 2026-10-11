import { useEffect } from "react";
import { Routes, Route, useLocation } from "react-router";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import Home from "@/pages/Home";
import { DashboardNavbar } from "@/components/dashboard/DashboardLayout";
import Dashboard from "@/pages/Dashboard";
import SignInPlaceholder from "@/pages/SignInPlaceholder";
import StockAnalysis from "@/pages/StockAnalysis";
import InformationPlaceholder from "@/pages/InformationPlaceholder";
import DataModeProvider from "@/context/DataModeProvider";

function ScrollToLocation() {
  const { pathname, hash, key } = useLocation();
  useEffect(() => {
    if (hash) {
      const frame = requestAnimationFrame(() =>
        document.getElementById(hash.slice(1))?.scrollIntoView(),
      );
      return () => cancelAnimationFrame(frame);
    }
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [pathname, hash, key]);
  return null;
}

function AppContent() {
  const { pathname } = useLocation();
  const isResearch =
    pathname === "/dashboard" || pathname.startsWith("/stocks/");
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <ScrollToLocation />
      {isResearch ? <DashboardNavbar /> : <Navbar />}
      <main id="main-content" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/signin" element={<SignInPlaceholder />} />
          <Route path="/stocks/:ticker" element={<StockAnalysis />} />
          <Route path="/:page" element={<InformationPlaceholder />} />
          <Route path="*" element={<InformationPlaceholder />} />
        </Routes>
      </main>
      <Footer />
    </>
  );
}

export default function App() {
  return (
    <DataModeProvider>
      <AppContent />
    </DataModeProvider>
  );
}
