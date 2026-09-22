"use client";

import { useState } from "react";
import Icon from "./icons";
import styles from "./stacks.module.css";
import type { StackType } from "../lib/stacks";

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
  onSubmit: (input: { name: string; desc: string }) => void;
}) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = () => {
    if (!name.trim()) {
      setError("Give this item a name.");
      return;
    }
    onSubmit({ name: name.trim(), desc: desc.trim() });
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
        Create a new item inside the {type.name} stack. It will be visible to
        your workspace.
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
      <FieldLabel label="Description · Optional">
        <textarea
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          placeholder="What is this item about?"
          className={styles.textarea}
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
        <button onClick={handleSubmit} className={styles.primaryBtn}>
          Add item <Icon name="arrow-right" />
        </button>
      </div>
    </div>
  );
}
