"use client";

import { useEffect, useState, type MouseEvent } from "react";
import Link from "next/link";
import Icon from "./icons";
import styles from "./to-check-view.module.css";
import type { StackType, Substack } from "../lib/stacks";
import type { ReviewFilter } from "../lib/routes";
import { reviewQueue, type QueueKind } from "../lib/review-queue";
import {
  dismissFinding,
  listFindings,
  type AnalysisRun,
  type FindingRow,
} from "../lib/api";

const FILTERS: [ReviewFilter, string][] = [
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
  analysisRuns,
  filter,
  onFilterChange,
  substackHref,
  onOpen,
  onConfirm,
  onAnalyze,
  onConfirmAll,
  onRetryAnalysis,
}: {
  accountId: string | null;
  stackTypes: StackType[];
  substacks: Substack[];
  busy: boolean;
  notice: string;
  analysisRuns: AnalysisRun[];
  filter: ReviewFilter;
  onFilterChange: (filter: ReviewFilter) => void;
  substackHref: (ss: Substack) => string;
  onOpen: (event: MouseEvent, href: string) => void;
  onConfirm: (ss: Substack) => void;
  onAnalyze: () => void;
  onConfirmAll: () => void;
  onRetryAnalysis: (runId: string) => void;
}) {
  const activeRun = analysisRuns.find((run) =>
    ["queued", "embedding", "discovering", "generating"].includes(run.status)
    || run.generation_queued > 0
    || run.generation_running > 0,
  );
  const failedRun = analysisRuns.find((run) => (run.status === "failed" || run.status === "partial") && run.generation_queued === 0 && run.generation_running === 0);
  const generationPercent = activeRun?.generation_total
    ? Math.round(((activeRun.generation_completed + activeRun.generation_failed) / activeRun.generation_total) * 100)
    : 0;
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

  const analyzing = Boolean(activeRun);
  useEffect(() => {
    if (!analyzing) refreshFindings();
  }, [accountId, analyzing]);

  const queue = reviewQueue(substacks, "all");
  const visible = reviewQueue(substacks, filter);
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
              <Icon name="activity" size={17} />
            </span>
            Analyze workspace
          </h1>
          <p className={styles.subtitle}>Analyze sources, then check the proposals and findings they produce.</p>
        </div>
        <div className={styles.heroActions}>
          <span className={styles.chip}>
            {total} {total === 1 ? "item" : "items"} to check
          </span>
          <button type="button" onClick={onConfirmAll} disabled={busy} className={styles.ghostBtn}>
            <Icon name="check" size={13} /> Confirm all
          </button>
          <button type="button" onClick={onAnalyze} disabled={busy || Boolean(activeRun)} className={styles.confirmBtn}>
            <Icon name="activity" size={13} /> {activeRun ? "Analyzing…" : "Analyze workspace"}
          </button>
        </div>
      </div>

      {activeRun && (
        <div className={styles.analysisStatus} role="status" aria-live="polite">
          <div className={styles.analysisSummary}>
            <strong>{activeRun.generation_total > 0 ? "Generating LLM reports" : activeRun.status === "queued" ? "Analysis queued" : `${activeRun.status[0]!.toUpperCase()}${activeRun.status.slice(1)} knowledge`}</strong>
            <span>{activeRun.documents_processed}/{activeRun.documents_total} documents analyzed · {activeRun.chunks_embedded} chunks embedded · {activeRun.candidates_found} records found</span>
          </div>
          {activeRun.generation_total > 0 && (
            <div className={styles.generationProgress}>
              <div className={styles.progressLabels}>
                <span>LLM content</span>
                <strong>{activeRun.generation_completed}/{activeRun.generation_total} generated</strong>
              </div>
              <div className={styles.progressTrack} role="progressbar" aria-label="LLM content generation" aria-valuemin={0} aria-valuemax={activeRun.generation_total} aria-valuenow={activeRun.generation_completed + activeRun.generation_failed}>
                <span style={{ width: `${generationPercent}%` }} />
              </div>
              <span>{activeRun.generation_running > 0 ? `${activeRun.generation_running} generating · ` : ""}{activeRun.generation_queued} queued{activeRun.generation_failed > 0 ? ` · ${activeRun.generation_failed} failed` : ""}</span>
            </div>
          )}
        </div>
      )}
      {!activeRun && failedRun && (
        <div className={styles.analysisStatus} role="status">
          <span>Analysis needs attention. {failedRun.failures} job{failedRun.failures === 1 ? "" : "s"} failed.</span>
          <button type="button" onClick={() => onRetryAnalysis(failedRun.id)} disabled={busy}>Retry</button>
        </div>
      )}

      <div className={styles.filterRow} role="group" aria-label="Filter queue">
        {FILTERS.map(([kind, label]) => (
          <button
            key={kind}
            type="button"
            aria-pressed={filter === kind}
            onClick={() => onFilterChange(kind)}
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
              const href = substackHref(ss);
              return (
                <div key={ss.id} className={styles.row}>
                  <Link
                    href={href}
                    scroll={false}
                    className={styles.rowMain}
                    onClick={(event) => onOpen(event, href)}
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
                  </Link>
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
                      <Link href={href} scroll={false} className={styles.reviewBtn} onClick={(event) => onOpen(event, href)}>
                        {kind === "update" ? "Review update" : "Review"}
                      </Link>
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
