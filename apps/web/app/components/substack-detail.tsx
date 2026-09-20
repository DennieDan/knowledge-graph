"use client";

import { useMemo, useState } from "react";
import Icon from "./icons";
import { SUBSTACK_DETAILS, type DetailSource, type StackType, type Substack } from "../lib/stacks";
import styles from "./substack-detail.module.css";

interface Props {
  substack: Substack;
  stackTypes: StackType[];
  substacks: Substack[];
  canGoBack: boolean;
  canGoForward: boolean;
  onBack: () => void;
  onForward: () => void;
  onOpen: (id: string) => void;
}

const fallbackSources = (substack: Substack, substacks: Substack[]): DetailSource[] => substack.docs.map((name, index) => {
  const file = substacks.find((item) => item.typeId === "files" && item.name === name);
  return { id: `fallback-${index}`, substackId: file?.id ?? "file-po2431", name, type: "Files", origin: "Google Drive", updated: substack.updated, note: "Supporting document" };
});

export default function SubstackDetail({ substack, stackTypes, substacks, canGoBack, canGoForward, onBack, onForward, onOpen }: Props) {
  const [query, setQuery] = useState("");
  const [hoveredSourceIds, setHoveredSourceIds] = useState<string[] | null>(null);
  const [relatedPreviewId, setRelatedPreviewId] = useState<string | null>(null);
  const [relatedOpen, setRelatedOpen] = useState(true);
  const type = stackTypes.find((item) => item.id === substack.typeId);
  const detail = SUBSTACK_DETAILS[substack.id];
  const isConversation = substack.typeId === "conversations";
  const sources = detail?.sources ?? fallbackSources(substack, substacks);
  const previewSources = relatedPreviewId
    ? SUBSTACK_DETAILS[relatedPreviewId]?.sources ?? fallbackSources(substacks.find((item) => item.id === relatedPreviewId)!, substacks)
    : sources;
  const visibleSources = hoveredSourceIds ? previewSources.filter((source) => hoveredSourceIds.includes(source.id)) : previewSources;
  const related = (detail?.relatedIds ?? []).map((id) => substacks.find((item) => item.id === id)).filter((item): item is Substack => Boolean(item));
  const tokens = useMemo(() => (detail?.tokens ?? []).filter((token) => `${token.label} ${token.value}`.toLowerCase().includes(query.toLowerCase())), [detail?.tokens, query]);
  const messages = useMemo(() => (detail?.conversation ?? []).filter((entry) => `${entry.date} ${entry.author} ${entry.message} ${entry.summary}`.toLowerCase().includes(query.toLowerCase())), [detail?.conversation, query]);

  return (
    <div className={styles.page}>
      <section className={styles.content}>
        <header className={styles.header}>
          <div className={styles.historyButtons}>
            <button onClick={onBack} disabled={!canGoBack} aria-label="Back"><Icon name="arrow-left" size={19} /></button>
            <button onClick={onForward} disabled={!canGoForward} aria-label="Next"><Icon name="arrow-right" size={19} /></button>
          </div>
          <h1>{substack.name}</h1>
          <span>{type?.name ?? "Stack"}</span>
        </header>

        <div className={styles.toolbar}>
          {isConversation && <select aria-label="Sort conversation"><option>By Date</option><option>By Sender</option></select>}
          <label><Icon name="search" size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search for token" /></label>
        </div>

        <h2>{isConversation ? "Summary" : "Content"}</h2>
        {isConversation ? (
          <div className={styles.messages}>
            {messages.map((entry) => (
              <button key={entry.id} className={styles.message} onMouseEnter={() => setHoveredSourceIds(entry.sourceIds)} onMouseLeave={() => setHoveredSourceIds(null)}>
                <span className={styles.messageDate}>{entry.date}</span>
                <strong>{entry.message}</strong>
                <em>{entry.summary}</em>
              </button>
            ))}
          </div>
        ) : (
          <div className={styles.tokens}>
            {tokens.map((token) => (
              <button key={token.id} className={styles.token} onMouseEnter={() => setHoveredSourceIds(token.sourceIds)} onMouseLeave={() => setHoveredSourceIds(null)}>
                <span>{token.label}</span><strong>{token.value}</strong>
              </button>
            ))}
            {tokens.length === 0 && <p className={styles.empty}>No matching tokens.</p>}
          </div>
        )}

        <section className={`${styles.related} ${relatedOpen ? "" : styles.relatedClosed}`}>
          <button className={styles.relatedToggle} onClick={() => setRelatedOpen((open) => !open)} aria-expanded={relatedOpen}>
            <span>Related <small>{related.length}</small></span><Icon name="chevron-down" />
          </button>
          {relatedOpen && <div className={styles.relatedGrid}>
            {related.map((item) => {
              const relatedType = stackTypes.find((candidate) => candidate.id === item.typeId);
              return <button key={item.id} onClick={() => onOpen(item.id)} onMouseEnter={() => { setRelatedPreviewId(item.id); setHoveredSourceIds(null); }} onMouseLeave={() => setRelatedPreviewId(null)}>
                <span>{relatedType?.name}</span><strong>{item.name}</strong>
              </button>;
            })}
          </div>}
        </section>
      </section>

      <aside className={styles.sources}>
        <h2>{isConversation ? "Attachments" : "Sources"}</h2>
        <div className={styles.sourceList}>
          {visibleSources.map((source, index) => <button key={source.id} onClick={() => onOpen(source.substackId)}>
            <b>{String(index + 1).padStart(2, "0")}</b>
            <span><strong>{source.name}</strong><small>{source.type} · {source.origin} · {source.updated}</small><small>{source.note}</small></span>
          </button>)}
          {visibleSources.length === 0 && <p className={styles.empty}>No sources linked to this token.</p>}
        </div>
        <button className={styles.chat}>Chat with POPO <Icon name="chevron-down" /></button>
      </aside>
    </div>
  );
}
