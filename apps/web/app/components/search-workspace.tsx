"use client";

import { useEffect, useState } from "react";
import DriveFiles from "./drive-files";
import { getMe, loginUrl, logout, type Me } from "../lib/api";
import styles from "./search-workspace.module.css";

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

const Icon = ({ d }: { d: string }) => (
  <svg
    className={styles.icon}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d={d} />
  </svg>
);

const icons = {
  search: "M21 21l-4.35-4.35M17 10.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0Z",
  graph:
    "M12 5a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM5 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm14 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM10.6 3.6 6 16.4M13.4 3.6 18 16.4M7 18h10",
  build:
    "M14.7 6.3a4.5 4.5 0 0 0-6 5.6L3 17.6V21h3.4l5.7-5.7a4.5 4.5 0 0 0 5.6-6l-3.2 3.2-2.5-.6-.6-2.5 3.3-3.1Z",
  lock: "M6 11V8a6 6 0 1 1 12 0v3M5 11h14v10H5V11Z",
};

export default function SearchWorkspace() {
  const [query, setQuery] = useState("");
  const [sources, setSources] = useState({ Drive: true, WhatsApp: true });
  const [selected, setSelected] = useState(0);
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  const q = query.trim().toLowerCase();
  const results = SEARCHABLE.map((item, index) => ({ item, index })).filter(
    ({ item }) =>
      sources[item.source as "Drive" | "WhatsApp"] &&
      (q === "" || `${item.title} ${item.text}`.toLowerCase().includes(q)),
  );
  const detail = ITEMS[selected] as KnowledgeItem;

  return (
    <div className={styles.app}>
      <header className={styles.topBar}>
        <div className={styles.brand}>
          <span className={styles.brandName}>Knowledge Workspace</span>
          <span className={styles.brandTag}>Company workspace</span>
        </div>
        <form
          className={styles.searchBar}
          role="search"
          onSubmit={(e) => e.preventDefault()}
        >
          <Icon d={icons.search} />
          <input
            type="search"
            aria-label="Search company knowledge"
            placeholder="Search files, conversations, people…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </form>
        {me ? (
          <>
            <span className={styles.userChip}>
              {me.display_name ?? me.email}
            </span>
            <button
              type="button"
              className={styles.btnText}
              onClick={() => logout().then(() => setMe(null))}
            >
              Sign out
            </button>
          </>
        ) : (
          <a className={styles.userChip} href={loginUrl}>
            Sign in with Google
          </a>
        )}
      </header>

      <div className={styles.shell}>
        <aside className={styles.drawer}>
          <nav className={styles.nav} aria-label="Workspace pages">
            <button
              type="button"
              className={`${styles.navItem} ${styles.navItemActive}`}
              aria-current="page"
            >
              <Icon d={icons.search} />
              Search
            </button>
            <button type="button" className={styles.navItem} disabled>
              <Icon d={icons.graph} />
              Knowledge graph
            </button>
            <button type="button" className={styles.navItem} disabled>
              <Icon d={icons.build} />
              Maintenance
            </button>
          </nav>

          <h2 className={styles.sectionLabel}>Sources</h2>
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

          <h2 className={styles.sectionLabel}>Visibility</h2>
          <p className={styles.muted}>
            <Icon d={icons.lock} /> Only information you can access
          </p>

          <h2 className={styles.sectionLabel}>Connections</h2>
          <div className={styles.connection}>
            <span>Google Drive</span>
            {me?.drive_linked ? (
              <span className={styles.chip}>Connected</span>
            ) : (
              <a className={styles.btnText} href={loginUrl}>
                Link
              </a>
            )}
          </div>
          <div className={styles.connection}>
            <span>WhatsApp</span>
            <span className={styles.chip}>Imported</span>
          </div>
        </aside>

        <main className={styles.content}>
          <h1 className={styles.title}>Find company knowledge</h1>
          <p className={styles.muted}>Search across connected sources</p>

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

          {me?.drive_linked && <DriveFiles />}
        </main>

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

      <footer className={styles.footer}>
        Low-fidelity wireframe · Fictional sample data · Actions affect this demo
        only
      </footer>
    </div>
  );
}
