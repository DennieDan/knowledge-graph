"use client";

import { useEffect, useState } from "react";
import {
  driveConnectUrl,
  listDriveWorkspaces,
  loginUrl,
  syncDriveWorkspace,
  type Account,
  type DriveWorkspace,
  type Me,
} from "../lib/api";
import { track } from "../lib/analytics";
import Icon from "./icons";
import styles from "./sources.module.css";

export default function SourcesView({
  me,
  activeAccount,
  onManageWhatsApp,
  onManageDrive,
}: {
  me: Me | null;
  activeAccount: Account | null;
  onManageWhatsApp: () => void;
  onManageDrive: () => void;
}) {
  const [syncMsg, setSyncMsg] = useState("");
  const [syncState, setSyncState] = useState<{ done: number; total: number } | null>(null);
  const [workspaces, setWorkspaces] = useState<DriveWorkspace[]>([]);
  const syncing = syncState !== null;
  const uploadedChats = me?.whatsapp_uploaded_chats ?? 0;

  const refresh = () => {
    if (!activeAccount?.drive_linked) {
      setWorkspaces([]);
      return;
    }
    listDriveWorkspaces(activeAccount.id)
      .then(setWorkspaces)
      .catch(() => setWorkspaces([]));
  };

  useEffect(() => {
    refresh();
  }, [activeAccount?.id, activeAccount?.drive_linked]);

  const handleSync = async () => {
    if (!activeAccount || syncing) return;
    setSyncMsg("");
    setSyncState({ done: 0, total: 0 });
    const startedAt = performance.now();
    try {
      const rows = await listDriveWorkspaces(activeAccount.id);
      setWorkspaces(rows);
      setSyncState({ done: 0, total: rows.length });
      track("drive_sync_started", { workspaces: rows.length });
      let queued = 0;
      for (const [index, workspace] of rows.entries()) {
        const result = await syncDriveWorkspace(workspace.id);
        if (result.queued) queued += 1;
        setSyncState({ done: index + 1, total: rows.length });
      }
      track("drive_sync_completed", {
        workspaces: rows.length,
        queued,
        duration_ms: Math.round(performance.now() - startedAt),
      });
      if (rows.length === 0) {
        setSyncMsg("No Drive workspaces to sync.");
      } else {
        setSyncMsg(`Queued ${queued} sync job(s). Worker will update freshness.`);
      }
      refresh();
    } catch (reason) {
      setSyncMsg(reason instanceof Error ? reason.message : "Sync failed.");
    } finally {
      setSyncState(null);
    }
  };

  const failed = workspaces.filter((row) => row.health === "failed");
  const stale = workspaces.filter((row) => row.health === "stale");

  return (
    <div className={styles.page}>
      <div className={styles.headRow}>
        <p className={styles.subtitle}>Connection health and indexing freshness.</p>
      </div>

      <div className={styles.connGrid}>
        <div className={styles.connCard}>
          <p className={styles.connName}>Google Drive</p>
          <div className={styles.connRow}>
            <span className={activeAccount?.drive_linked ? styles.pillDark : styles.pillLight}>
              {activeAccount?.drive_linked ? "Connected" : "Not linked"}
            </span>
            {activeAccount?.drive_linked && (
              <span className={styles.connMeta}>{activeAccount.name}</span>
            )}
          </div>
          <div className={styles.connAction}>
            {activeAccount?.drive_linked ? (
              <>
                <button type="button" onClick={onManageDrive}>
                  <Icon name="settings" size={13} /> Manage access
                </button>
                <button type="button" onClick={handleSync} disabled={syncing} aria-busy={syncing}>
                  <span className={syncing ? styles.spinning : undefined}>
                    <Icon name="refresh-cw" size={13} />
                  </span>
                  {syncing
                    ? syncState && syncState.total > 1
                      ? `Queueing ${syncState.done}/${syncState.total}…`
                      : "Queueing…"
                    : "Sync now"}
                </button>
              </>
            ) : me && activeAccount ? (
              <a href={driveConnectUrl(activeAccount.id)} onClick={() => track("drive_connect_clicked", { account_type: activeAccount.account_type })}>Connect Drive</a>
            ) : (
              <a href={loginUrl}>Sign in to connect</a>
            )}
            {syncMsg && (
              <span className={styles.connMeta} role="status" aria-live="polite">
                {syncMsg}
              </span>
            )}
          </div>
        </div>

        <div className={styles.connCard}>
          <p className={styles.connName}>WhatsApp</p>
          <div className={styles.connRow}>
            <span className={me?.whatsapp_linked ? styles.pillDark : styles.pillLight}>
              {me?.whatsapp_linked ? "Connected" : uploadedChats > 0 ? "Chats uploaded" : "Not linked"}
            </span>
            {me?.whatsapp_linked ? (
              <span className={styles.connMeta}>Live sync</span>
            ) : uploadedChats > 0 && (
              <span className={styles.connMeta}>
                {uploadedChats} chat{uploadedChats === 1 ? "" : "s"} · no live sync
              </span>
            )}
          </div>
          <div className={styles.connAction}>
            {me ? (
              <button type="button" onClick={onManageWhatsApp}>
                {me.whatsapp_linked ? "Manage / import chats" : uploadedChats > 0 ? "Manage chats" : "Connect"}
              </button>
            ) : (
              <a href={loginUrl}>Sign in to connect</a>
            )}
          </div>
        </div>

        <div className={styles.connCard}>
          <p className={styles.connName}>Coverage</p>
          <div className={styles.connRow}>
            <span className={styles.pillLight}>
              {failed.length + stale.length} gap{failed.length + stale.length === 1 ? "" : "s"}
            </span>
            <span className={styles.connMeta}>Drive health</span>
          </div>
        </div>
      </div>
    </div>
  );
}
