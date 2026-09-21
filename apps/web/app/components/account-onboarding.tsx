"use client";

import { useState } from "react";
import { createAccount, loginUrl, loginWithInviteUrl, type Me } from "../lib/api";
import styles from "./account-onboarding.module.css";

export default function AccountOnboarding({ me, inviteToken, onCreated }: { me: Me | null; inviteToken: string | null; onCreated: () => void }) {
  const [type, setType] = useState<"personal" | "company" | null>(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!me) {
    return (
      <main className={styles.page}>
        <section className={styles.card}>
          <span className={styles.eyebrow}>crosspod</span>
          <h1>Turn company knowledge into checked records.</h1>
          <p>Continue with Google to create your account. Drive access is connected separately and remains optional.</p>
          <a className={styles.primary} href={inviteToken ? loginWithInviteUrl(inviteToken) : loginUrl}>Continue with Google</a>
        </section>
      </main>
    );
  }

  const submit = async () => {
    if (!type) return;
    setSaving(true);
    setError(null);
    try {
      await createAccount(type, name || undefined);
      onCreated();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "account_creation_failed");
      setSaving(false);
    }
  };

  return (
    <main className={styles.page}>
      <section className={styles.card}>
        <span className={styles.eyebrow}>Signed in as {me.email}</span>
        <h1>Create your workspace</h1>
        <p>Choose how you will use crosspod. You can connect Google Drive after setup.</p>
        <div className={styles.options}>
          <button className={type === "personal" ? styles.selected : ""} onClick={() => setType("personal")}>
            <strong>Personal</strong><span>Your private account and knowledge.</span>
          </button>
          <button disabled={!me.hosted_domain} className={type === "company" ? styles.selected : ""} onClick={() => setType("company")}>
            <strong>Company / Organization</strong><span>{me.hosted_domain ? `Google Workspace: ${me.hosted_domain}` : "Requires a Google Workspace identity"}</span>
          </button>
        </div>
        {type && (
          <label className={styles.field}>
            Workspace name
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder={type === "company" ? "Company name" : `${me.display_name ?? "My"} workspace`} />
          </label>
        )}
        {type === "company" && <p className={styles.note}>You will be the Company Admin. Additional employees join by invitation.</p>}
        {error && <p className={styles.error}>{error}</p>}
        <button className={styles.primaryButton} disabled={!type || saving} onClick={submit}>{saving ? "Creating…" : "Create account"}</button>
      </section>
    </main>
  );
}
