"use client";

import { useState } from "react";
import Icon from "./icons";
import styles from "./stacks.module.css";
import { DESCRIBABLE_STACK_TYPES, type StackType, type Substack } from "../lib/stacks";

function FieldLabel({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className={styles.fieldLabel}>
      {label}
      {children}
    </label>
  );
}

export function CreateSubstackModal({
  type,
  onClose,
  onSubmit,
}: {
  type: StackType;
  onClose: () => void;
  onSubmit: (input: { name: string; desc: string; generate: boolean }) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const generate = DESCRIBABLE_STACK_TYPES.has(type.id);

  const handleSubmit = () => {
    if (!name.trim()) {
      setError("Give this item a name.");
      return;
    }
    if (generate && !desc.trim()) {
      setError("Describe the record so it can be found in your files.");
      return;
    }
    setError("");
    setBusy(true);
    onSubmit({ name: name.trim(), desc: desc.trim(), generate })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "The record could not be created."))
      .finally(() => setBusy(false));
  };

  return (
    <div>
      <div className={styles.modalHead}>
        <h2 id="dialog-title" className={styles.modalTitle}>
          Add to {type.name}
        </h2>
        <button onClick={onClose} className={styles.ghostBtn} aria-label="Close">
          <Icon name="x" />
        </button>
      </div>
      <p className={styles.modalSub}>
        {generate
          ? "Describe a record that Analyze missed. It will be generated from your files as a proposal for you to check."
          : `Create a new item inside the ${type.name} stack.`}
      </p>
      <FieldLabel label="Name">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={`e.g. New ${type.name.slice(0, -1)}`}
          className={styles.input}
          autoFocus
        />
      </FieldLabel>
      <FieldLabel label={generate ? "Describe the record" : "Description"}>
        <textarea
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          placeholder={
            generate
              ? "What is it, and which files or chats mention it? e.g. PO 4471 from Acme for 500 brackets, in \"Acme PO 4471.pdf\" and the Acme WhatsApp chat."
              : "What is this item about?"
          }
          className={styles.textarea}
          rows={generate ? 5 : undefined}
        />
      </FieldLabel>
      {error && (
        <div role="alert" className={styles.error}>
          {error}
        </div>
      )}
      <div className={styles.modalFoot}>
        <button onClick={onClose} className={styles.actionBtn}>
          Cancel
        </button>
        <button onClick={handleSubmit} className={styles.primaryBtn} disabled={busy}>
          {generate ? (busy ? "Starting…" : "Generate record") : "Add item"} <Icon name="arrow-right" />
        </button>
      </div>
    </div>
  );
}

export function DeleteSubstackModal({
  substack,
  onClose,
  onConfirm,
}: {
  substack: Substack;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const handleDelete = () => {
    setError("");
    setBusy(true);
    onConfirm()
      .catch((reason) => setError(reason instanceof Error ? reason.message : "The substack could not be deleted."))
      .finally(() => setBusy(false));
  };

  return (
    <div>
      <div className={styles.modalHead}>
        <h2 id="dialog-title" className={styles.modalTitle}>
          Delete &ldquo;{substack.name}&rdquo;?
        </h2>
        <button onClick={onClose} className={styles.ghostBtn} aria-label="Close">
          <Icon name="x" />
        </button>
      </div>
      <p className={styles.modalSub}>This substack may be auto-generated in the future.</p>
      {error && (
        <div role="alert" className={styles.error}>
          {error}
        </div>
      )}
      <div className={styles.modalFoot}>
        <button onClick={onClose} className={styles.actionBtn}>
          Cancel
        </button>
        <button onClick={handleDelete} className={styles.dangerBtn} disabled={busy}>
          <Icon name="trash" /> {busy ? "Deleting…" : "Delete Substack"}
        </button>
      </div>
    </div>
  );
}
