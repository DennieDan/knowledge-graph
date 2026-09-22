"use client";

import { useState } from "react";
import { driveConnectUrl, listDriveWorkspaces, loginUrl, syncDriveWorkspace, type Account, type Me } from "../lib/api";
import Icon from "./icons";
import styles from "./sources.module.css";

type SourceState = "Healthy" | "Stale" | "Gap";

const SOURCE_ROWS: {
  name: string;
  freshness: string;
  records: string;
  state: SourceState;
}[] = [
  { name: "Atlas / Drive", freshness: "18 min", records: "12", state: "Healthy" },
  { name: "Maya - Alex / WhatsApp", freshness: "2 min", records: "1 chat", state: "Healthy" },
  { name: "Nova / Drive", freshness: "3 days", records: "8", state: "Stale" },
  { name: "Supplier archive", freshness: "12 days", records: "24", state: "Gap" },
];

const VISIBILITY_GAPS = [
  { name: "Project Nova", reason: "Drive not refreshed", age: "3 days" },
  { name: "Supplier decisions", reason: "No linked chat", age: "12 days" },
];

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
  const [syncing, setSyncing] = useState(false);

  const handleSync = async () => {
    if (!activeAccount || syncing) return;
    setSyncing(true);
    setSyncMsg("");
    try {
      const workspaces = await listDriveWorkspaces(activeAccount.id);
      const results = await Promise.all(workspaces.map((workspace) => syncDriveWorkspace(workspace.id)));
      const ingested = results.reduce((total, result) => total + result.ingested, 0);
      const synced = results.reduce((total, result) => total + result.synced, 0);
      const errors = results.flatMap((result) => result.errors);
      setSyncMsg(errors.length > 0 ? `Synced ${synced} files, ingested ${ingested} · ${errors.length} error(s)` : `Synced ${synced} files, ingested ${ingested}`);
    } catch (reason) {
      setSyncMsg(reason instanceof Error ? reason.message : "Sync failed.");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className={styles.page}>
      {/* Subtitle + Add source */}
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
                <button type="button" onClick={handleSync} disabled={syncing}>
                  <Icon name="refresh-cw" size={13} /> {syncing ? "Syncing…" : "Sync now"}
                </button>
              </>
            ) : me && activeAccount ? (
              <a href={driveConnectUrl(activeAccount.id)}>Connect Drive</a>
            ) : (
              <a href={loginUrl}>Sign in to connect</a>
            )}
            {syncMsg && <span className={styles.connMeta}>{syncMsg}</span>}
          </div>
        </div>

        <div className={styles.connCard}>
          <p className={styles.connName}>WhatsApp</p>
          <div className={styles.connRow}>
            <span className={me?.whatsapp_linked ? styles.pillDark : styles.pillLight}>
              {me?.whatsapp_linked ? "Connected" : "Not linked"}
            </span>
            {me?.whatsapp_linked && (
              <span className={styles.connMeta}>WAHA session</span>
            )}
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
            <span className={styles.pillLight}>2 gaps</span>
            <span className={styles.connMeta}>Review</span>
          </div>
        </div>
      </div>

      {/* Table + Gaps panel */}
      <div className={styles.columns}>
        {/* Knowledge Inputs table */}
        <div className={styles.tableCard}>
          <p className={styles.panelLabel}>Knowledge Inputs</p>
          <table className={styles.table}>
            <colgroup>
              <col style={{ width: "44%" }} />
              <col style={{ width: "18%" }} />
              <col style={{ width: "16%" }} />
              <col style={{ width: "22%" }} />
            </colgroup>
            <thead>
              <tr>
                {["Source", "Freshness", "Records", "State"].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SOURCE_ROWS.map((row) => (
                <tr key={row.name}>
                  <td className={styles.cellSource}>{row.name}</td>
                  <td className={styles.cellMeta}>{row.freshness}</td>
                  <td className={styles.cellMeta}>{row.records}</td>
                  <td>
                    <StatePill state={row.state} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Visibility Gaps panel */}
        <div className={styles.gapsPanel}>
          <p className={styles.panelLabel}>Visibility Gaps</p>
          <h3 className={styles.gapsTitle}>What crosspod cannot see</h3>
          <div className={styles.gapList}>
            {VISIBILITY_GAPS.map((gap) => (
              <div key={gap.name} className={styles.gapCard}>
                <p className={styles.gapName}>{gap.name}</p>
                <p className={styles.gapReason}>{gap.reason}</p>
                <span className={styles.pillOutline}>{gap.age}</span>
              </div>
            ))}
          </div>
          <button className={styles.reviewBtn}>Review gaps</button>
        </div>
      </div>
    </div>
  );
}
