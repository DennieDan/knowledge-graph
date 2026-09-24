"use client";

import { useEffect, useState } from "react";
import {
  deliverMorning,
  getMorning,
  type MorningMessage,
} from "../lib/api";
import styles from "./morning-panel.module.css";

type Props = {
  accountId: string | null;
  onOpenToCheck?: () => void;
};

export default function MorningPanel({ accountId, onOpenToCheck }: Props) {
  const [message, setMessage] = useState<MorningMessage | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!accountId) {
      setMessage(null);
      return;
    }
    let cancelled = false;
    getMorning(accountId)
      .then((data) => {
        if (!cancelled) setMessage(data);
      })
      .catch(() => {
        if (!cancelled) setMessage(null);
      });
    return () => {
      cancelled = true;
    };
  }, [accountId]);

  if (!accountId || !message || message.waiting_count <= 0) {
    return null;
  }

  async function handleDryRun() {
    if (!accountId || busy) return;
    setBusy(true);
    setNotice(null);
    try {
      const result = await deliverMorning(accountId);
      setNotice(
        `Email dry-run logged (${result.waiting_count} waiting). No message was sent.`,
      );
    } catch {
      setNotice("Could not log the dry-run delivery.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel} aria-label="Morning message">
      <div className={styles.header}>
        <h2 className={styles.title}>Waiting for you</h2>
        <span className={styles.count}>{message.waiting_count}</span>
      </div>
      <p className={styles.lead}>
        Open findings that need a person before the day starts.
      </p>
      <ul className={styles.list}>
        {message.items.slice(0, 5).map((item) => (
          <li key={item.id} className={styles.item}>
            <span className={styles.itemKey}>{item.check_key}</span>
            <span className={styles.itemSummary}>{item.summary_sentence}</span>
          </li>
        ))}
      </ul>
      {message.waiting_count > 5 && (
        <p className={styles.more}>
          +{message.waiting_count - 5} more in To check
        </p>
      )}
      <div className={styles.actions}>
        {onOpenToCheck && (
          <button type="button" className={styles.primary} onClick={onOpenToCheck}>
            Review in To check
          </button>
        )}
        <button
          type="button"
          className={styles.secondary}
          onClick={handleDryRun}
          disabled={busy}
        >
          {busy ? "Logging…" : "Log email dry-run"}
        </button>
      </div>
      {notice && <p className={styles.notice}>{notice}</p>}
    </section>
  );
}
