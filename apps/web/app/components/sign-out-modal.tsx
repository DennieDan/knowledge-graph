"use client";

import { useState } from "react";
import Icon from "./icons";
import modal from "./stacks.module.css";

export default function SignOutModal({
  email,
  onClose,
  onConfirm,
}: {
  email: string;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const handleSignOut = () => {
    setError("");
    setBusy(true);
    onConfirm()
      .catch((reason) => setError(reason instanceof Error ? reason.message : "You could not be signed out."))
      .finally(() => setBusy(false));
  };

  return (
    <div>
      <div className={modal.modalHead}>
        <h2 id="dialog-title" className={modal.modalTitle}>
          Sign out?
        </h2>
        <button onClick={onClose} className={modal.ghostBtn} aria-label="Close">
          <Icon name="x" />
        </button>
      </div>
      <p className={modal.modalSub}>You will be signed out of {email} on this device.</p>
      {error && (
        <div role="alert" className={modal.error}>
          {error}
        </div>
      )}
      <div className={modal.modalFoot}>
        <button onClick={onClose} className={modal.actionBtn} autoFocus>
          Cancel
        </button>
        <button onClick={handleSignOut} className={modal.primaryBtn} disabled={busy}>
          {busy ? "Signing out…" : "Sign out"}
        </button>
      </div>
    </div>
  );
}
