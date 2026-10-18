import React, { useState } from "react";
import { BrowserRouter, Routes, Route, NavLink, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import ExperimentSummary from "./pages/ExperimentSummary";
import Privacy from "./pages/Privacy";
import Terms from "./pages/Terms";
import NotFound from "./pages/NotFound";

export default function App() {
  const [apiDisclaimer, setApiDisclaimer] = useState("");

  return (
    <BrowserRouter>
      {/* Header */}
      <header className="app-header">
        <div className="header-top">
          <h1 className="app-title">
            WarmLambda AI: simulated warm-capacity policy comparison
          </h1>
          <nav>
            <ul className="nav-links">
              <li>
                <NavLink
                  to="/"
                  end
                  className={({ isActive }) =>
                    isActive ? "nav-link active" : "nav-link"
                  }
                >
                  Dashboard
                </NavLink>
              </li>
              <li>
                <NavLink
                  to="/experiment-results"
                  className={({ isActive }) =>
                    isActive ? "nav-link active" : "nav-link"
                  }
                >
                  Experiment results
                </NavLink>
              </li>
            </ul>
          </nav>
        </div>

        <div className="notice-banner">
          Results are simulated estimates under stated assumptions. They are not real AWS measurements or costs.
        </div>

        {apiDisclaimer && (
          <div className="api-disclaimer-note">
            API note: {apiDisclaimer}
          </div>
        )}
      </header>

      {/* Main Content */}
      <main className="main-content">
        <Routes>
          <Route
            path="/"
            element={<Dashboard onDisclaimer={setApiDisclaimer} />}
          />
          <Route
            path="/experiment-results"
            element={<ExperimentSummary />}
          />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>

      {/* Footer */}
      <footer className="app-footer">
        <ul className="footer-links">
          <li>
            <Link to="/privacy">Privacy Policy</Link>
          </li>
          <li>
            <Link to="/terms">Terms and Conditions</Link>
          </li>
        </ul>
        <span>College project, GLA University.</span>
      </footer>
    </BrowserRouter>
  );
}
