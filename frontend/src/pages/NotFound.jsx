import React from "react";
import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="text-page" style={{ textAlign: "center" }}>
      <p className="eyebrow">ROUTE NOT FOUND</p>
      <h1>404: Page Not Found</h1>
      <p>The requested console route does not exist.</p>
      <Link to="/" className="button primary-button" style={{ display: "inline-block", width: "auto" }}>
        Return to Workbench
      </Link>
    </div>
  );
}
