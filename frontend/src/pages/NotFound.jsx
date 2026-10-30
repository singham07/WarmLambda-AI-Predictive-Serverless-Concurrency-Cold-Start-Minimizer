import React from "react";
import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="text-page" style={{ textAlign: "center" }}>
      <h1>Page not found</h1>
      <p>The requested page does not exist.</p>
      <Link to="/" className="button">
        Back to the simulator
      </Link>
    </div>
  );
}