"use client";

import { useState } from "react";
import Icon from "./icons";
import styles from "./stacks.module.css";
import type { StackType, Substack } from "../lib/stacks";

function Chip({ children }: { children: React.ReactNode }) {
  return <span className={styles.chip}>{children}</span>;
}

function DetailBlock({ children }: { children: React.ReactNode }) {
  return <div className={styles.detailBlock}>{children}</div>;
}

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

export function SubstackDetails({
  ss,
  type,
  onClose,
}: {
  ss: Substack;
  type: StackType;
  onClose: () => void;
}) {
  return (
    <div>
      <div className={styles.modalHead}>
        <span className={styles.tileIcon}>
          <Icon name={type.icon} size={18} />
        </span>
        <button onClick={onClose} className={styles.ghostBtn} aria-label="Close">
          <Icon name="x" />
        </button>
      </div>
      <div className={styles.detailsType}>{type.name}</div>
      <h2 id="dialog-title" className={styles.detailsTitle}>
        {ss.name}
      </h2>
      <p className={styles.detailsDesc}>{ss.desc}</p>
      <div className={styles.chipRow}>
        <Chip>{ss.access}</Chip>
        <Chip>{ss.role}</Chip>
      </div>
      <DetailBlock>
        <h3 className={styles.blockTitle}>Sources</h3>
        <div className={styles.sourcesHead}>
          <span className={styles.sourcesMeta}>{ss.count} total</span>
          <span className={styles.sourcesFresh}>Up to date</span>
        </div>
        {ss.docs.map((x) => (
          <div key={x} className={styles.sourceRow}>
            <Icon name="file-text" />
            <span>
              {x}
              <div className={styles.sourceMeta}>
                Google Drive · Accessible to you
              </div>
            </span>
          </div>
        ))}
        <p className={styles.sourcesMeta}>
          {ss.count} sources · {ss.updated}
        </p>
      </DetailBlock>
      <DetailBlock>
        <h3 className={styles.blockTitle}>Access</h3>
        <p className={styles.blockText}>
          {ss.scope === "workspace"
            ? `Available through your ${ss.access} group.`
            : `${ss.access}.`}{" "}
          Original source permissions apply.
        </p>
      </DetailBlock>
      <div className={styles.modalFoot}>
        <span className={styles.sourcesMeta}>Sample content</span>
        <button onClick={onClose} className={styles.actionBtn}>
          Close
        </button>
      </div>
    </div>
  );
}

export function CreateSubstackModal({
  type,
  onClose,
  onSubmit,
}: {
  type: StackType;
  onClose: () => void;
  onSubmit: (ss: Omit<Substack, "id">) => void;
}) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [access, setAccess] = useState("private");
  const [error, setError] = useState("");

  const handleSubmit = () => {
    if (!name.trim()) {
      setError("Give this item a name.");
      return;
    }
    const accessLabel =
      access === "private"
        ? "Only you"
        : access === "product"
          ? "Product & Design"
          : "All members";
    const scope: Substack["scope"] =
      access === "private"
        ? "mine"
        : access === "product"
          ? "shared"
          : "workspace";
    onSubmit({
      typeId: type.id,
      name: name.trim(),
      desc: desc.trim() || `A new ${type.name.toLowerCase()} item.`,
      scope,
      access: accessLabel,
      role: "Owner",
      updated: "Just now",
      docs: [],
      count: 0,
    });
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
        Create a new item inside the {type.name} stack.
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
      <FieldLabel label="Who can access?">
        <select
          value={access}
          onChange={(e) => setAccess(e.target.value)}
          className={styles.select}
        >
          <option value="private">Only me</option>
          <option value="product">Product & Design</option>
          <option value="everyone">All members</option>
        </select>
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

export function CreateStackModal({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (type: StackType) => void;
}) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = () => {
    if (!name.trim()) {
      setError("Give this stack a name.");
      return;
    }
    onSubmit({
      id: name.toLowerCase().replace(/\s+/g, "-") + "-" + Date.now(),
      name: name.trim(),
      desc: desc.trim() || `Manage your ${name.trim().toLowerCase()}.`,
      icon: "folder",
    });
  };

  return (
    <div>
      <div className={styles.modalHead}>
        <h2 id="dialog-title" className={styles.modalTitle}>
          Create a stack
        </h2>
        <button onClick={onClose} className={styles.ghostBtn} aria-label="Close">
          <Icon name="x" />
        </button>
      </div>
      <p className={styles.modalSub}>
        Add a new category to organize your knowledge.
      </p>
      <FieldLabel label="Stack name">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Partnerships"
          className={styles.input}
          autoFocus
        />
      </FieldLabel>
      <FieldLabel label="Description · Optional">
        <textarea
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          placeholder="What will this stack contain?"
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
          Create stack <Icon name="arrow-right" />
        </button>
      </div>
    </div>
  );
}
