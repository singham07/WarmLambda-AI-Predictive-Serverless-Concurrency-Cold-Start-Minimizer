import React from "react";
import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="text-page" style={{ textAlign: "center" }}>
      <h1>404: Page Not Found</h1>
      <p>The requested page does not exist.</p>
      <Link to="/" className="btn btn-primary" style={{ display: "inline-block", width: "auto" }}>
        Return to Dashboard
      </Link>
    </div>
  );
}
