"use client";

import { useMemo, useState } from "react";
import Icon from "./icons";
import { SUBSTACK_DETAILS, type DetailSource, type DetailToken, type StackType, type Substack } from "../lib/stacks";
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

function HighlightedToken({ children, sourceIds, onHover }: { children: React.ReactNode; sourceIds: string[]; onHover: (ids: string[] | null) => void }) {
  return <mark className={styles.highlightedToken} onMouseEnter={() => onHover(sourceIds)} onMouseLeave={() => onHover(null)}>{children}</mark>;
}

function InlineToken({ token, onHover }: { token?: DetailToken; onHover: (ids: string[] | null) => void }) {
  if (!token) return null;
  return <HighlightedToken sourceIds={token.sourceIds} onHover={onHover}>{token.value}</HighlightedToken>;
}

export default function SubstackDetail({ substack, stackTypes, substacks, canGoBack, canGoForward, onBack, onForward, onOpen }: Props) {
  const [query, setQuery] = useState("");
  const [hoveredSourceIds, setHoveredSourceIds] = useState<string[] | null>(null);
  const [relatedPreviewId, setRelatedPreviewId] = useState<string | null>(null);
  const [relatedOpen, setRelatedOpen] = useState(true);
  const [panelOpen, setPanelOpen] = useState(true);
  const [expandedTopics, setExpandedTopics] = useState<string[]>([]);
  const type = stackTypes.find((item) => item.id === substack.typeId);
  const detail = SUBSTACK_DETAILS[substack.id];
  const isConversation = substack.typeId === "conversations";
  const isFile = substack.typeId === "files";
  const sources = isFile ? [] : detail?.sources ?? fallbackSources(substack, substacks);
  const allSourceIds = sources.map((source) => source.id);
  const previewTarget = relatedPreviewId ? substacks.find((item) => item.id === relatedPreviewId) : null;
  const previewSources = isFile ? [] : previewTarget ? SUBSTACK_DETAILS[previewTarget.id]?.sources ?? fallbackSources(previewTarget, substacks) : sources;
  const visibleSources = hoveredSourceIds ? previewSources.filter((source) => hoveredSourceIds.includes(source.id)) : previewSources;
  const explicitRelatedIds = detail?.relatedIds ?? [];
  const reverseRelatedIds = isFile ? substacks.filter((item) => item.id !== substack.id && (SUBSTACK_DETAILS[item.id]?.sources.some((source) => source.substackId === substack.id) || item.docs.includes(substack.name))).map((item) => item.id) : [];
  const relatedIds = [...new Set([...explicitRelatedIds, ...reverseRelatedIds])];
  const related = relatedIds.map((id) => substacks.find((item) => item.id === id)).filter((item): item is Substack => Boolean(item));
  const tokens = detail?.tokens ?? [];
  const token = (id: string) => tokens.find((item) => item.id === id);
  const matchingTokens = useMemo(() => tokens.filter((item) => `${item.label} ${item.value}`.toLowerCase().includes(query.toLowerCase())), [tokens, query]);
  const topics = useMemo(() => (detail?.conversation ?? []).filter((entry) => `${entry.date} ${entry.message} ${entry.summary}`.toLowerCase().includes(query.toLowerCase())), [detail?.conversation, query]);
  const genericMatches = `${substack.name} ${substack.desc} ${substack.docs.join(" ")}`.toLowerCase().includes(query.toLowerCase());

  const toggleTopic = (id: string) => setExpandedTopics((current) => current.includes(id) ? current.filter((topicId) => topicId !== id) : [...current, id]);

  return (
    <div className={`${styles.page} ${panelOpen ? "" : styles.pagePanelClosed}`}>
      <section className={styles.content}>
        <header className={styles.header}>
          <div className={styles.historyButtons}>
            <button onClick={onBack} disabled={!canGoBack} aria-label="Back"><Icon name="arrow-left" size={19} /></button>
            <button onClick={onForward} disabled={!canGoForward} aria-label="Next"><Icon name="arrow-right" size={19} /></button>
          </div>
          <h1>{substack.name}</h1><span>{type?.name ?? "Stack"}</span>
          <button className={styles.panelToggle} onClick={() => setPanelOpen((open) => !open)} aria-label={panelOpen ? "Close side panel" : "Open side panel"} aria-expanded={panelOpen}><Icon name="panel-right" size={18} /></button>
        </header>

        <div className={styles.toolbar}>
          {isConversation && <span className={styles.sortLabel}>Most recent first</span>}
          <label><Icon name="search" size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={isConversation ? "Search summary" : "Search content"} /></label>
        </div>

        <h2>{isConversation ? "Summary" : "Content"}</h2>
        {isConversation ? <div className={styles.topics}>
          {topics.map((topic) => {
            const expanded = expandedTopics.includes(topic.id);
            return <article key={topic.id} className={styles.topic} onMouseEnter={() => setHoveredSourceIds(topic.sourceIds)} onMouseLeave={() => setHoveredSourceIds(null)}>
              <div className={styles.topicMeta}>{topic.date}</div>
              <h3><HighlightedToken sourceIds={topic.sourceIds} onHover={setHoveredSourceIds}>{topic.message}</HighlightedToken></h3>
              <p className={expanded ? "" : styles.clamped}>{topic.summary}</p>
              <button onClick={() => toggleTopic(topic.id)}>{expanded ? "Show less" : "Show more"}<Icon name="chevron-down" size={14} /></button>
            </article>;
          })}
          {topics.length === 0 && <p className={styles.empty}>No matching topics.</p>}
        </div> : substack.id === "so-2431" ? <div className={styles.prose}>
          {(query === "" || matchingTokens.length > 0) && <>
            <section><h3>Order overview</h3><p><InlineToken token={token("client")} onHover={setHoveredSourceIds} /> placed sales order <InlineToken token={token("po")} onHover={setHoveredSourceIds} /> for <InlineToken token={token("qty")} onHover={setHoveredSourceIds} /> of the <InlineToken token={token("item")} onHover={setHoveredSourceIds} />. The order is <InlineToken token={token("status")} onHover={setHoveredSourceIds} /> and has a total value of <InlineToken token={token("total")} onHover={setHoveredSourceIds} />.</p></section>
            <section><h3>Delivery and ownership</h3><p>Delivery is scheduled for <InlineToken token={token("delivery")} onHover={setHoveredSourceIds} />. <InlineToken token={token("pic")} onHover={setHoveredSourceIds} /> is coordinating the customer confirmation, production handoff, and final delivery.</p></section>
            <section><h3>What needs attention</h3><p>The latest WhatsApp confirmation changed the quantity to 240 units. Production should use the approved BRK-440 Rev C specification and preserve the conversation as evidence for this revision.</p></section>
          </>}
          {query && matchingTokens.length === 0 && <p className={styles.empty}>No matching content.</p>}
        </div> : <div className={styles.prose}>
          {genericMatches ? <>
            <section><h3>Overview</h3><p>{sources.length > 0 ? <HighlightedToken sourceIds={allSourceIds} onHover={setHoveredSourceIds}>{substack.name}</HighlightedToken> : <strong>{substack.name}</strong>} is recorded in the {type?.name ?? "workspace"} stack. {substack.desc}</p></section>
            <section><h3>Current context</h3><p>This record was last updated {sources.length > 0 ? <HighlightedToken sourceIds={allSourceIds} onHover={setHoveredSourceIds}>{substack.updated.toLowerCase()}</HighlightedToken> : substack.updated.toLowerCase()} and is available to {substack.access.toLowerCase()}. Supporting information has been organized in the side panel so the team can verify the record against its original evidence.</p></section>
            {sources.length > 0 && <section><h3>Supporting material</h3><p>The record references {sources.map((source, index) => <span key={source.id}>{index > 0 && ", "}<HighlightedToken sourceIds={[source.id]} onHover={setHoveredSourceIds}>{source.name}</HighlightedToken></span>)}. Hover over a highlighted token to isolate its evidence, or open the source to inspect the original record.</p></section>}
          </> : <p className={styles.empty}>No matching content.</p>}
        </div>}

        <section className={`${styles.related} ${relatedOpen ? "" : styles.relatedClosed}`}>
          <button className={styles.relatedToggle} onClick={() => setRelatedOpen((open) => !open)} aria-expanded={relatedOpen}><span>Related <small>{related.length}</small></span><Icon name="chevron-down" /></button>
          {relatedOpen && <div className={styles.relatedGrid}>{related.map((item) => {
            const relatedType = stackTypes.find((candidate) => candidate.id === item.typeId);
            return <button key={item.id} onClick={() => onOpen(item.id)} onMouseEnter={() => { setRelatedPreviewId(item.id); setHoveredSourceIds(null); }} onMouseLeave={() => setRelatedPreviewId(null)}><span>{relatedType?.name}</span><strong>{item.name}</strong></button>;
          })}</div>}
        </section>
      </section>

      {panelOpen && <aside className={styles.sources}>
        <div className={styles.sourcesHeader}><h2>{isConversation ? "Attachments" : "Sources"}</h2><button onClick={() => setPanelOpen(false)} aria-label="Close side panel"><Icon name="x" size={16} /></button></div>
        <div className={styles.sourceList}>
          {visibleSources.map((source, index) => <button key={source.id} onClick={() => onOpen(source.substackId)}><b>{String(index + 1).padStart(2, "0")}</b><span><strong>{source.name}</strong><small>{source.type} · {source.origin} · {source.updated}</small><small>{source.note}</small></span></button>)}
          {visibleSources.length === 0 && <div className={styles.emptyPanel}><Icon name="file-text" size={20} /><p>{isFile ? "Files are original evidence and do not have their own sources." : "No sources linked to this content."}</p></div>}
        </div>
        <button className={styles.chat}>Chat with POPO <Icon name="chevron-down" /></button>
      </aside>}
    </div>
  );
}
