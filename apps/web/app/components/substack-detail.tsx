"use client";

import { useMemo, useState } from "react";
import Icon from "./icons";
import ClientPicture from "./client-picture";
import { type StackType, type Substack, type UiSubstackDetail } from "../lib/stacks";
import { track } from "../lib/analytics";
import styles from "./substack-detail.module.css";

interface Props {
  substack: Substack;
  stackTypes: StackType[];
  detail: UiSubstackDetail | null;
  details: Record<string, UiSubstackDetail>;
  backLabel: string;
  accountId: string | null;
  onBack: () => void;
  /** Present when the record was opened from the Analyze workspace queue. */
  queue: { position: number; total: number; onPrev: (() => void) | null; onNext: (() => void) | null } | null;
  onOpen: (id: string) => void;
  onEnsureDetail: (id: string) => void;
  onConfirmContent: (contentId: string) => void;
  onKeepCurrentContent: (contentId: string) => void;
}

type UpdateAction = "confirm" | "keep";
const UPDATE_ACTIONS: Record<UpdateAction, string> = { confirm: "Confirm update", keep: "Keep current version" };

const TOPIC_KINDS: Record<string, string> = { topic: "Topic", decision: "Decision", key_point: "Key point" };

function formatTopicDate(value: unknown): string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return "";
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function HighlightedToken({ children, sourceIds, onHover }: { children: React.ReactNode; sourceIds: string[]; onHover: (ids: string[] | null) => void }) {
  if (sourceIds.length === 0) return <>{children}</>;
  return <mark className={styles.highlightedToken} onMouseEnter={() => onHover(sourceIds)} onMouseLeave={() => onHover(null)}>{children}</mark>;
}

export default function SubstackDetail({ substack, stackTypes, detail, details, backLabel, accountId, onBack, queue, onOpen, onEnsureDetail, onConfirmContent, onKeepCurrentContent }: Props) {
  const [query, setQuery] = useState("");
  const [showPending, setShowPending] = useState(false);
  const [updateMenuOpen, setUpdateMenuOpen] = useState(false);
  const [updateAction, setUpdateAction] = useState<UpdateAction>("confirm");
  const [hoveredSourceIds, setHoveredSourceIds] = useState<string[] | null>(null);
  const [relatedPreviewId, setRelatedPreviewId] = useState<string | null>(null);
  const [relatedOpen, setRelatedOpen] = useState(true);
  const [panelOpen, setPanelOpen] = useState(true);
  const type = stackTypes.find((item) => item.id === substack.typeId);
  const isConversation = substack.typeId === "conversations";
  const isClient = substack.typeId === "clients";
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
  const allTopics = useMemo(() => (displayed?.segments ?? []).filter((segment) => segment.kind === "text" && segment.name), [displayed?.segments]);
  const topics = useMemo(
    () => matchingSegments
      .filter((segment) => segment.kind === "text" && segment.name)
      .map((segment, index) => ({ segment, index, date: typeof segment.locator?.date === "string" ? segment.locator.date : "" }))
      .sort((a, b) => b.date.localeCompare(a.date) || a.index - b.index)
      .map(({ segment }) => segment),
    [matchingSegments],
  );
  const [expandedTopics, setExpandedTopics] = useState<Set<string>>(new Set());
  const toggleTopic = (id: string) => setExpandedTopics((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
  const summarized = Boolean(displayed?.id) && !(displayed?.segments ?? []).some((segment) => segment.kind !== "text");

  return (
    <div className={`${styles.page} ${panelOpen ? "" : styles.pagePanelClosed}`}>
      <section className={styles.content}>
        <button type="button" className={styles.backButton} onClick={onBack}>
          <Icon name="arrow-left" size={14} /> <span>{backLabel}</span>
        </button>
        <header className={styles.header}>
          <h1>{substack.name}</h1><span>{type?.name ?? "Stack"}</span>
          {queue && (
            <nav className={styles.queueNav} aria-label="Review queue">
              <button type="button" onClick={queue.onPrev ?? undefined} disabled={!queue.onPrev} aria-label="Previous item to check"><Icon name="chevron-left" size={16} /></button>
              <span>{queue.position} of {queue.total}</span>
              <button type="button" onClick={queue.onNext ?? undefined} disabled={!queue.onNext} aria-label="Next item to check"><Icon name="chevron-right" size={16} /></button>
            </nav>
          )}
          <button className={queue ? `${styles.panelToggle} ${styles.panelToggleInline}` : styles.panelToggle} onClick={() => togglePanel(!panelOpen)} aria-label={panelOpen ? "Close side panel" : "Open side panel"} aria-expanded={panelOpen}><Icon name="panel-right" size={18} /></button>
        </header>

        {substack.generating && (
          <div className={styles.reviewBanner} role="status" aria-live="polite">
            <span>Generating this record from your files. Its content will appear here when it is ready.</span>
          </div>
        )}
        {substack.reviewState === "unsupported" && (
          <div className={styles.reviewBanner} role="status">
            <span>This record no longer has enough current supporting evidence. Its last confirmed content remains available.</span>
          </div>
        )}
        {substack.reviewState === "generation_error" && (
          <div className={styles.reviewBanner} role="status">
            <span>Generating content for this record failed.</span>
          </div>
        )}
        {detail?.pending && (
          <div className={styles.reviewBanner} role="status">
            <span>{showPending ? "Reviewing proposed update" : "A proposed update is ready for review"}</span>
            <button onClick={() => setShowPending((value) => !value)}>{showPending ? "View current" : "Review update"}</button>
            {showPending && detail.pending.id && (
              <div
                className={styles.splitButton}
                onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setUpdateMenuOpen(false); }}
                onKeyDown={(event) => { if (event.key === "Escape") setUpdateMenuOpen(false); }}
              >
                <button
                  className={styles.confirmButton}
                  onClick={() => {
                    if (updateAction === "keep") {
                      setShowPending(false);
                      onKeepCurrentContent(detail.pending!.id);
                    } else onConfirmContent(detail.pending!.id);
                  }}
                >
                  {UPDATE_ACTIONS[updateAction]}
                </button>
                <button className={styles.splitToggle} onClick={() => setUpdateMenuOpen((open) => !open)} aria-label="Choose update action" aria-haspopup="menu" aria-expanded={updateMenuOpen}><Icon name="chevron-down" size={14} /></button>
                {updateMenuOpen && (
                  <div className={styles.splitMenu} role="menu">
                    {(Object.keys(UPDATE_ACTIONS) as UpdateAction[]).map((action) => (
                      <button
                        key={action}
                        role="menuitemradio"
                        aria-checked={updateAction === action}
                        onClick={() => { setUpdateAction(action); setUpdateMenuOpen(false); }}
                      >
                        <span className={styles.splitMenuCheck}>{updateAction === action && <Icon name="check" size={14} />}</span>
                        {UPDATE_ACTIONS[action]}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
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
            {topics.map((topic) => {
              const expanded = expandedTopics.has(topic.id);
              const meta = [TOPIC_KINDS[String(topic.locator?.kind)] ?? "Topic", formatTopicDate(topic.locator?.date)].filter(Boolean).join(" · ");
              return (
                <article key={topic.id} className={styles.topic} onMouseEnter={() => setHoveredSourceIds(topic.sourceIds)} onMouseLeave={() => setHoveredSourceIds(null)}>
                  <div className={styles.topicMeta}>{meta}</div>
                  <h3>{topic.name}</h3>
                  <p className={expanded ? undefined : styles.clamped}>{topic.value}</p>
                  <button type="button" onClick={() => toggleTopic(topic.id)} aria-expanded={expanded}>
                    {expanded ? "Show less" : "Show more"} <Icon name="chevron-down" size={13} />
                  </button>
                </article>
              );
            })}
            {topics.length === 0 && (
              <p className={styles.empty}>
                {allTopics.length > 0 ? "No matching topics." : summarized ? "No business topics were found in this conversation." : "No summary yet. Run Analyze and regenerate this conversation to summarize it."}
              </p>
            )}
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
              <p className={styles.empty}>{(displayed?.segments.length ?? 0) === 0 ? (substack.generating ? "Generating content…" : "No generated content yet.") : "No matching content."}</p>
            )}
          </div>
        )}

        {isClient && accountId && (
          <ClientPicture
            accountId={accountId}
            substackId={substack.id}
            stackTypes={stackTypes}
            onOpen={onOpen}
          />
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
