import React from "react";
import { CONTACT_EMAIL } from "../config";

export default function Privacy() {
  return (
    <div className="text-page">
      <h1>Privacy Policy</h1>
      <p>
        WarmLambda AI is an educational simulation tool for comparing serverless
        warm-capacity policies.
      </p>

      <h2>Data Collection</h2>
      <p>
        This application does not collect, store, or share any personal data.
      </p>
      <ul>
        <li>No user accounts or authentication.</li>
        <li>No cookies or persistent local tracking tokens.</li>
        <li>No third-party analytics, tracking scripts, or telemetry.</li>
        <li>No advertisements.</li>
      </ul>

      <h2>Simulation Settings</h2>
      <p>
        The simulation parameters you enter in the settings form (such as scenario name,
        headroom, and random seed) are sent directly to the local simulator API to execute
        the simulation run. None of these inputs are tied to your identity.
      </p>

      <h2>Contact</h2>
      {CONTACT_EMAIL ? (
        <p>If you have questions regarding this policy, contact: {CONTACT_EMAIL}</p>
      ) : (
        <p>This is a student project created for academic evaluation.</p>
      )}
    </div>
  );
}
