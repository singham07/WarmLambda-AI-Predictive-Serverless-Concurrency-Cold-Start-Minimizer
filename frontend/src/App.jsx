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
          <div>
            <Link to="/" className="brand">WarmLambda AI</Link>
            <p className="brand-subtitle">
              Predicts traffic and recommends how many instances to keep warm. Tested in a simulator.
            </p>
          </div>
          <nav className="site-nav" aria-label="Primary navigation">
            <NavLink to="/" end>Dashboard</NavLink>
            <NavLink to="/experiment-results">Experiment results</NavLink>
          </nav>
        </div>
        <div className="notice-banner">Simulated estimates, not real AWS measurements or costs.</div>
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
