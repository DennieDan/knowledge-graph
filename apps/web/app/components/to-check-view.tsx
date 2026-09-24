"use client";

import { useEffect, useRef, useState, type MouseEvent } from "react";
import Link from "next/link";
import Icon from "./icons";
import MultiSelectChip from "./multi-select-chip";
import styles from "./to-check-view.module.css";
import type { StackType, Substack } from "../lib/stacks";
import type { ReviewFilter, ReviewState } from "../lib/routes";
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

const PAGE_SIZE = 20;

type Entry =
  | { key: string; ss: Substack; kind: QueueKind }
  | { key: string; finding: FindingRow };

function kindLabel(ss: Substack, kind: QueueKind): string {
  if (ss.reviewState === "generation_error") return "Generation failed";
  return KIND_LABEL[kind];
}

/** Page numbers to show, with "…" gaps: 1 … 4 5 6 … 12. */
function pageList(current: number, count: number): (number | "…")[] {
  const pages = [...new Set([1, current - 1, current, current + 1, count])]
    .filter((page) => page >= 1 && page <= count)
    .sort((a, b) => a - b);
  return pages.flatMap((page, i) => (i > 0 && page - pages[i - 1]! > 1 ? ["…" as const, page] : [page]));
}

export default function ToCheckView({
  accountId,
  stackTypes,
  substacks,
  busy,
  notice,
  analysisRuns,
  review,
  onReviewChange,
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
  review: ReviewState;
  onReviewChange: (review: ReviewState) => void;
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

  const { filter, types } = review;
  const listRef = useRef<HTMLDivElement>(null);
  const total = reviewQueue(substacks, { filter: "all", types: [] }).length + findings.length;

  // Every entry for the current queue kind, before the stack type filter.
  const typeOfSubstack = new Map(substacks.map((ss) => [ss.id, ss.typeId]));
  const findingType = (finding: FindingRow) =>
    finding.subject_kind === "substack" ? typeOfSubstack.get(finding.subject_id) ?? null : null;
  const kindEntries: { entry: Entry; typeId: string | null }[] = [
    ...(filter === "findings" ? [] : reviewQueue(substacks, { filter, types: [] })).map(({ ss, kind }) => ({
      entry: { key: ss.id, ss, kind },
      typeId: ss.typeId,
    })),
    ...(filter === "all" || filter === "findings" ? findings : []).map((finding) => ({
      entry: { key: `finding-${finding.id}`, finding },
      typeId: findingType(finding),
    })),
  ];
  const entries = kindEntries
    .filter((item) => types.length === 0 || (item.typeId !== null && types.includes(item.typeId)))
    .map((item) => item.entry);

  const typeOptions = stackTypes.map((type) => ({
    value: type.id,
    label: type.name,
    icon: type.icon,
    count: kindEntries.filter((item) => item.typeId === type.id).length,
  }));

  const pageCount = Math.max(1, Math.ceil(entries.length / PAGE_SIZE));
  const page = Math.min(review.page, pageCount);
  const pageStart = (page - 1) * PAGE_SIZE;
  const pageEntries = entries.slice(pageStart, pageStart + PAGE_SIZE);

  const goToPage = (next: number) => {
    onReviewChange({ ...review, page: next });
    listRef.current?.scrollIntoView({ block: "start" });
  };

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
            onClick={() => onReviewChange({ ...review, filter: kind, page: 1 })}
            className={`${styles.filterChip} ${filter === kind ? styles.filterChipActive : ""}`}
          >
            {label}
          </button>
        ))}
        <span className={styles.filterDivider} aria-hidden="true" />
        <MultiSelectChip
          label="Stack type"
          options={typeOptions}
          selected={types}
          onChange={(next) => onReviewChange({ ...review, types: next, page: 1 })}
        />
      </div>

      {entries.length === 0 ? (
        <div className={styles.empty}>
          <p className={styles.emptyTitle}>Nothing to check</p>
          <p className={styles.emptyText}>
            {types.length ? "No items match the selected stack types." : "New proposals will appear here."}
          </p>
        </div>
      ) : (
        <div ref={listRef} className={styles.list}>
          {pageEntries.map((entry) => {
              if (!("ss" in entry)) {
                const { finding } = entry;
                return (
                  <div key={entry.key} className={styles.row}>
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
                );
              }
              const { ss, kind } = entry;
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
        </div>
      )}

      {entries.length > PAGE_SIZE && (
        <nav className={styles.pager} aria-label="Pagination">
          <span className={styles.pagerRange}>
            {pageStart + 1}–{pageStart + pageEntries.length} of {entries.length}
          </span>
          <div className={styles.pagerButtons}>
            <button
              type="button"
              className={styles.pageBtn}
              disabled={page === 1}
              onClick={() => goToPage(page - 1)}
              aria-label="Previous page"
            >
              <Icon name="chevron-left" size={14} />
            </button>
            {pageList(page, pageCount).map((item, i) =>
              item === "…" ? (
                <span key={`gap-${i}`} className={styles.pageGap}>…</span>
              ) : (
                <button
                  key={item}
                  type="button"
                  className={`${styles.pageBtn} ${item === page ? styles.pageBtnActive : ""}`}
                  aria-current={item === page ? "page" : undefined}
                  onClick={() => goToPage(item)}
                >
                  {item}
                </button>
              ),
            )}
            <button
              type="button"
              className={styles.pageBtn}
              disabled={page === pageCount}
              onClick={() => goToPage(page + 1)}
              aria-label="Next page"
            >
              <Icon name="chevron-right" size={14} />
            </button>
          </div>
        </nav>
      )}

      {notice && (
        <div role="status" aria-live="polite" className={styles.notice}>
          {notice}
        </div>
      )}
    </div>
  );
}
