"use client";

import { useState } from "react";
import { driveConnectUrl, listDriveWorkspaces, loginUrl, syncDriveWorkspace, type Account, type Me } from "../lib/api";
import { track } from "../lib/analytics";
import Icon from "./icons";
import styles from "./sources.module.css";

export default function SourcesView({
  me,
  activeAccount,
  onManageWhatsApp,
  onManageDrive,
  onSynced,
}: {
  me: Me | null;
  activeAccount: Account | null;
  onManageWhatsApp: () => void;
  onManageDrive: () => void;
  onSynced: () => void;
}) {
  const [syncMsg, setSyncMsg] = useState("");
  const [syncState, setSyncState] = useState<{ done: number; total: number } | null>(null);
  const syncing = syncState !== null;
  const uploadedChats = me?.whatsapp_uploaded_chats ?? 0;

  const handleSync = async () => {
    if (!activeAccount || syncing) return;
    setSyncMsg("");
    setSyncState({ done: 0, total: 0 });
    const startedAt = performance.now();
    try {
      const workspaces = await listDriveWorkspaces(activeAccount.id);
      setSyncState({ done: 0, total: workspaces.length });
      track("drive_sync_started", { workspaces: workspaces.length });
      let synced = 0, ingested = 0;
      const errors: string[] = [];
      for (const [index, workspace] of workspaces.entries()) {
        const result = await syncDriveWorkspace(workspace.id);
        synced += result.synced;
        ingested += result.ingested;
        errors.push(...result.errors);
        setSyncState({ done: index + 1, total: workspaces.length });
      }
      track("drive_sync_completed", {
        workspaces: workspaces.length,
        synced,
        ingested,
        errors: errors.length,
        duration_ms: Math.round(performance.now() - startedAt),
      });
      if (workspaces.length === 0) {
        setSyncMsg("No Drive workspaces to sync.");
      } else {
        onSynced();
        setSyncMsg(errors.length > 0 ? `Synced ${synced} files, ingested ${ingested} · ${errors.length} error(s)` : `Synced ${synced} files, ingested ${ingested}`);
      }
    } catch (reason) {
      setSyncMsg(reason instanceof Error ? reason.message : "Sync failed.");
    } finally {
      setSyncState(null);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.headRow}>
        <p className={styles.subtitle}>Connection health and indexing freshness.</p>
      </div>

      {/* Connection summary cards */}
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
                    ? syncState.total > 1
                      ? `Syncing ${syncState.done}/${syncState.total}…`
                      : "Syncing…"
                    : "Sync now"}
                </button>
              </>
            ) : me && activeAccount ? (
              <a href={driveConnectUrl(activeAccount.id)} onClick={() => track("drive_connect_clicked", { account_type: activeAccount.account_type })}>Connect Drive</a>
            ) : (
              <a href={loginUrl}>Sign in to connect</a>
            )}
            {syncMsg && <span className={styles.connMeta} role="status" aria-live="polite">{syncMsg}</span>}
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
      </div>
    </div>
  );
}
