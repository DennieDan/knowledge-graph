"use client";

import { useMemo, useState } from "react";
import Icon from "./icons";
import { type StackType, type Substack, type UiSubstackDetail } from "../lib/stacks";
import { track } from "../lib/analytics";
import styles from "./substack-detail.module.css";

interface Props {
  substack: Substack;
  stackTypes: StackType[];
  detail: UiSubstackDetail | null;
  details: Record<string, UiSubstackDetail>;
  canGoBack: boolean;
  canGoForward: boolean;
  onBack: () => void;
  onForward: () => void;
  onOpen: (id: string) => void;
  onEnsureDetail: (id: string) => void;
  onConfirmContent: (contentId: string) => void;
}

function HighlightedToken({ children, sourceIds, onHover }: { children: React.ReactNode; sourceIds: string[]; onHover: (ids: string[] | null) => void }) {
  if (sourceIds.length === 0) return <>{children}</>;
  return <mark className={styles.highlightedToken} onMouseEnter={() => onHover(sourceIds)} onMouseLeave={() => onHover(null)}>{children}</mark>;
}

export default function SubstackDetail({ substack, stackTypes, detail, details, canGoBack, canGoForward, onBack, onForward, onOpen, onEnsureDetail, onConfirmContent }: Props) {
  const [query, setQuery] = useState("");
  const [showPending, setShowPending] = useState(false);
  const [hoveredSourceIds, setHoveredSourceIds] = useState<string[] | null>(null);
  const [relatedPreviewId, setRelatedPreviewId] = useState<string | null>(null);
  const [relatedOpen, setRelatedOpen] = useState(true);
  const [panelOpen, setPanelOpen] = useState(true);
  const type = stackTypes.find((item) => item.id === substack.typeId);
  const isConversation = substack.typeId === "conversations";
  const sources = detail?.sources ?? [];
  const previewSources = relatedPreviewId && details[relatedPreviewId] ? details[relatedPreviewId].sources : sources;
  const visibleSources = hoveredSourceIds ? previewSources.filter((source) => hoveredSourceIds.includes(source.id)) : previewSources;
  const related = detail?.related ?? [];
  const [relatedTypeFilter, setRelatedTypeFilter] = useState<Set<string>>(new Set());
  const relatedTypes = useMemo(() => [...new Set(related.map((item) => item.typeId))], [related]);
  const visibleRelated = related.filter((item) => relatedTypeFilter.size === 0 || relatedTypeFilter.has(item.typeId));
  const displayed = showPending && detail?.pending ? detail.pending : detail;
  const togglePanel = (open: boolean) => {
    track("evidence_panel_toggled", { open, stack_type: substack.typeId });
    setPanelOpen(open);
  };

  const matchingSegments = useMemo(
    () => (displayed?.segments ?? []).filter((segment) => `${segment.name ?? ""} ${segment.value}`.toLowerCase().includes(query.toLowerCase())),
    [displayed?.segments, query],
  );
  const topics = useMemo(
    () => (displayed?.conversation ?? []).filter((entry) => `${entry.date} ${entry.author} ${entry.message}`.toLowerCase().includes(query.toLowerCase())),
    [displayed?.conversation, query],
  );

  return (
    <div className={`${styles.page} ${panelOpen ? "" : styles.pagePanelClosed}`}>
      <section className={styles.content}>
        <header className={styles.header}>
          <div className={styles.historyButtons}>
            <button onClick={onBack} disabled={!canGoBack} aria-label="Back"><Icon name="arrow-left" size={19} /></button>
            <button onClick={onForward} disabled={!canGoForward} aria-label="Next"><Icon name="arrow-right" size={19} /></button>
          </div>
          <h1>{substack.name}</h1><span>{type?.name ?? "Stack"}</span>
          <button className={styles.panelToggle} onClick={() => togglePanel(!panelOpen)} aria-label={panelOpen ? "Close side panel" : "Open side panel"} aria-expanded={panelOpen}><Icon name="panel-right" size={18} /></button>
        </header>

        {substack.reviewState === "unsupported" && (
          <div className={styles.reviewBanner} role="status">
            <span>This record no longer has enough current supporting evidence. Its last confirmed content remains available.</span>
          </div>
        )}
        {substack.reviewState === "generation_error" && (
          <div className={styles.reviewBanner} role="status">
            <span>Generating content for this record failed. Check Maintenance for the failed run.</span>
          </div>
        )}
        {detail?.pending && (
          <div className={styles.reviewBanner} role="status">
            <span>{showPending ? "Reviewing proposed update" : "A proposed update is ready for review"}</span>
            <button onClick={() => setShowPending((value) => !value)}>{showPending ? "View current" : "Review update"}</button>
            {showPending && detail.pending.id && <button className={styles.confirmButton} onClick={() => onConfirmContent(detail.pending!.id)}>Confirm update</button>}
          </div>
        )}
        {!detail?.pending && detail?.status === "proposed" && detail.id && (
          <div className={styles.reviewBanner} role="status">
            <span>This AI-generated content is proposed and has not been confirmed.</span>
            <button className={styles.confirmButton} onClick={() => onConfirmContent(detail.id)}>Confirm content</button>
          </div>
        )}

        <div className={styles.toolbar}>
          {isConversation && <span className={styles.sortLabel}>Most recent first</span>}
          <label><Icon name="search" size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={isConversation ? "Search summary" : "Search content"} /></label>
        </div>

        <h2>{isConversation ? "Summary" : "Content"}</h2>
        {!detail ? (
          <p className={styles.empty}>Loading content…</p>
        ) : isConversation ? (
          <div className={styles.topics}>
            {topics.map((topic) => (
              <article key={topic.id} className={styles.topic} onMouseEnter={() => setHoveredSourceIds(topic.sourceIds)} onMouseLeave={() => setHoveredSourceIds(null)}>
                <div className={styles.topicMeta}>{topic.date} · {topic.author}</div>
                <h3><HighlightedToken sourceIds={topic.sourceIds} onHover={setHoveredSourceIds}>{topic.message}</HighlightedToken></h3>
              </article>
            ))}
            {topics.length === 0 && <p className={styles.empty}>No matching topics.</p>}
          </div>
        ) : (
          <div className={styles.prose}>
            {matchingSegments.length > 0 ? (
              <section>
                <p>
                  {matchingSegments.map((segment) => (
                    <span key={segment.id} className={segment.kind === "text" ? styles.reportParagraph : undefined}>
                      <HighlightedToken sourceIds={segment.sourceIds} onHover={setHoveredSourceIds}>
                        {segment.kind === "field" && segment.name ? `${segment.name}: ${segment.value}` : segment.value}
                      </HighlightedToken>
                    </span>
                  ))}
                </p>
              </section>
            ) : (
              <p className={styles.empty}>{(displayed?.segments.length ?? 0) === 0 ? "No generated content yet." : "No matching content."}</p>
            )}
          </div>
        )}

        <section className={`${styles.related} ${relatedOpen ? "" : styles.relatedClosed}`}>
          <button className={styles.relatedToggle} onClick={() => setRelatedOpen((open) => !open)} aria-expanded={relatedOpen}><span>Related <small>{relatedTypeFilter.size > 0 ? `${visibleRelated.length}/${related.length}` : related.length}</small></span><Icon name="chevron-down" /></button>
          {relatedOpen && relatedTypes.length > 1 && (
            <div className={styles.relatedFilters} role="group" aria-label="Filter related by stack type">
              {relatedTypes.map((typeId) => (
                <button
                  key={typeId}
                  type="button"
                  aria-pressed={relatedTypeFilter.has(typeId)}
                  onClick={() => setRelatedTypeFilter((current) => {
                    const next = new Set(current);
                    if (next.has(typeId)) next.delete(typeId);
                    else next.add(typeId);
                    return next;
                  })}
                  className={`${styles.relatedChip} ${relatedTypeFilter.has(typeId) ? styles.relatedChipActive : ""}`}
                >
                  {stackTypes.find((candidate) => candidate.id === typeId)?.name ?? typeId}
                </button>
              ))}
            </div>
          )}
          {relatedOpen && <div className={styles.relatedGrid}>{visibleRelated.map((item) => {
            const relatedType = stackTypes.find((candidate) => candidate.id === item.typeId);
            return <button key={item.id} onClick={() => { track("related_opened", { stack_type: substack.typeId, target_type: item.typeId }); onOpen(item.id); }} onMouseEnter={() => { setRelatedPreviewId(item.id); setHoveredSourceIds(null); onEnsureDetail(item.id); }} onMouseLeave={() => setRelatedPreviewId(null)}><span>{relatedType?.name}</span><strong>{item.name}</strong></button>;
          })}</div>}
        </section>
      </section>

      {panelOpen && <aside className={styles.sources}>
        <div className={styles.sourcesHeader}><h2>{isConversation ? "Attachments" : "Sources"}</h2><button onClick={() => togglePanel(false)} aria-label="Close side panel"><Icon name="x" size={16} /></button></div>
        <div className={styles.sourceList}>
          {visibleSources.map((source, index) => <button key={`${source.id}-${index}`} onClick={() => { track("source_opened", { stack_type: substack.typeId, source_type: source.type }); if (source.substackId) onOpen(source.substackId); }}><b>{String(index + 1).padStart(2, "0")}</b><span><strong>{source.name}</strong><small>{source.type} · {source.origin} · {source.updated}</small><small>{source.note}</small></span></button>)}
          {visibleSources.length === 0 && <div className={styles.emptyPanel}><Icon name="file-text" size={20} /><p>No sources linked to this content.</p></div>}
        </div>
        <button className={styles.chat}>Chat with POPO <Icon name="chevron-down" /></button>
      </aside>}
    </div>
  );
}
