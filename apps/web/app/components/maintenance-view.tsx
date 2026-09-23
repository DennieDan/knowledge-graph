"use client";

import { useEffect, useState } from "react";
import { getHealth, type HealthSnapshot } from "../lib/api";
import styles from "./maintenance-view.module.css";

export default function MaintenanceView({ accountId }: { accountId: string | null }) {
  const [health, setHealth] = useState<HealthSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!accountId) return;
    let cancelled = false;
    getHealth(accountId)
      .then((data) => {
        if (!cancelled) {
          setHealth(data);
          setError(null);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || "Could not load health");
      });
    return () => {
      cancelled = true;
    };
  }, [accountId]);

  if (!accountId) {
    return (
      <div className={styles.root}>
        <h1 className={styles.title}>Maintenance</h1>
        <p className={styles.lead}>Select an account to see health.</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.root}>
        <h1 className={styles.title}>Maintenance</h1>
        <p className={styles.lead}>{error}</p>
      </div>
    );
  }

  if (!health) {
    return (
      <div className={styles.root}>
        <h1 className={styles.title}>Maintenance</h1>
        <p className={styles.lead}>Loading…</p>
      </div>
    );
  }

  return (
    <div className={styles.root}>
      <h1 className={styles.title}>Maintenance</h1>
      <p className={styles.lead}>{health.at_rest}</p>
      {health.alarms.length > 0 && (
        <ul className={styles.alarms}>
          {health.alarms.map((alarm) => (
            <li key={alarm.key}>{alarm.message}</li>
          ))}
        </ul>
      )}
      <button type="button" className={styles.toggle} onClick={() => setExpanded((v) => !v)}>
        {expanded ? "Hide numbers" : "Show numbers"}
      </button>
      {expanded && (
        <div className={styles.panels}>
          <section>
            <h2>What people did</h2>
            <p>
              Person {health.windows["7d"].confirms.person ?? 0} · Bulk{" "}
              {health.windows["7d"].confirms.bulk ?? 0} · Auto{" "}
              {health.windows["7d"].confirms.auto ?? 0} (7d)
            </p>
          </section>
          <section>
            <h2>What the checks found</h2>
            <p>
              Raised {health.windows["7d"].findings.raised} · Open{" "}
              {health.windows["7d"].findings.open} · Dismiss rate{" "}
              {Math.round(health.windows["7d"].findings.dismiss_rate * 100)}%
            </p>
          </section>
          <section>
            <h2>What the nightly test says</h2>
            <p>
              {health.nightly_test
                ? `${health.nightly_test.status} · recall@5 ${
                    health.nightly_test.recall_at_5_mean ?? "—"
                  }`
                : "No run yet"}
            </p>
          </section>
          <section>
            <h2>What it cost</h2>
            <p>
              Queue {health.jobs?.queue_depth ?? health.queue_depth} · Failures 24h{" "}
              {health.jobs?.failures_last_24h ?? 0} · Tokens today{" "}
              {health.model_spend_tokens_today}
              {health.daily_token_budget != null ? ` / ${health.daily_token_budget}` : ""}
            </p>
            <p>
              7d spend {health.windows["7d"].model_spend_tokens ?? "—"} · 28d spend{" "}
              {health.windows["28d"].model_spend_tokens ?? "—"}
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
