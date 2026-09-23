"use client";

import { useEffect, useRef, useState } from "react";
import Icon from "./icons";
import {
  createChatThread,
  getChatThread,
  isRecordCitation,
  listChatThreads,
  postChatMessage,
  setChatFeedback,
  type ChatCitation,
  type ChatMessage,
  type ChatThread,
} from "../lib/api";
import styles from "./search-view.module.css";

function checkedClass(note: string | null): string {
  if (!note) return "";
  if (note.startsWith("Confirmed by")) return styles.checkedYes ?? "";
  return styles.checkedNo ?? "";
}

function CitationChip({
  citation,
  onOpenRecord,
}: {
  citation: ChatCitation;
  onOpenRecord: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  if (isRecordCitation(citation)) {
    return (
      <button
        type="button"
        className={`${styles.cite} ${styles.citeRecord}`}
        onClick={() => onOpenRecord(citation.record_id)}
        title={citation.stack_type}
      >
        <Icon
          name={citation.checked === "person" ? "badge-check" : "file-text"}
          size={12}
        />
        {citation.name}
      </button>
    );
  }
  return (
    <span className={styles.citeWrap}>
      <button
        type="button"
        className={styles.cite}
        onClick={() => setOpen((v) => !v)}
        title={citation.source}
      >
        <Icon name="file-text" size={12} />
        {citation.title}
      </button>
      {open && <span className={styles.snippet}>{citation.snippet}</span>}
    </span>
  );
}

function AnswerBlock({
  message,
  accountId,
  onOpenRecord,
}: {
  message: ChatMessage;
  accountId: string;
  onOpenRecord: (id: string) => void;
}) {
  const [feedback, setFeedback] = useState(message.feedback);
  const [stepsOpen, setStepsOpen] = useState(false);

  const rate = (rating: "up" | "down") => {
    setFeedback(rating);
    setChatFeedback(accountId, message.id, rating).catch(() =>
      setFeedback(message.feedback),
    );
  };

  const queries = (message.steps ?? [])
    .map((s) => s.query)
    .filter((q): q is string => Boolean(q));

  return (
    <div className={styles.answer}>
      <p className={message.answered ? styles.answerText : styles.answerTextNone}>
        {message.text}
      </p>
      {message.checked_note && (
        <p className={`${styles.checkedNote} ${checkedClass(message.checked_note)}`}>
          <Icon name="shield" size={12} />
          {message.checked_note}
        </p>
      )}
      {message.citations?.length > 0 && (
        <div className={styles.cites}>
          {message.citations.map((c, i) => (
            <CitationChip
              key={isRecordCitation(c) ? c.record_id : c.chunk_id ?? i}
              citation={c}
              onOpenRecord={onOpenRecord}
            />
          ))}
        </div>
      )}
      <div className={styles.answerMeta}>
        {message.answered && (
          <span className={styles.feedback}>
            <button
              type="button"
              className={`${styles.rateBtn} ${feedback === "up" ? styles.rateOn : ""}`}
              onClick={() => rate("up")}
              aria-label="Helpful"
              aria-pressed={feedback === "up"}
            >
              <Icon name="thumbs-up" size={14} />
            </button>
            <button
              type="button"
              className={`${styles.rateBtn} ${feedback === "down" ? styles.rateOn : ""}`}
              onClick={() => rate("down")}
              aria-label="Not helpful"
              aria-pressed={feedback === "down"}
            >
              <Icon name="thumbs-down" size={14} />
            </button>
          </span>
        )}
        {queries.length > 0 && (
          <button
            type="button"
            className={styles.stepsBtn}
            onClick={() => setStepsOpen((v) => !v)}
          >
            <Icon name="search" size={12} />
            {stepsOpen ? "Hide searches" : `Searched ${queries.length}×`}
          </button>
        )}
      </div>
      {stepsOpen && (
        <ul className={styles.stepsList}>
          {queries.map((q, i) => (
            <li key={i}>“{q}”</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function SearchView({
  accountId,
  onOpenRecord,
}: {
  accountId: string | null;
  onOpenRecord: (id: string) => void;
}) {
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  // Set when we create a thread ourselves: local state is already
  // authoritative, so the thread-load effect must not clobber it.
  const skipNextFetch = useRef(false);

  useEffect(() => {
    if (!accountId) return;
    listChatThreads(accountId)
      .then((d) => setThreads(d.threads))
      .catch(() => setThreads([]));
  }, [accountId]);

  useEffect(() => {
    if (!accountId || !threadId) {
      setMessages([]);
      return;
    }
    if (skipNextFetch.current) {
      skipNextFetch.current = false;
      return;
    }
    setLoading(true);
    getChatThread(accountId, threadId)
      .then((d) => setMessages(d.messages))
      .catch(() => setError("Could not load this conversation."))
      .finally(() => setLoading(false));
  }, [accountId, threadId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const send = async () => {
    const text = input.trim();
    if (!text || !accountId || busy) return;
    setBusy(true);
    setError("");
    try {
      let id = threadId;
      if (!id) {
        const thread = await createChatThread(accountId);
        id = thread.id;
        skipNextFetch.current = true;
        setThreadId(id);
      }
      setMessages((m) => [
        ...m,
        {
          id: `local-${Date.now()}`,
          role: "user",
          text,
          answered: true,
          checked: false,
          checked_note: null,
          citations: [],
          steps: [],
          feedback: null,
          created_at: null,
        },
      ]);
      const answer = await postChatMessage(accountId, id, text);
      setMessages((m) => [...m, answer]);
      setInput("");
    } catch {
      setError("Could not get an answer. Try again.");
    } finally {
      setBusy(false);
      listChatThreads(accountId)
        .then((d) => setThreads(d.threads))
        .catch(() => {});
    }
  };

  return (
    <div className={styles.askShell}>
      <aside className={styles.threadRail}>
        <button
          type="button"
          className={styles.newThread}
          onClick={() => setThreadId(null)}
        >
          <Icon name="plus" size={14} /> New question
        </button>
        <div className={styles.threadList}>
          {threads.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`${styles.threadItem} ${t.id === threadId ? styles.threadOn : ""}`}
              onClick={() => setThreadId(t.id)}
            >
              {t.title ?? "Untitled"}
            </button>
          ))}
        </div>
      </aside>

      <div className={styles.chat}>
        <div className={styles.messages} aria-live="polite">
          {loading ? (
            <p className={styles.empty}>Loading…</p>
          ) : messages.length === 0 && !busy ? (
            <p className={styles.empty}>
              Ask a question about your checked records and sources.
            </p>
          ) : (
            messages.map((m) =>
              m.role === "user" ? (
                <p key={m.id} className={styles.question}>
                  {m.text}
                </p>
              ) : (
                <AnswerBlock
                  key={m.id}
                  message={m}
                  accountId={accountId ?? ""}
                  onOpenRecord={onOpenRecord}
                />
              ),
            )
          )}
          {busy && <p className={styles.pending}>Reading sources…</p>}
          {error && <p className={styles.error}>{error}</p>}
          <div ref={bottomRef} />
        </div>

        <form
          className={styles.composer}
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <input
            type="text"
            aria-label="Ask a question"
            placeholder="Ask about orders, clients, documents…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={!accountId || busy}
            maxLength={1000}
          />
          <button
            type="submit"
            className={styles.sendBtn}
            disabled={!accountId || busy || !input.trim()}
            aria-label="Send"
          >
            <Icon name="arrow-right" size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}
