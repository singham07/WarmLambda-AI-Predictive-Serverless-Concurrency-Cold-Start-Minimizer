import React from "react";
import { BrowserRouter, Routes, Route, NavLink, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import ExperimentSummary from "./pages/ExperimentSummary";
import Privacy from "./pages/Privacy";
import Terms from "./pages/Terms";
import NotFound from "./pages/NotFound";

export default function App() {
  return (
    <BrowserRouter>
      <header className="site-header">
        <div className="header-inner">
          <Link to="/" className="brand-lockup">
            <span className="brand-mark" aria-hidden="true">WL</span>
            <span><strong className="brand">WarmLambda AI</strong><span className="brand-subtitle">capacity intelligence console</span></span>
          </Link>
          <nav className="site-nav" aria-label="Primary navigation">
            <NavLink to="/" end>Workbench</NavLink>
            <NavLink to="/experiment-results">Benchmark archive</NavLink>
          </nav>
        </div>
        <div className="notice-banner"><strong>SIMULATION MODE</strong> &nbsp; Outputs are modeled estimates, not live cloud telemetry or billing data.</div>
      </header>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/experiment-results" element={<ExperimentSummary />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <footer className="site-footer">
        <div><Link to="/privacy">Privacy Policy</Link><Link to="/terms">Terms and Conditions</Link></div>
        <span>Academic systems engineering project</span>
      </footer>
    </BrowserRouter>
  );
}
