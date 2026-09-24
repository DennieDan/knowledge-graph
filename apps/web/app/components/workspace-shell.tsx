"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "./icons";
import Modal from "./modal";
import SearchView from "./search-view";
import SourcesView from "./sources-view";
import StacksView from "./stacks-view";
import SubstackDetail from "./substack-detail";
import ToCheckView from "./to-check-view";
import WhatsAppConnect from "./whatsapp-connect";
import DrivePicker from "./drive-picker";
import AccountOnboarding from "./account-onboarding";
import AnalyzeDialog from "./analyze-dialog";
import CompanyMembers from "./company-members";
import { CreateSubstackModal } from "./stack-modals";
import {
  STACK_TYPES,
  toSubstack,
  toUiDetail,
  type Scope,
  type StackType,
  type Substack,
  type UiSubstackDetail,
} from "../lib/stacks";
import {
  acceptInvitation,
  activateAccount,
  confirmAllSubstacks,
  confirmSubstack,
  confirmSubstackContent,
  convertToCompany,
  createSubstack,
  getMe,
  getSubstackDetail,
  getSubstacks,
  listAnalysis,
  loginUrl,
  logout,
  retryAnalysis,
  startAnalysis,
  type AnalysisRun,
  type Me,
  type RegenerateMode,
} from "../lib/api";
import { identifyUser, resetAnalytics, track } from "../lib/analytics";
import styles from "./workspace-shell.module.css";

type NavId = "tocheck" | "stacks" | "sources" | "search" | "maintenance";

type ModalState =
  | null
  | { kind: "createSubstack"; typeId: string };

const NAV_ITEMS = [
  { icon: "activity", label: "Analyze workspace", id: "tocheck" },
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

function analysisInProgress(run: AnalysisRun): boolean {
  return ["queued", "embedding", "discovering", "generating"].includes(run.status)
    || run.generation_queued > 0
    || run.generation_running > 0;
}

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
  const stackTypes = STACK_TYPES;
  const [substacks, setSubstacks] = useState<Substack[]>([]);
  const [details, setDetails] = useState<Record<string, UiSubstackDetail>>({});
  const [scope, setScope] = useState<Scope>("all");
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selectedSubstackId, setSelectedSubstackId] = useState<string | null>(null);
  const [detailHistory, setDetailHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [recentIds, setRecentIds] = useState<string[]>([]);
  const [searchVal, setSearchVal] = useState("");
  const [listMode, setListMode] = useState(false);
  const [modal, setModal] = useState<ModalState>(null);
  const [notice, setNotice] = useState("");
  const [me, setMe] = useState<Me | null>(null);
  const [authLoaded, setAuthLoaded] = useState(false);
  const [waOpen, setWaOpen] = useState(false);
  const [driveOpen, setDriveOpen] = useState(false);
  const [membersOpen, setMembersOpen] = useState(false);
  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRun[]>([]);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analyzeOpen, setAnalyzeOpen] = useState(false);
  const [inviteToken, setInviteToken] = useState<string | null>(null);
  const driveSetupPending = useRef(false);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshMe = useCallback(() => {
    getMe()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setAuthLoaded(true));
  }, []);

  useEffect(() => {
    refreshMe();
  }, [refreshMe]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("drive") === "connected") {
      if (!driveSetupPending.current) track("drive_connected");
      driveSetupPending.current = true;
      window.history.replaceState(null, "", window.location.pathname);
    }
    const invite = params.get("invite");
    setInviteToken(invite);
    if (invite && me) {
      acceptInvitation(invite)
        .then(() => {
          window.history.replaceState(null, "", window.location.pathname);
          refreshMe();
        })
        .catch((reason) => setNotice(reason instanceof Error ? reason.message : "Invitation could not be accepted."));
    }
  }, [me, refreshMe]);

  useEffect(() => {
    if (driveSetupPending.current && me) {
      driveSetupPending.current = false;
      refreshMe();
      setDriveOpen(true);
    }
  }, [me, refreshMe]);

  const activeAccount = me?.accounts.find((account) => account.id === me.active_account_id) ?? me?.accounts[0] ?? null;

  useEffect(() => {
    if (me) identifyUser(me, activeAccount);
  }, [me, activeAccount]);

  const signOut = () => {
    resetAnalytics();
    logout().then(() => setMe(null));
  };

  const refreshSubstacks = useCallback(() => {
    if (!activeAccount) return;
    getSubstacks(activeAccount.id)
      .then((rows) => setSubstacks(rows.map(toSubstack)))
      .catch(() => setSubstacks([]));
  }, [activeAccount]);

  const ensureDetail = useCallback((id: string) => {
    getSubstackDetail(id)
      .then((row) => setDetails((prev) => ({ ...prev, [id]: toUiDetail(row) })))
      .catch(() => undefined);
  }, []);

  // Load substacks whenever the active account changes.
  useEffect(() => {
    setSubstacks([]);
    setDetails({});
    setAnalysisRuns([]);
    setSelectedSubstackId(null);
    setSelectedType(null);
    refreshSubstacks();
    if (activeAccount) listAnalysis(activeAccount.id).then(setAnalysisRuns).catch(() => setAnalysisRuns([]));
  }, [activeAccount, refreshSubstacks]);

  useEffect(() => {
    if (!activeAccount || !analysisRuns.some(analysisInProgress)) return;
    const timer = window.setInterval(() => {
      listAnalysis(activeAccount.id).then((runs) => {
        setAnalysisRuns(runs);
        if (!runs.some(analysisInProgress)) {
          refreshSubstacks();
          if (selectedSubstackId) ensureDetail(selectedSubstackId);
        }
      }).catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [activeAccount, analysisRuns, ensureDetail, refreshSubstacks, selectedSubstackId]);

  const closeModal = useCallback(() => setModal(null), []);

  const showNotice = (msg: string) => {
    setNotice(msg);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(""), 5000);
  };

  const handleAnalyze = () => {
    if (!activeAccount || analysisBusy) return;
    track("analyze_workspace_clicked", { substack_count: substacks.length });
    setAnalyzeOpen(true);
  };

  const handleStartAnalysis = async (mode: RegenerateMode, substackIds: string[]) => {
    if (!activeAccount) return;
    setAnalysisBusy(true);
    try {
      const runs = await startAnalysis(activeAccount.id, mode, substackIds);
      track("analysis_started", { mode, record_count: substackIds.length, run_count: runs.length });
      setAnalysisRuns((current) => [...runs, ...current.filter((run) => !runs.some((item) => item.id === run.id))]);
      setAnalyzeOpen(false);
      showNotice(runs.length ? "Workspace analysis queued." : "Nothing changed, so there was nothing to analyze.");
    } finally {
      setAnalysisBusy(false);
    }
  };

  const handleConfirmAll = () => {
    if (!activeAccount || analysisBusy) return;
    setAnalysisBusy(true);
    confirmAllSubstacks(activeAccount.id)
      .then(({ confirmed }) => {
        track("confirm_all", { count: confirmed });
        refreshSubstacks();
        if (selectedSubstackId) ensureDetail(selectedSubstackId);
        showNotice(`Confirmed ${confirmed} proposed ${confirmed === 1 ? "record" : "records"}.`);
      })
      .catch((reason) => showNotice(reason instanceof Error ? reason.message : "Proposals could not be confirmed."))
      .finally(() => setAnalysisBusy(false));
  };

  const handleRetryAnalysis = (runId: string) => {
    setAnalysisBusy(true);
    retryAnalysis(runId)
      .then(({ run }) => setAnalysisRuns((runs) => [run, ...runs.filter((item) => item.id !== run.id)]))
      .catch((reason) => showNotice(reason instanceof Error ? reason.message : "Analysis could not be retried."))
      .finally(() => setAnalysisBusy(false));
  };

  const handleConfirmItem = (ss: Substack) => {
    if (analysisBusy) return;
    setAnalysisBusy(true);
    confirmSubstack(ss.id)
      .then(() => {
        track("substack_confirmed", { method: "single", stack_type: ss.typeId });
        refreshSubstacks();
        showNotice(`"${ss.name}" confirmed.`);
      })
      .catch((reason) => showNotice(reason instanceof Error ? reason.message : "Proposal could not be confirmed."))
      .finally(() => setAnalysisBusy(false));
  };

  const handleConfirmContent = (substackId: string, contentId: string) => {
    confirmSubstackContent(substackId, contentId)
      .then(() => {
        track("substack_confirmed", {
          method: "content",
          stack_type: substacks.find((item) => item.id === substackId)?.typeId ?? null,
        });
        refreshSubstacks();
        ensureDetail(substackId);
        showNotice("Proposed content confirmed.");
      })
      .catch((reason) => showNotice(reason instanceof Error ? reason.message : "Content could not be confirmed."));
  };

  const handleAddSubstack = (input: { name: string; desc: string }) => {
    if (!activeAccount || modal?.kind !== "createSubstack") return;
    const typeId = modal.typeId;
    createSubstack(activeAccount.id, { stack_type: typeId, name: input.name, summary: input.desc })
      .then((row) => {
        track("substack_created", { stack_type: typeId });
        setSubstacks((prev) => [toSubstack(row), ...prev]);
        showNotice(`"${row.name}" added to ${stackTypes.find((t) => t.id === typeId)?.name ?? typeId}.`);
        setModal(null);
      })
      .catch((reason) => showNotice(reason instanceof Error ? reason.message : "Substack could not be created."));
  };

  const openSubstack = (id: string) => {
    const target = substacks.find((item) => item.id === id);
    if (!target) return;
    track("substack_opened", { stack_type: target.typeId, status: target.status, from_view: activeNav });
    setActiveNav("stacks");
    setSelectedType(target.typeId);
    setSelectedSubstackId(id);
    setSearchVal("");
    ensureDetail(id);
    setRecentIds((current) => [id, ...current.filter((recentId) => recentId !== id)].slice(0, 5));
    setDetailHistory((current) => {
      const next = [...current.slice(0, historyIndex + 1), id];
      setHistoryIndex(next.length - 1);
      return next;
    });
  };

  const moveThroughHistory = (offset: number) => {
    const nextIndex = historyIndex + offset;
    const id = detailHistory[nextIndex];
    if (!id) return;
    const target = substacks.find((item) => item.id === id);
    if (!target) return;
    setHistoryIndex(nextIndex);
    setSelectedSubstackId(id);
    setSelectedType(target.typeId);
    ensureDetail(id);
    setRecentIds((current) => [id, ...current.filter((recentId) => recentId !== id)].slice(0, 5));
  };

  if (!authLoaded) return null;
  if (!me || me.needs_account) return <AccountOnboarding me={me} inviteToken={inviteToken} onCreated={refreshMe} />;

  const activeType = selectedType
    ? stackTypes.find((t) => t.id === selectedType)
    : null;
  const selectedSubstack = selectedSubstackId
    ? substacks.find((item) => item.id === selectedSubstackId) ?? null
    : null;

  const selectNav = (id: NavId) => {
    if (id !== activeNav) track("view_changed", { view: id, from_view: activeNav });
    setActiveNav(id);
    if (id !== "stacks") {
      setSelectedType(null);
      setSelectedSubstackId(null);
      setSearchVal("");
    }
  };

  const crumbLabel =
    activeNav === "tocheck"
      ? "Analyze workspace"
      : activeNav === "sources"
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
              <span className={styles.avatar}>{activeAccount?.name[0]?.toUpperCase() ?? "W"}</span>
              <select
                value={activeAccount?.id ?? ""}
                aria-label="Active account"
                onChange={(event) => {
                  track("account_switched");
                  activateAccount(event.target.value).then(refreshMe);
                }}
              >
                {me.accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
              </select>
            </div>
            {activeAccount?.account_type === "company" && activeAccount.role === "admin" && (
              <button type="button" className={styles.inviteMembers} onClick={() => setMembersOpen(true)}>Invite members</button>
            )}
            {activeAccount?.account_type === "personal" && me.hosted_domain &&
             !me.accounts.some((a) => a.account_type === "company" && a.google_domain === me.hosted_domain) && (
              <button type="button" className={styles.inviteMembers} onClick={() => convertToCompany(activeAccount.id).then(() => {
                track("converted_to_company");
                refreshMe();
              })}>Convert to company</button>
            )}
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
            {recentIds.map((id) => substacks.find((item) => item.id === id)).filter((item): item is Substack => Boolean(item)).map((ss) => {
              const type = stackTypes.find((t) => t.id === ss.typeId);
              return (
                <button
                  key={ss.id}
                  onClick={() => openSubstack(ss.id)}
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
                  onClick={signOut}
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
                      setSelectedSubstackId(null);
                      setSearchVal("");
                    }}
                    className={`${styles.crumbBtn} ${selectedType ? "" : styles.crumbActive}`}
                  >
                    Stacks
                  </button>
                  {activeType && (
                    <>
                      <Icon name="chevron-right" size={13} />
                      {selectedSubstack ? (
                        <>
                          <button
                            onClick={() => setSelectedSubstackId(null)}
                            className={styles.crumbBtn}
                          >
                            {activeType.name}
                          </button>
                          <Icon name="chevron-right" size={13} />
                          <span className={styles.crumbActive}>
                            {selectedSubstack.name}
                          </span>
                        </>
                      ) : (
                        <span className={styles.crumbActive}>
                          {activeType.name}
                        </span>
                      )}
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
                    onClick={signOut}
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

          {activeNav === "tocheck" && (
            <ToCheckView
              accountId={activeAccount?.id ?? null}
              stackTypes={stackTypes}
              substacks={substacks}
              busy={analysisBusy}
              notice={notice}
              analysisRuns={analysisRuns}
              onOpen={(ss) => openSubstack(ss.id)}
              onConfirm={handleConfirmItem}
              onAnalyze={handleAnalyze}
              onConfirmAll={handleConfirmAll}
              onRetryAnalysis={handleRetryAnalysis}
            />
          )}
          {activeNav === "sources" && (
            <SourcesView
              me={me}
              activeAccount={activeAccount}
              onManageWhatsApp={() => setWaOpen(true)}
              onManageDrive={() => setDriveOpen(true)}
            />
          )}
          {activeNav === "search" && (
            <SearchView
              accountId={me?.active_account_id ?? null}
              onOpenRecord={openSubstack}
            />
          )}
          {activeNav === "maintenance" && (
            <div className={styles.placeholder}>
              <h1 className={styles.placeholderTitle}>Maintenance</h1>
              <p className={styles.placeholderText}>
                Review stale sources, conflicts, and visibility gaps. Coming
                soon.
              </p>
            </div>
          )}

          <div className={activeNav !== "stacks" ? styles.hiddenView : undefined}>
            {selectedSubstack ? (
              <SubstackDetail
                substack={selectedSubstack}
                stackTypes={stackTypes}
                detail={selectedSubstack ? details[selectedSubstack.id] ?? null : null}
                details={details}
                canGoBack={historyIndex > 0}
                canGoForward={historyIndex < detailHistory.length - 1}
                onBack={() => moveThroughHistory(-1)}
                onForward={() => moveThroughHistory(1)}
                onOpen={openSubstack}
                onEnsureDetail={ensureDetail}
                onConfirmContent={(contentId) => handleConfirmContent(selectedSubstack.id, contentId)}
              />
            ) : (
              <StacksView
                stackTypes={stackTypes}
                substacks={substacks}
                scope={scope}
                selectedType={selectedType}
                searchVal={searchVal}
                listMode={listMode}
                notice={notice}
                onScopeChange={setScope}
                onSelectType={(typeId) => {
                  setSelectedType(typeId);
                  setSelectedSubstackId(null);
                }}
                onSearchChange={setSearchVal}
                onToggleListMode={() => setListMode((v) => !v)}
                onOpenDetails={(ss) => openSubstack(ss.id)}
                onAddItem={(typeId) => setModal({ kind: "createSubstack", typeId })}
              />
            )}
          </div>
        </main>
      </div>

      {/* Modals */}
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
      {waOpen && (
        <WhatsAppConnect
          onClose={() => setWaOpen(false)}
          onChanged={refreshMe}
          accountId={activeAccount?.id}
        />
      )}

      {analyzeOpen && activeAccount && (
        <Modal onClose={() => setAnalyzeOpen(false)}>
          <AnalyzeDialog accountId={activeAccount.id} onClose={() => setAnalyzeOpen(false)} onStart={handleStartAnalysis} />
        </Modal>
      )}

      {driveOpen && activeAccount && (
        <Modal onClose={() => setDriveOpen(false)}>
          <DrivePicker accountId={activeAccount.id} onClose={() => setDriveOpen(false)} />
        </Modal>
      )}

      {membersOpen && activeAccount?.account_type === "company" && activeAccount.google_domain && (
        <Modal onClose={() => setMembersOpen(false)}>
          <CompanyMembers accountId={activeAccount.id} domain={activeAccount.google_domain} onClose={() => setMembersOpen(false)} />
        </Modal>
      )}
    </div>
  );
}
