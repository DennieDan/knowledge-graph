"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "./icons";
import Modal from "./modal";
import SearchView from "./search-view";
import SourcesView from "./sources-view";
import StacksView from "./stacks-view";
import WhatsAppConnect from "./whatsapp-connect";
import {
  CreateStackModal,
  CreateSubstackModal,
  SubstackDetails,
} from "./stack-modals";
import {
  INITIAL_SUBSTACKS,
  STACK_TYPES,
  loadStacksState,
  saveStacksState,
  type Scope,
  type StackType,
  type Substack,
} from "../lib/stacks";
import { getMe, loginUrl, logout, type Me } from "../lib/api";
import styles from "./workspace-shell.module.css";

type NavId = "stacks" | "sources" | "search" | "maintenance";

type ModalState =
  | null
  | { kind: "details"; ss: Substack }
  | { kind: "createSubstack"; typeId: string }
  | { kind: "createStack" };

const NAV_ITEMS = [
  { icon: "search", label: "Search", id: "search" },
  { icon: "layers", label: "Stacks", id: "stacks" },
  { icon: "database", label: "Sources", id: "sources" },
  { icon: "activity", label: "Maintenance", id: "maintenance" },
] as const satisfies { icon: string; label: string; id: NavId }[];

const FALLBACK_TYPE: StackType = {
  id: "unknown",
  name: "Stack",
  icon: "folder",
  desc: "",
};

function initials(me: Me): string {
  const name = me.display_name ?? me.email;
  return name
    .split(/[\s@]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}

export default function WorkspaceShell() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeNav, setActiveNav] = useState<NavId>("stacks");
  const [stackTypes, setStackTypes] = useState<StackType[]>(STACK_TYPES);
  const [substacks, setSubstacks] = useState<Substack[]>(INITIAL_SUBSTACKS);
  const [hydrated, setHydrated] = useState(false);
  const [scope, setScope] = useState<Scope>("all");
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [searchVal, setSearchVal] = useState("");
  const [listMode, setListMode] = useState(false);
  const [modal, setModal] = useState<ModalState>(null);
  const [notice, setNotice] = useState("");
  const [me, setMe] = useState<Me | null>(null);
  const [waOpen, setWaOpen] = useState(false);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshMe = useCallback(() => {
    getMe()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  useEffect(() => {
    refreshMe();
  }, [refreshMe]);

  // Restore locally persisted stacks after hydration.
  useEffect(() => {
    const stored = loadStacksState();
    if (stored) {
      setStackTypes(stored.stackTypes);
      setSubstacks(stored.substacks);
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated) saveStacksState({ stackTypes, substacks });
  }, [stackTypes, substacks, hydrated]);

  const closeModal = useCallback(() => setModal(null), []);

  const showNotice = (msg: string) => {
    setNotice(msg);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(""), 5000);
  };

  const handleAddStack = (type: StackType) => {
    setStackTypes((prev) => [...prev, type]);
    showNotice(`"${type.name}" stack created.`);
    setModal(null);
  };

  const handleAddSubstack = (ss: Omit<Substack, "id">) => {
    const newSS: Substack = { ...ss, id: "ss-" + Date.now() };
    setSubstacks((prev) => [newSS, ...prev]);
    showNotice(
      `"${newSS.name}" added to ${stackTypes.find((t) => t.id === ss.typeId)?.name ?? ss.typeId}.`,
    );
    setModal(null);
  };

  const activeType = selectedType
    ? stackTypes.find((t) => t.id === selectedType)
    : null;

  const selectNav = (id: NavId) => {
    setActiveNav(id);
    if (id !== "stacks") {
      setSelectedType(null);
      setSearchVal("");
    }
  };

  const crumbLabel =
    activeNav === "sources"
      ? "Sources"
      : activeNav === "search"
        ? "Search"
        : activeNav === "maintenance"
          ? "Maintenance"
          : null;

  return (
    <div className={styles.app}>
      <div
        className={`${styles.shell} ${sidebarOpen ? "" : styles.shellCollapsed}`}
      >
        {/* ── Sidebar ── */}
        <aside
          className={`${styles.sidebar} ${sidebarOpen ? "" : styles.sidebarClosed}`}
        >
          <div className={styles.brand}>
            <span className={styles.brandIcon}>
              <Icon name="layers" size={15} />
            </span>
            crosspod
          </div>

          <div>
            <div className={styles.sectionLabel}>Workspace</div>
            <div className={styles.workspaceRow}>
              <span className={styles.avatar}>S</span>
              <span>Studio North</span>
            </div>
          </div>

          <nav aria-label="Application">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                onClick={() => selectNav(item.id)}
                className={`${styles.navItem} ${activeNav === item.id ? styles.navItemActive : ""}`}
              >
                <Icon name={item.icon} size={15} />
                {item.label}
              </button>
            ))}
          </nav>

          <div>
            <div className={styles.sectionLabel}>Your Groups</div>
            {["Product & Design", "All members"].map((g) => (
              <div key={g} className={styles.groupItem}>
                {g}
              </div>
            ))}
          </div>

          <div>
            <div className={styles.sectionLabel}>Recent Substacks</div>
            {substacks.slice(0, 5).map((ss) => {
              const type = stackTypes.find((t) => t.id === ss.typeId);
              return (
                <button
                  key={ss.id}
                  onClick={() => {
                    setActiveNav("stacks");
                    setSelectedType(ss.typeId);
                    setSearchVal("");
                  }}
                  className={styles.recentBtn}
                >
                  <span className={styles.recentIcon}>
                    <Icon name={type?.icon ?? "file-text"} size={11} />
                  </span>
                  <span className={styles.recentName}>{ss.name}</span>
                </button>
              );
            })}
          </div>

          <div className={styles.profile}>
            {me ? (
              <>
                <span className={styles.avatar}>{initials(me)}</span>
                <div className={styles.profileText}>
                  <div className={styles.profileName}>
                    {me.display_name ?? me.email}
                  </div>
                  <div className={styles.profileSub}>{me.email}</div>
                </div>
                <button
                  type="button"
                  className={styles.signOut}
                  onClick={() => logout().then(() => setMe(null))}
                >
                  Sign out
                </button>
              </>
            ) : (
              <a href={loginUrl} className={styles.signIn}>
                Sign in with Google
              </a>
            )}
          </div>
        </aside>

        {/* ── Main ── */}
        <main className={styles.main}>
          <header className={styles.topbar}>
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              className={styles.signOut}
              style={{ padding: 6 }}
              aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
            >
              <Icon name="sidebar" size={18} />
            </button>

            <nav aria-label="Breadcrumb" className={styles.crumb}>
              {crumbLabel ? (
                <span className={styles.crumbActive}>{crumbLabel}</span>
              ) : (
                <>
                  <button
                    onClick={() => {
                      setSelectedType(null);
                      setSearchVal("");
                    }}
                    className={`${styles.crumbBtn} ${selectedType ? "" : styles.crumbActive}`}
                  >
                    Stacks
                  </button>
                  {activeType && (
                    <>
                      <Icon name="chevron-right" size={13} />
                      <span className={styles.crumbActive}>
                        {activeType.name}
                      </span>
                    </>
                  )}
                </>
              )}
            </nav>

            <div className={styles.topAuth}>
              {me ? (
                <>
                  <span className={styles.avatar}>{initials(me)}</span>
                  <button
                    type="button"
                    className={styles.signOut}
                    onClick={() => logout().then(() => setMe(null))}
                  >
                    Sign out
                  </button>
                </>
              ) : (
                <a href={loginUrl} className={styles.topSignIn}>
                  Sign in with Google
                </a>
              )}
            </div>
          </header>

          {activeNav === "sources" && (
            <SourcesView me={me} onManageWhatsApp={() => setWaOpen(true)} />
          )}
          {activeNav === "search" && <SearchView me={me} />}
          {activeNav === "maintenance" && (
            <div className={styles.placeholder}>
              <h1 className={styles.placeholderTitle}>Maintenance</h1>
              <p className={styles.placeholderText}>
                Review stale sources, conflicts, and visibility gaps. Coming
                soon.
              </p>
            </div>
          )}

          <div
            className={activeNav !== "stacks" ? styles.hiddenView : undefined}
          >
            <StacksView
              stackTypes={stackTypes}
              substacks={substacks}
              scope={scope}
              selectedType={selectedType}
              searchVal={searchVal}
              listMode={listMode}
              notice={notice}
              onScopeChange={setScope}
              onSelectType={setSelectedType}
              onSearchChange={setSearchVal}
              onToggleListMode={() => setListMode((v) => !v)}
              onOpenDetails={(ss) => setModal({ kind: "details", ss })}
              onAddItem={(typeId) =>
                setModal({ kind: "createSubstack", typeId })
              }
              onCreateStack={() => setModal({ kind: "createStack" })}
            />
          </div>
        </main>
      </div>

      {/* Modals */}
      {modal?.kind === "details" && (
        <Modal onClose={closeModal}>
          <SubstackDetails
            ss={modal.ss}
            type={
              stackTypes.find((t) => t.id === modal.ss.typeId) ?? FALLBACK_TYPE
            }
            onClose={closeModal}
          />
        </Modal>
      )}
      {modal?.kind === "createSubstack" && (
        <Modal onClose={closeModal}>
          <CreateSubstackModal
            type={
              stackTypes.find((t) => t.id === modal.typeId) ?? FALLBACK_TYPE
            }
            onClose={closeModal}
            onSubmit={handleAddSubstack}
          />
        </Modal>
      )}
      {modal?.kind === "createStack" && (
        <Modal onClose={closeModal}>
          <CreateStackModal onClose={closeModal} onSubmit={handleAddStack} />
        </Modal>
      )}

      {waOpen && (
        <WhatsAppConnect
          onClose={() => setWaOpen(false)}
          onChanged={refreshMe}
        />
      )}
    </div>
  );
}
