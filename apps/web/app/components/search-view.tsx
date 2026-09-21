"use client";

import { useState } from "react";
import DriveFiles from "./drive-files";
import Icon from "./icons";
import type { Me } from "../lib/api";
import styles from "./search-view.module.css";

type Source = "Drive" | "WhatsApp" | "Knowledge record";

interface KnowledgeItem {
  title: string;
  source: Source;
  path: string;
  text: string;
  access: string;
  relation: string;
  updated: string;
}

const ITEMS: KnowledgeItem[] = [
  {
    title: "Project Atlas — Launch brief",
    source: "Drive",
    path: "Company Drive / Projects / Atlas / Launch brief",
    text: "Launch plan, deliverables and proposed schedule.",
    access: "Atlas team · View",
    relation: "Document belongs to Project Atlas",
    updated: "12 Sep · Maya Chen",
  },
  {
    title: "Maya ↔ Alex — Launch discussion",
    source: "WhatsApp",
    path: "Imported 1:1 chat / Maya ↔ Alex / 13 Sep",
    text: "“Can we move the Atlas launch to 25 September?”",
    access: "Chat participants + explicitly authorized viewers",
    relation: "Conversation discusses Project Atlas",
    updated: "13 Sep · Maya Chen",
  },
  {
    title: "Project Atlas — Meeting notes",
    source: "Drive",
    path: "Company Drive / Projects / Atlas / Meeting notes",
    text: "Decisions, owners and follow-up actions.",
    access: "Atlas team · View",
    relation: "AI-linked to Project Atlas",
    updated: "11 Sep · Alex Tan",
  },
  {
    title: "Project Atlas",
    source: "Knowledge record",
    path: "Workspace / Projects / Atlas",
    text: "Launch project connecting its brief, discussion and meeting notes.",
    access: "Derived from accessible sources only",
    relation: "Project groups the visible connected items",
    updated: "14 Sep · AI maintenance",
  },
  {
    title: "Maya Chen",
    source: "Knowledge record",
    path: "Workspace / People / Maya Chen",
    text: "Project owner named in the launch brief.",
    access: "Atlas team · View",
    relation: "Maya owns Project Atlas",
    updated: "12 Sep · Source: launch brief",
  },
];

const SEARCHABLE = ITEMS.slice(0, 3);

export default function SearchView({ me }: { me: Me | null }) {
  const [query, setQuery] = useState("");
  const [sources, setSources] = useState({ Drive: true, WhatsApp: true });
  const [selected, setSelected] = useState(0);

  const q = query.trim().toLowerCase();
  const results = SEARCHABLE.map((item, index) => ({ item, index })).filter(
    ({ item }) =>
      sources[item.source as "Drive" | "WhatsApp"] &&
      (q === "" || `${item.title} ${item.text}`.toLowerCase().includes(q)),
  );
  const detail = ITEMS[selected] as KnowledgeItem;

  return (
    <div className={styles.searchShell}>
      <div className={styles.content}>
        <h1 className={styles.title}>Find company knowledge</h1>
        <p className={styles.subtitle}>Search across connected sources</p>

        <form
          className={styles.searchBar}
          role="search"
          onSubmit={(e) => e.preventDefault()}
        >
          <Icon name="search" size={18} />
          <input
            type="search"
            aria-label="Search company knowledge"
            placeholder="Search files, conversations, people…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </form>

        <div className={styles.filters}>
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={sources.Drive}
              onChange={() =>
                setSources((s) => ({ ...s, Drive: !s.Drive }))
              }
            />
            Google Drive
          </label>
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={sources.WhatsApp}
              onChange={() =>
                setSources((s) => ({ ...s, WhatsApp: !s.WhatsApp }))
              }
            />
            WhatsApp · 1:1
          </label>
          <span className={styles.visibility}>
            <Icon name="lock" size={14} /> Only information you can access
          </span>
        </div>

        <section className={styles.summaryCard}>
          <span className={styles.cardOverline}>Suggestion</span>
          <h2 className={styles.cardTitle}>Project Atlas</h2>
          <p>
            Launch timing differs between the project brief and the latest
            conversation.
          </p>
          <div className={styles.cardActions}>
            <button type="button" className={styles.btnTonal} disabled>
              Review conflicting information
            </button>
          </div>
        </section>

        <div className={styles.results} aria-live="polite">
          <p className={styles.muted}>
            {results.length} accessible result
            {results.length === 1 ? "" : "s"}
          </p>
          {results.map(({ item, index }) => (
            <button
              key={item.title}
              type="button"
              className={styles.result}
              data-selected={selected === index}
              onClick={() => setSelected(index)}
            >
              <span className={styles.resultTitle}>{item.title}</span>
              <span className={styles.resultMeta}>
                {item.source} · {item.updated}
              </span>
              <span className={styles.resultText}>{item.text}</span>
            </button>
          ))}
        </div>

        {me?.drive_linked && me.active_account_id && <DriveFiles accountId={me.active_account_id} />}
      </div>

      <aside className={styles.detail} aria-live="polite">
        <span className={styles.sectionLabel}>Item details</span>
        <h2 className={styles.cardTitle}>{detail.title}</h2>
        <p>{detail.text}</p>
        <dl className={styles.detailList}>
          <dt>Source location</dt>
          <dd>{detail.path}</dd>
          <dt>Last updated</dt>
          <dd>{detail.updated}</dd>
          <dt>Permission</dt>
          <dd>{detail.access}</dd>
          <dt>Relationship</dt>
          <dd>{detail.relation}</dd>
        </dl>
        <p className={styles.muted}>Source preview · Demo record</p>
      </aside>
    </div>
  );
}
