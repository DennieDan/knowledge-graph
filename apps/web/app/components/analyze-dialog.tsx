"use client";

import { useEffect, useMemo, useState } from "react";
import { getAnalysisPlan, type AnalysisPlan, type AnalysisRecord, type RegenerateMode } from "../lib/api";
import { STACK_TYPES } from "../lib/stacks";
import Icon from "./icons";
import modal from "./stacks.module.css";
import styles from "./analyze-dialog.module.css";

const typeName = (typeId: string) => STACK_TYPES.find((type) => type.id === typeId)?.name ?? typeId;

function RecordList({ records, checked, onToggle }: {
  records: AnalysisRecord[];
  checked?: Set<string>;
  onToggle?: (id: string) => void;
}) {
  if (!records.length) return <p className={styles.muted}>No records.</p>;
  return (
    <div className={styles.list}>
      {records.map((record) => (
        <label key={record.id} className={styles.row}>
          {checked && onToggle && (
            <input type="checkbox" checked={checked.has(record.id)} onChange={() => onToggle(record.id)} />
          )}
          <span className={styles.rowLabel} title={record.name}>{record.name}</span>
          <span className={styles.badge}>{typeName(record.type_id)}</span>
        </label>
      ))}
    </div>
  );
}

export default function AnalyzeDialog({ accountId, onClose, onStart }: {
  accountId: string;
  onClose: () => void;
  onStart: (mode: RegenerateMode, substackIds: string[]) => Promise<void>;
}) {
  const [plan, setPlan] = useState<AnalysisPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<RegenerateMode>("affected");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    getAnalysisPlan(accountId)
      .then((result) => {
        setPlan(result);
        setMode(result.changed_documents.length ? "affected" : "selected");
        setChecked(new Set(result.affected_records.map((record) => record.id)));
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Could not check for changes."));
  }, [accountId]);

  const visible = useMemo(() => {
    const query = filter.trim().toLowerCase();
    return (plan?.records ?? []).filter((record) =>
      !query || `${record.name} ${typeName(record.type_id)}`.toLowerCase().includes(query));
  }, [plan, filter]);

  const changed = plan?.changed_documents ?? [];
  const allVisibleChecked = visible.length > 0 && visible.every((record) => checked.has(record.id));
  const toggle = (id: string) => setChecked((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
  const toggleVisible = () => setChecked((current) => {
    const next = new Set(current);
    for (const record of visible) {
      if (allVisibleChecked) next.delete(record.id);
      else next.add(record.id);
    }
    return next;
  });

  const summary = !plan ? "" : [
    changed.length ? `${changed.length} changed file${changed.length === 1 ? "" : "s"} will be re-embedded and scanned` : null,
    mode === "affected" ? `${plan.affected_records.length} affected record${plan.affected_records.length === 1 ? "" : "s"} regenerated`
      : mode === "all" ? `all ${plan.records.length} records regenerated`
      : `${checked.size} record${checked.size === 1 ? "" : "s"} regenerated`,
  ].filter(Boolean).join(" · ");
  const canStart = Boolean(plan) && !starting && (mode !== "selected" || checked.size > 0) && (mode !== "all" || plan!.records.length > 0);

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      await onStart(mode, mode === "selected" ? [...checked] : []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Analysis could not be started.");
      setStarting(false);
    }
  };

  const option = (value: RegenerateMode, title: string, description: string) => (
    <label className={`${styles.option} ${mode === value ? styles.optionActive : ""}`}>
      <input type="radio" name="regenerate" checked={mode === value} onChange={() => setMode(value)} />
      <span><strong>{title}</strong><small>{description}</small></span>
    </label>
  );

  return (
    <div>
      <div className={modal.modalHead}>
        <h2 id="dialog-title" className={modal.modalTitle}>Analyze workspace</h2>
        <button onClick={onClose} className={modal.ghostBtn} aria-label="Close"><Icon name="x" /></button>
      </div>
      <p className={modal.modalSub}>Only files that changed since the last analysis are re-embedded. Choose which records the LLM regenerates.</p>
      {error && <div role="alert" className={modal.error}>{error}</div>}
      {!plan && !error && <p className={styles.muted}>Checking for changes…</p>}
      {plan && (
        <>
          <h3 className={styles.heading}>Changed files</h3>
          {changed.length ? (
            <div className={styles.list}>
              {changed.map((document) => (
                <div key={document.id} className={styles.row}>
                  <Icon name="file-text" size={14} />
                  <span className={styles.rowLabel} title={document.title}>{document.title}</span>
                  <span className={`${styles.badge} ${document.change === "new" ? styles.badgeNew : ""}`}>
                    {document.change === "new" ? "New" : `Updated · rev ${document.revision}`}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className={styles.muted}>No files changed since the last analysis. Nothing needs re-embedding.</p>
          )}

          <h3 className={styles.heading}>Regenerate</h3>
          <div className={styles.options}>
            {changed.length > 0 && option("affected", `Affected records (${plan.affected_records.length})`, "Records mentioned in the changed files. Newly found records are always generated.")}
            {option("selected", "Choose records", "Pick exactly which records to regenerate.")}
            {option("all", `All records (${plan.records.length})`, "Regenerate every Sales Order, Client and Item. One LLM call per record.")}
          </div>

          {mode === "affected" && <RecordList records={plan.affected_records} />}
          {mode === "selected" && (
            <>
              <div className={styles.toolbar}>
                <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter records" aria-label="Filter records" />
                <button onClick={toggleVisible} disabled={!visible.length}>{allVisibleChecked ? "Clear shown" : "Select shown"}</button>
              </div>
              <RecordList records={visible} checked={checked} onToggle={toggle} />
            </>
          )}
        </>
      )}
      <div className={modal.modalFoot}>
        <span className={styles.muted}>{summary}</span>
        <button onClick={onClose} className={modal.actionBtn}>Cancel</button>
        <button onClick={start} className={modal.primaryBtn} disabled={!canStart}>{starting ? "Starting…" : "Start analysis"}</button>
      </div>
    </div>
  );
}
