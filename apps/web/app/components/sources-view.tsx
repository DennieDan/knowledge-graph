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

type SourceState = "Healthy" | "Stale" | "Failed";

function healthLabel(health?: DriveWorkspace["health"]): SourceState {
  if (health === "failed") return "Failed";
  if (health === "stale") return "Stale";
  return "Healthy";
}

function freshnessText(workspace: DriveWorkspace): string {
  if (workspace.last_error) {
    return workspace.last_error.split(":")[0] || "Error";
  }
  if (!workspace.last_success_at) return "Never synced";
  const ageMs = Date.now() - new Date(workspace.last_success_at).getTime();
  const minutes = Math.round(ageMs / 60000);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hr`;
  return `${Math.round(hours / 24)} days`;
}

function StatePill({ state }: { state: SourceState }) {
  return <span className={styles.pillOutline}>{state}</span>;
}

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
        <p className={styles.subtitle}>
          Connection health, indexing freshness, and visibility gaps.
        </p>
        {me ? (
          <button onClick={onManageWhatsApp} className={styles.addSource}>
            Add source
          </button>
        ) : (
          <a href={loginUrl} className={styles.addSource}>
            Sign in to add
          </a>
        )}
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
              {me?.whatsapp_linked ? "Connected" : "Not linked"}
            </span>
            {me?.whatsapp_linked && <span className={styles.connMeta}>WAHA session</span>}
          </div>
          <div className={styles.connAction}>
            {me ? (
              <button type="button" onClick={onManageWhatsApp}>
                {me.whatsapp_linked ? "Manage / import chats" : "Connect"}
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

      <div className={styles.columns}>
        <div className={styles.tableCard}>
          <p className={styles.panelLabel}>Knowledge Inputs</p>
          <table className={styles.table}>
            <thead>
              <tr>
                {["Source", "Freshness", "Kind", "State"].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {workspaces.length === 0 ? (
                <tr>
                  <td className={styles.cellMeta} colSpan={4}>
                    No Drive workspaces yet.
                  </td>
                </tr>
              ) : (
                workspaces.map((row) => (
                  <tr key={row.id}>
                    <td className={styles.cellSource}>{row.name}</td>
                    <td className={styles.cellMeta}>{freshnessText(row)}</td>
                    <td className={styles.cellMeta}>{row.kind}</td>
                    <td>
                      <StatePill state={healthLabel(row.health)} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className={styles.gapsPanel}>
          <p className={styles.panelLabel}>Visibility Gaps</p>
          <h3 className={styles.gapsTitle}>Failed or stale sources</h3>
          <div className={styles.gapList}>
            {[...failed, ...stale].length === 0 ? (
              <p className={styles.gapReason}>No gaps right now.</p>
            ) : (
              [...failed, ...stale].map((gap) => (
                <div key={gap.id} className={styles.gapCard}>
                  <p className={styles.gapName}>{gap.name}</p>
                  <p className={styles.gapReason}>
                    {gap.last_error || "Missed a sync schedule"}
                  </p>
                  <span className={styles.pillOutline}>{healthLabel(gap.health)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
