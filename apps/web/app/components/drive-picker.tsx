"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  driveTree,
  getDrivePermissions,
  getDriveSelection,
  listDriveWorkspaces,
  putDriveSelection,
  refreshDriveWorkspaces,
  type DrivePermissionDetails,
  type DriveTreeItem,
  type DriveWorkspace,
} from "../lib/api";
import Icon from "./icons";
import modal from "./stacks.module.css";
import styles from "./drive-picker.module.css";

const FOLDER_MIME = "application/vnd.google-apps.folder";
type CheckState = "on" | "off" | "partial";

function TriBox({ state, disabled, onToggle }: { state: CheckState; disabled?: boolean; onToggle: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = state === "partial" }, [state]);
  return <input ref={ref} type="checkbox" checked={state === "on"} disabled={disabled} onChange={onToggle} aria-label="Toggle included" />;
}

function PermissionPanel({ details, onBack }: { details: DrivePermissionDetails; onBack: () => void }) {
  const enabled = Object.entries(details.capabilities).filter(([, value]) => value).map(([key]) => key.replace(/^can/, ""));
  return (
    <div className={styles.permissions}>
      <button className={styles.back} onClick={onBack}><Icon name="chevron-left" size={13} /> Back to files</button>
      <h3>{details.file.name}</h3>
      <p className={styles.muted}>{details.file.shared ? "Shared in Google Drive" : "Private in Google Drive"}</p>
      <div className={styles.permissionList}>
        {details.permissions.map((permission) => {
          const inherited = permission.permissionDetails?.some((item) => item.inherited);
          return (
            <div className={styles.permissionRow} key={permission.id}>
              <span><strong>{permission.displayName || permission.emailAddress || permission.domain || (permission.type === "anyone" ? "Anyone with the link" : permission.type)}</strong><small>{permission.type}{inherited ? " · inherited" : " · direct"}</small></span>
              <span className={styles.role}>{permission.role}</span>
            </div>
          );
        })}
      </div>
      <p className={styles.capabilities}><strong>Your effective capabilities:</strong> {enabled.length ? enabled.join(", ") : "view only"}</p>
      <p className={styles.muted}>Google Workspace groups are shown as groups. Member lists require separate Workspace directory access.</p>
    </div>
  );
}

export default function DrivePicker({ accountId, onClose }: { accountId: string; onClose: () => void }) {
  const [workspaces, setWorkspaces] = useState<DriveWorkspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [items, setItems] = useState<DriveTreeItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [shareAll, setShareAll] = useState(false);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [permissions, setPermissions] = useState<DrivePermissionDetails | null>(null);

  useEffect(() => {
    listDriveWorkspaces(accountId).then((rows) => { setWorkspaces(rows); setWorkspaceId(rows[0]?.id ?? null) }).catch((reason) => setError(reason instanceof Error ? reason.message : "Failed to load Drive workspaces"));
  }, [accountId]);

  useEffect(() => {
    if (!workspaceId) return;
    setItems(null); setPermissions(null); setExpanded(new Set()); setError(null);
    Promise.all([driveTree(workspaceId), getDriveSelection(workspaceId)])
      .then(([tree, selection]) => { setItems(tree.files); setShareAll(selection.configured && selection.share_all); setChecked(new Set(selection.file_ids)) })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Failed to load Drive"));
  }, [workspaceId]);

  const activeWorkspace = workspaces.find((workspace) => workspace.id === workspaceId) ?? null;
  const byId = useMemo(() => new Map((items ?? []).map((item) => [item.id, item])), [items]);
  const parentOf = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const item of items ?? []) map.set(item.id, (item.parents ?? []).filter((parent) => byId.has(parent)));
    return map;
  }, [items, byId]);
  const childrenOf = useMemo(() => {
    const map = new Map<string, DriveTreeItem[]>();
    for (const item of items ?? []) {
      const parent = (item.parents ?? []).find((id) => byId.has(id)) ?? "";
      map.set(parent, [...(map.get(parent) ?? []), item]);
    }
    for (const children of map.values()) children.sort((a, b) => Number(b.mimeType === FOLDER_MIME) - Number(a.mimeType === FOLDER_MIME) || a.name.localeCompare(b.name));
    return map;
  }, [items, byId]);
  const inherited = useMemo(() => {
    const result = new Set<string>();
    const stack = [...checked].filter((id) => byId.get(id)?.mimeType === FOLDER_MIME);
    while (stack.length) for (const child of childrenOf.get(stack.pop()!) ?? []) { if (!result.has(child.id)) { result.add(child.id); if (child.mimeType === FOLDER_MIME) stack.push(child.id) } }
    return result;
  }, [checked, byId, childrenOf]);
  const partial = useMemo(() => {
    const result = new Set<string>();
    const seen = new Set<string>();
    const stack = [...checked];
    while (stack.length) for (const parent of parentOf.get(stack.pop()!) ?? []) { if (!seen.has(parent)) { seen.add(parent); if (!checked.has(parent)) result.add(parent); stack.push(parent) } }
    for (const id of result) if (checked.has(id) || inherited.has(id)) result.delete(id);
    return result;
  }, [checked, parentOf, inherited]);

  const toggle = (item: DriveTreeItem) => {
    if (shareAll || inherited.has(item.id)) return;
    setChecked((current) => {
      const next = new Set(current);
      if (next.has(item.id)) next.delete(item.id);
      else {
        next.add(item.id);
        if (item.mimeType === FOLDER_MIME) {
          const stack = [item.id];
          while (stack.length) for (const child of childrenOf.get(stack.pop()!) ?? []) { next.delete(child.id); if (child.mimeType === FOLDER_MIME) stack.push(child.id) }
        }
      }
      return next;
    });
  };

  const showPermissions = async (item: DriveTreeItem) => {
    if (!workspaceId) return;
    setError(null);
    try { setPermissions(await getDrivePermissions(workspaceId, item.id)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : "permissions_failed") }
  };

  const renderNode = (item: DriveTreeItem, depth: number) => {
    const folder = item.mimeType === FOLDER_MIME;
    const open = expanded.has(item.id);
    const state: CheckState = shareAll || checked.has(item.id) || inherited.has(item.id) ? "on" : folder && partial.has(item.id) ? "partial" : "off";
    return (
      <div key={item.id}>
        <div className={styles.row} style={{ paddingLeft: 6 + depth * 18 }}>
          {folder ? <button className={`${styles.expander} ${open ? styles.expanderOpen : ""}`} onClick={() => setExpanded((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })}><Icon name="chevron-right" size={12} /></button> : <span className={styles.expanderSpacer} />}
          <TriBox state={state} disabled={shareAll || inherited.has(item.id)} onToggle={() => toggle(item)} />
          <span className={styles.rowIcon}><Icon name={folder ? "folder" : "file-text"} size={14} /></span>
          <span className={styles.rowLabel} title={item.name}>{item.name}</span>
          <button className={styles.accessButton} onClick={() => showPermissions(item)}>Access</button>
        </div>
        {folder && open && (childrenOf.get(item.id) ?? []).map((child) => renderNode(child, depth + 1))}
      </div>
    );
  };

  const save = async () => {
    if (!workspaceId) return;
    setSaving(true); setError(null);
    try { await putDriveSelection(workspaceId, shareAll, [...checked]); onClose() }
    catch (reason) { setError(reason instanceof Error ? reason.message : "save_failed"); setSaving(false) }
  };

  const refresh = async () => {
    setRefreshing(true); setError(null);
    try { const rows = await refreshDriveWorkspaces(accountId); setWorkspaces(rows); if (!rows.some((row) => row.id === workspaceId)) setWorkspaceId(rows[0]?.id ?? null) }
    catch (reason) { setError(reason instanceof Error ? reason.message : "refresh_failed") }
    finally { setRefreshing(false) }
  };

  return (
    <div>
      <div className={modal.modalHead}><h2 id="dialog-title" className={modal.modalTitle}>Google Drive access</h2><button onClick={onClose} className={modal.ghostBtn} aria-label="Close"><Icon name="x" /></button></div>
      <p className={modal.modalSub}>Choose what crosspod can read. This does not change sharing permissions in Google.</p>
      <div className={styles.workspaceBar}>
        {workspaces.map((workspace) => <button key={workspace.id} className={workspace.id === workspaceId ? styles.workspaceActive : ""} onClick={() => setWorkspaceId(workspace.id)}><strong>{workspace.name}</strong><small>{workspace.private ? "Only you" : "Shared Drive"}</small></button>)}
        <button onClick={refresh} disabled={refreshing}>{refreshing ? "Refreshing…" : "Refresh drives"}</button>
      </div>
      {error && <div role="alert" className={modal.error}>{error}</div>}
      {permissions ? <PermissionPanel details={permissions} onBack={() => setPermissions(null)} /> : (
        <>
          <label className={styles.shareAllRow}><input type="checkbox" checked={shareAll} onChange={(event) => setShareAll(event.target.checked)} />Include everything in {activeWorkspace?.name ?? "this Drive"}<span className={styles.shareAllMeta}>including new files</span></label>
          {items === null && !error && <p className={styles.muted}>Loading Drive…</p>}
          {items !== null && <div className={`${styles.tree} ${shareAll ? styles.treeDisabled : ""}`} role="tree">{(childrenOf.get("") ?? []).length ? (childrenOf.get("") ?? []).map((item) => renderNode(item, 0)) : <p className={styles.muted}>This Drive is empty.</p>}</div>}
        </>
      )}
      <div className={modal.modalFoot}><span className={styles.muted}>{shareAll ? `Everything in ${activeWorkspace?.name ?? "this Drive"} will be included.` : `${checked.size + inherited.size} items will be included.`}</span><button onClick={onClose} className={modal.actionBtn}>Cancel</button><button onClick={save} className={modal.primaryBtn} disabled={saving || !workspaceId}>{saving ? "Saving…" : "Save access"}</button></div>
    </div>
  );
}
