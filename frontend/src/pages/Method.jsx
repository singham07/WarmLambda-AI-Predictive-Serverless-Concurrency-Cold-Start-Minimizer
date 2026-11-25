import React from "react";

const steps = [
  ["Traffic generator", "A non-homogeneous Poisson process samples arrivals from a scenario rate function."],
  ["Discrete-event simulator", "Requests move through initializing, idle, and busy instance states with queue timeouts."],
  ["Forecaster", "A named forecaster uses completed interval counts only. No future arrivals enter a decision."],
  ["Little's Law sizing", "N = ceil(rate x mean execution time x (1 + headroom)). The result is capped by max instances."],
  ["Correction and budget", "The full policy compares forecast capacity with current busy and queued load, then applies an optional budget."],
];

export default function Method() {
  return (
    <section className="document-page">
      <p className="eyebrow">Method</p>
      <h1>How the simulator works</h1>
      <p className="lede">This page describes the implemented simulation path and its explicit assumptions.</p>
      <div className="method-list">
        {steps.map(([title, body], index) => (
          <article className="method-step" key={title}>
            <span className="step-number">{String(index + 1).padStart(2, "0")}</span>
            <div><h2>{title}</h2><p>{body}</p></div>
          </article>
        ))}
      </div>
      <section className="card">
        <h2>Assumptions and limitations</h2>
        <ul className="plain-list">
          <li>One invocation runs per instance at a time.</li>
          <li>Cold-start time is fixed by the simulation configuration.</li>
          <li>Costs are dimensionless instance-time units.</li>
          <li>Known seasonal periods are an explicit experiment assumption.</li>
          <li>Synthetic traffic does not establish production performance.</li>
        </ul>
      </section>
    </section>
  );
}
