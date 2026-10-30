import React from "react";
import { BrowserRouter, Routes, Route, NavLink, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import ExperimentSummary from "./pages/ExperimentSummary";
import Privacy from "./pages/Privacy";
import Terms from "./pages/Terms";
import NotFound from "./pages/NotFound";

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" fill="#f0a23b" rx="3" />
      <rect x="6" y="19" width="5" height="7" fill="#0a0e12" />
      <rect x="13.5" y="13" width="5" height="13" fill="#0a0e12" />
      <rect x="21" y="6" width="5" height="20" fill="#0a0e12" />
    </svg>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <header className="site-header">
        <div className="header-inner">
          <Link to="/" className="brand">
            <BrandMark />
            WarmLambda AI
          </Link>
          <nav className="site-nav" aria-label="Primary navigation">
            <NavLink to="/" end>Simulator</NavLink>
            <NavLink to="/experiment-results">Experiment results</NavLink>
          </nav>
          <span className="sim-note">Simulated estimates, not real AWS measurements or costs</span>
        </div>
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
        <div>
          <Link to="/privacy">Privacy Policy</Link>
          <Link to="/terms">Terms and Conditions</Link>
        </div>
        <span>College project, GLA University.</span>
      </footer>
    </BrowserRouter>
  );
}