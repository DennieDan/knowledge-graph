"use client";

import { useState } from "react";
import Icon from "./icons";
import styles from "./to-check-view.module.css";
import type { StackType, Substack } from "../lib/stacks";

type QueueKind = "new" | "update" | "attention";

const FILTERS: [QueueKind | "all", string][] = [
  ["all", "All"],
  ["new", "New proposals"],
  ["update", "Updates"],
  ["attention", "Needs attention"],
];

const KIND_LABEL: Record<QueueKind, string> = {
  new: "New",
  update: "Update",
  attention: "Needs review",
};

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
  stackTypes,
  substacks,
  busy,
  notice,
  onOpen,
  onConfirm,
}: {
  stackTypes: StackType[];
  substacks: Substack[];
  busy: boolean;
  notice: string;
  onOpen: (ss: Substack) => void;
  onConfirm: (ss: Substack) => void;
}) {
  const [filter, setFilter] = useState<QueueKind | "all">("all");

  const queue = substacks
    .map((ss) => ({ ss, kind: queueKind(ss) }))
    .filter((item): item is { ss: Substack; kind: QueueKind } => item.kind !== null);
  const visible = queue.filter((item) => filter === "all" || item.kind === filter);

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
          <p className={styles.subtitle}>Proposals waiting for a person.</p>
        </div>
        <span className={styles.chip}>
          {queue.length} {queue.length === 1 ? "item" : "items"}
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

      {visible.length === 0 ? (
        <div className={styles.empty}>
          <p className={styles.emptyTitle}>Nothing to check</p>
          <p className={styles.emptyText}>New proposals will appear here.</p>
        </div>
      ) : (
        <div className={styles.list}>
          {visible.map(({ ss, kind }) => {
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
                    <span className={styles.rowName}>{ss.name}</span>
                    <span className={styles.rowMeta}>
                      {type?.name ?? "Stack"} · {ss.count}{" "}
                      {ss.count === 1 ? "source" : "sources"} · {ss.access} ·{" "}
                      {ss.updated}
                    </span>
                  </span>
                  <span className={`${styles.state} ${styles[`state_${kind}`]}`}>
                    {kindLabel(ss, kind)}
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
                    <button
                      type="button"
                      className={styles.reviewBtn}
                      onClick={() => onOpen(ss)}
                    >
                      {kind === "update" ? "Review update" : "Review"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
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
