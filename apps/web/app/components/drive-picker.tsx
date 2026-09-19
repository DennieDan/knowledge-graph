"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "./icons";
import {
  driveTree,
  getDriveSelection,
  putDriveSelection,
  type DriveTreeItem,
} from "../lib/api";
import modal from "./stacks.module.css";
import styles from "./drive-picker.module.css";

const FOLDER_MIME = "application/vnd.google-apps.folder";

type CheckState = "on" | "off" | "partial";

function TriBox({
  state,
  disabled,
  onToggle,
}: {
  state: CheckState;
  disabled?: boolean;
  onToggle: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = state === "partial";
  }, [state]);
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={state === "on"}
      disabled={disabled}
      onChange={onToggle}
      aria-label="Toggle shared"
    />
  );
}

export default function DrivePicker({ onClose }: { onClose: () => void }) {
  const [items, setItems] = useState<DriveTreeItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [shareAll, setShareAll] = useState(false);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    Promise.all([driveTree(), getDriveSelection()])
      .then(([tree, sel]) => {
        setItems(tree.files);
        // Unconfigured means the user hasn't chosen yet — fail closed
        // rather than pre-ticking "Share entire Google Drive".
        setShareAll(sel.configured && sel.share_all);
        setChecked(new Set(sel.file_ids));
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load Drive"),
      );
  }, []);

  const byId = useMemo(
    () => new Map((items ?? []).map((i) => [i.id, i])),
    [items],
  );

  const parentOf = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const it of items ?? []) {
      m.set(
        it.id,
        (it.parents ?? []).filter((p) => byId.has(p)),
      );
    }
    return m;
  }, [items, byId]);

  const childrenOf = useMemo(() => {
    const m = new Map<string, DriveTreeItem[]>();
    for (const it of items ?? []) {
      const pid = (it.parents ?? []).find((p) => byId.has(p)) ?? "";
      const arr = m.get(pid) ?? [];
      arr.push(it);
      m.set(pid, arr);
    }
    for (const arr of m.values()) {
      arr.sort(
        (a, b) =>
          Number(b.mimeType === FOLDER_MIME) -
            Number(a.mimeType === FOLDER_MIME) || a.name.localeCompare(b.name),
      );
    }
    return m;
  }, [items, byId]);

  const roots = childrenOf.get("") ?? [];

  // Descendants of checked folders are shared implicitly and locked on.
  const inherited = useMemo(() => {
    const s = new Set<string>();
    const stack = [...checked].filter(
      (id) => byId.get(id)?.mimeType === FOLDER_MIME,
    );
    while (stack.length) {
      const fid = stack.pop()!;
      for (const child of childrenOf.get(fid) ?? []) {
        if (s.has(child.id)) continue;
        s.add(child.id);
        if (child.mimeType === FOLDER_MIME) stack.push(child.id);
      }
    }
    return s;
  }, [checked, childrenOf, byId]);

  // Folders that contain checked items but aren't fully shared themselves.
  const partial = useMemo(() => {
    const p = new Set<string>();
    const seen = new Set<string>();
    const stack = [...checked];
    while (stack.length) {
      const id = stack.pop()!;
      for (const pid of parentOf.get(id) ?? []) {
        if (seen.has(pid)) continue;
        seen.add(pid);
        if (!checked.has(pid)) p.add(pid);
        stack.push(pid);
      }
    }
    for (const id of [...p]) {
      if (checked.has(id) || inherited.has(id)) p.delete(id);
    }
    return p;
  }, [checked, parentOf, inherited]);

  const sharedCount = useMemo(
    () =>
      shareAll
        ? (items?.length ?? 0)
        : (items ?? []).filter(
            (i) => checked.has(i.id) || inherited.has(i.id),
          ).length,
    [shareAll, items, checked, inherited],
  );

  const toggleExpand = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggle = (item: DriveTreeItem) => {
    if (shareAll || inherited.has(item.id)) return;
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(item.id)) {
        next.delete(item.id);
      } else {
        next.add(item.id);
        // A shared folder covers its subtree — drop redundant child picks.
        if (item.mimeType === FOLDER_MIME) {
          const stack = [item.id];
          while (stack.length) {
            for (const c of childrenOf.get(stack.pop()!) ?? []) {
              next.delete(c.id);
              if (c.mimeType === FOLDER_MIME) stack.push(c.id);
            }
          }
        }
      }
      return next;
    });
  };

  const stateOf = (item: DriveTreeItem): CheckState => {
    if (shareAll || checked.has(item.id) || inherited.has(item.id)) return "on";
    if (item.mimeType === FOLDER_MIME && partial.has(item.id)) return "partial";
    return "off";
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await putDriveSelection(shareAll, [...checked]);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "save_failed");
      setSaving(false);
    }
  };

  const renderNode = (item: DriveTreeItem, depth: number) => {
    const isFolder = item.mimeType === FOLDER_MIME;
    const kids = childrenOf.get(item.id) ?? [];
    const open = expanded.has(item.id);
    const locked = shareAll || inherited.has(item.id);
    return (
      <div key={item.id}>
        <div className={styles.row} style={{ paddingLeft: 6 + depth * 18 }}>
          {isFolder ? (
            <button
              type="button"
              className={`${styles.expander} ${open ? styles.expanderOpen : ""}`}
              onClick={() => toggleExpand(item.id)}
              aria-label={open ? `Collapse ${item.name}` : `Expand ${item.name}`}
            >
              <Icon name="chevron-right" size={12} />
            </button>
          ) : (
            <span className={styles.expanderSpacer} />
          )}
          <TriBox
            state={stateOf(item)}
            disabled={locked}
            onToggle={() => toggle(item)}
          />
          <span className={styles.rowIcon}>
            <Icon name={isFolder ? "folder" : "file-text"} size={14} />
          </span>
          <span className={styles.rowLabel} title={item.name}>
            {item.name}
          </span>
        </div>
        {isFolder && open && kids.map((k) => renderNode(k, depth + 1))}
      </div>
    );
  };

  return (
    <div>
      <div className={modal.modalHead}>
        <h2 id="dialog-title" className={modal.modalTitle}>
          Google Drive access
        </h2>
        <button onClick={onClose} className={modal.ghostBtn} aria-label="Close">
          <Icon name="x" />
        </button>
      </div>
      <p className={modal.modalSub}>
        Choose the folders and files crosspod can read. Sharing a folder
        includes everything inside it.
      </p>

      {error && (
        <div role="alert" className={modal.error}>
          {error}
        </div>
      )}

      <label className={styles.shareAllRow}>
        <input
          type="checkbox"
          checked={shareAll}
          onChange={(e) => setShareAll(e.target.checked)}
        />
        Share entire Google Drive
        <span className={styles.shareAllMeta}>including new files</span>
      </label>

      {items === null && !error && (
        <p className={styles.muted}>Loading your Drive…</p>
      )}
      {items !== null && (
        <div
          className={`${styles.tree} ${shareAll ? styles.treeDisabled : ""}`}
          role="tree"
          aria-label="Drive folders and files"
        >
          {roots.length === 0 && (
            <p className={styles.muted}>Your Drive is empty.</p>
          )}
          {roots.map((item) => renderNode(item, 0))}
        </div>
      )}

      <div className={modal.modalFoot}>
        <span className={styles.muted}>
          {shareAll
            ? "Everything in this Drive will be shared."
            : `${sharedCount} item${sharedCount === 1 ? "" : "s"} will be shared.`}
        </span>
        <button onClick={onClose} className={modal.actionBtn}>
          Cancel
        </button>
        <button onClick={save} className={modal.primaryBtn} disabled={saving}>
          {saving ? "Saving…" : "Save access"}
        </button>
      </div>
    </div>
  );
}
