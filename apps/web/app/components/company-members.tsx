"use client";

import { useEffect, useState } from "react";
import { createInvitation, listInvitations, revokeInvitation, type AccountInvitation } from "../lib/api";
import styles from "./company-members.module.css";
import modal from "./stacks.module.css";
import Icon from "./icons";

export default function CompanyMembers({ accountId, domain, onClose }: { accountId: string; domain: string; onClose: () => void }) {
  const [email, setEmail] = useState("");
  const [items, setItems] = useState<AccountInvitation[]>([]);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = () => listInvitations(accountId).then(setItems).catch((reason) => setError(reason instanceof Error ? reason.message : "load_failed"));
  useEffect(() => { void load() }, [accountId]);

  const invite = async () => {
    setSaving(true); setError(null); setInviteUrl(null);
    try {
      const result = await createInvitation(accountId, email);
      setInviteUrl(result.invite_url ?? null);
      setEmail("");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "invite_failed") }
    finally { setSaving(false) }
  };

  return (
    <div>
      <div className={modal.modalHead}><h2 className={modal.modalTitle}>Invite company members</h2><button onClick={onClose} className={modal.ghostBtn}><Icon name="x" /></button></div>
      <p className={modal.modalSub}>Invite Google Workspace identities from {domain}. Each member signs in and connects Drive individually.</p>
      <div className={styles.form}><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder={`name@${domain}`} /><button onClick={invite} disabled={saving || !email}>{saving ? "Inviting…" : "Create invitation"}</button></div>
      {error && <div className={modal.error}>{error}</div>}
      {inviteUrl && <div className={styles.link}><span>Share this invitation link:</span><input readOnly value={inviteUrl} onFocus={(event) => event.currentTarget.select()} /></div>}
      <div className={styles.list}>{items.map((item) => <div key={item.id}><span><strong>{item.email}</strong><small>{item.status} · expires {new Date(item.expires_at).toLocaleDateString()}</small></span>{item.status === "pending" && <button onClick={() => revokeInvitation(accountId, item.id).then(load)}>Revoke</button>}</div>)}</div>
      <div className={modal.modalFoot}><button onClick={onClose} className={modal.primaryBtn}>Done</button></div>
    </div>
  );
}
