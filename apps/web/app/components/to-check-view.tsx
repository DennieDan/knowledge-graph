"use client";

import { useEffect, useState } from "react";
import Icon from "./icons";
import styles from "./to-check-view.module.css";
import type { StackType, Substack } from "../lib/stacks";
import {
  dismissFinding,
  listFindings,
  type FindingRow,
} from "../lib/api";

type QueueKind = "new" | "update" | "attention";

const FILTERS: [QueueKind | "all" | "findings", string][] = [
  ["all", "All"],
  ["new", "New proposals"],
  ["update", "Updates"],
  ["attention", "Needs attention"],
  ["findings", "Findings"],
];

const KIND_LABEL: Record<QueueKind, string> = {
  new: "New",
  update: "Update",
  attention: "Needs review",
};

const DEFAULT_REASONS = [
  "not_a_change",
  "already_handled",
  "source_is_wrong",
  "duplicate",
  "other_recorded_below",
];

function queueKind(ss: Substack): QueueKind | null {
  if (ss.reviewState === "unsupported" || ss.reviewState === "generation_error") {
    return "attention";
  }
  if (ss.status !== "confirmed") return "new";
  if (ss.reviewState === "pending_update") return "update";
  return null;
}

function kindLabel(ss: Substack, kind: QueueKind): string {
  if (ss.reviewState === "generation_error") return "Generation failed";
  return KIND_LABEL[kind];
}

export default function ToCheckView({
  accountId,
  stackTypes,
  substacks,
  busy,
  notice,
  onOpen,
  onConfirm,
}: {
  accountId: string | null;
  stackTypes: StackType[];
  substacks: Substack[];
  busy: boolean;
  notice: string;
  onOpen: (ss: Substack) => void;
  onConfirm: (ss: Substack) => void;
}) {
  const [filter, setFilter] = useState<QueueKind | "all" | "findings">("all");
  const [findings, setFindings] = useState<FindingRow[]>([]);
  const [reasons, setReasons] = useState<string[]>(DEFAULT_REASONS);
  const [dismissBusy, setDismissBusy] = useState<string | null>(null);

  const refreshFindings = () => {
    if (!accountId) {
      setFindings([]);
      return;
    }
    listFindings(accountId)
      .then((data) => {
        setFindings(data.findings);
        if (data.dismissal_reasons?.length) setReasons(data.dismissal_reasons);
      })
      .catch(() => setFindings([]));
  };

  useEffect(() => {
    refreshFindings();
  }, [accountId]);

  const queue = substacks
    .map((ss) => ({ ss, kind: queueKind(ss) }))
    .filter((item): item is { ss: Substack; kind: QueueKind } => item.kind !== null);
  const visible = queue.filter((item) => filter === "all" || item.kind === filter);
  const showFindings = filter === "all" || filter === "findings";
  const total = queue.length + findings.length;

  const handleDismiss = async (findingId: string, reason: string) => {
    if (!accountId) return;
    setDismissBusy(findingId);
    try {
      await dismissFinding(accountId, findingId, reason);
      setFindings((rows) => rows.filter((row) => row.id !== findingId));
    } finally {
      setDismissBusy(null);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.hero}>
        <div>
          <h1 className={styles.title}>
            <span className={styles.titleIcon}>
              <Icon name="inbox" size={17} />
            </span>
            To check
          </h1>
          <p className={styles.subtitle}>Proposals and findings waiting for a person.</p>
        </div>
        <span className={styles.chip}>
          {total} {total === 1 ? "item" : "items"}
        </span>
      </div>

      <div className={styles.filterRow} role="group" aria-label="Filter queue">
        {FILTERS.map(([kind, label]) => (
          <button
            key={kind}
            type="button"
            aria-pressed={filter === kind}
            onClick={() => setFilter(kind)}
            className={`${styles.filterChip} ${filter === kind ? styles.filterChipActive : ""}`}
          >
            {label}
          </button>
        ))}
      </div>

      {visible.length === 0 && !(showFindings && findings.length > 0) ? (
        <div className={styles.empty}>
          <p className={styles.emptyTitle}>Nothing to check</p>
          <p className={styles.emptyText}>New proposals will appear here.</p>
        </div>
      ) : (
        <div className={styles.list}>
          {filter !== "findings" &&
            visible.map(({ ss, kind }) => {
              const type = stackTypes.find((t) => t.id === ss.typeId);
              return (
                <div key={ss.id} className={styles.row}>
                  <button
                    type="button"
                    className={styles.rowMain}
                    onClick={() => onOpen(ss)}
                    aria-label={`Open ${ss.name}`}
                  >
                    <span className={styles.rowIcon}>
                      <Icon name={type?.icon ?? "file-text"} size={15} />
                    </span>
                    <span className={styles.rowBody}>
                      <span className={styles.rowName}>
                        {ss.name}
                        {kind === "attention" && (
                          <span className={`${styles.state} ${styles.state_attention}`}>
                            {kindLabel(ss, kind)}
                          </span>
                        )}
                      </span>
                      <span className={styles.rowMeta}>
                        {type?.name ?? "Stack"} · {ss.count}{" "}
                        {ss.count === 1 ? "source" : "sources"} · {ss.access} ·{" "}
                        {ss.updated}
                      </span>
                    </span>
                  </button>
                  <div className={styles.rowActions}>
                    {kind === "new" ? (
                      <button
                        type="button"
                        className={styles.confirmBtn}
                        disabled={busy}
                        onClick={() => onConfirm(ss)}
                      >
                        <Icon name="check" size={13} /> Confirm
                      </button>
                    ) : (
                      <button type="button" className={styles.reviewBtn} onClick={() => onOpen(ss)}>
                        {kind === "update" ? "Review update" : "Review"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}

          {showFindings &&
            findings.map((finding) => (
              <div key={finding.id} className={styles.row}>
                <div className={styles.rowMain}>
                  <span className={styles.rowIcon}>
                    <Icon name="activity" size={15} />
                  </span>
                  <span className={styles.rowBody}>
                    <span className={styles.rowName}>
                      {finding.summary_sentence}
                      <span className={`${styles.state} ${styles.state_attention}`}>Needs attention</span>
                    </span>
                    <span className={styles.rowMeta}>
                      {finding.check_key} · {new Date(finding.detected_at).toLocaleString()}
                    </span>
                  </span>
                </div>
                <div className={styles.rowActions}>
                  <label className={styles.reviewBtn}>
                    Dismiss
                    <select
                      aria-label="Dismissal reason"
                      disabled={dismissBusy === finding.id}
                      defaultValue=""
                      onChange={(event) => {
                        const reason = event.target.value;
                        if (reason) void handleDismiss(finding.id, reason);
                      }}
                    >
                      <option value="" disabled>
                        Reason…
                      </option>
                      {reasons.map((reason) => (
                        <option key={reason} value={reason}>
                          {reason}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>
            ))}
        </div>
      )}

      {notice && (
        <div role="status" aria-live="polite" className={styles.notice}>
          {notice}
        </div>
      )}
    </div>
  );
}
