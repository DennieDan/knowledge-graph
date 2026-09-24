"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties, type MouseEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
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
import {
  NAV_PATHS,
  analyzePath,
  parseReviewState,
  parseRoute,
  reviewStateOf,
  stackPath,
  substackPath,
  type NavId,
} from "../lib/routes";
import { reviewQueue } from "../lib/review-queue";
import { isPlainClick, useAppHistory, type NavMethod } from "../lib/use-app-history";
import styles from "./workspace-shell.module.css";

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

const viewLabel = (view: NavId) => NAV_ITEMS.find((item) => item.id === view)?.label ?? "Stacks";

const FALLBACK_TYPE: StackType = {
  id: "unknown",
  name: "Stack",
  icon: "folder",
  desc: "",
};

const SIDEBAR_DEFAULT = 220;
const SIDEBAR_MIN = 180;
const SIDEBAR_MAX = 420;
const SIDEBAR_STORAGE_KEY = "crosspod.sidebarWidth";

const clampSidebar = (width: number) => Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, Math.round(width)));

function initialSidebarWidth(): number {
  if (typeof window === "undefined") return SIDEBAR_DEFAULT;
  const stored = Number(window.localStorage.getItem(SIDEBAR_STORAGE_KEY));
  return stored ? clampSidebar(stored) : SIDEBAR_DEFAULT;
}

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
  const [sidebarWidth, setSidebarWidth] = useState(initialSidebarWidth);
  const [resizing, setResizing] = useState(false);
  const shellRef = useRef<HTMLDivElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const { href, change, navigate, markNavigation, back, onScroll } = useAppHistory(mainRef);
  const searchParams = useSearchParams();
  const route = parseRoute(href);
  const activeNav = route?.view ?? null;
  const selectedType = route?.view === "stacks" ? route.typeId : null;
  const selectedSubstackId = route?.view === "stacks" ? route.substackId : null;
  const fromReview = selectedSubstackId !== null && searchParams.get("from") === "analyze";
  const reviewState = parseReviewState(searchParams);
  const stackTypes = STACK_TYPES;
  const [substacks, setSubstacks] = useState<Substack[]>([]);
  const [substacksLoaded, setSubstacksLoaded] = useState(false);
  const [details, setDetails] = useState<Record<string, UiSubstackDetail>>({});
  const [scope, setScope] = useState<Scope>("all");
  const [analyzeHref, setAnalyzeHref] = useState(NAV_PATHS.tocheck);
  const [visitedViews, setVisitedViews] = useState<ReadonlySet<NavId>>(new Set());
  const [queueIds, setQueueIds] = useState<string[]>([]);
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
      .catch(() => setSubstacks([]))
      .finally(() => setSubstacksLoaded(true));
  }, [activeAccount]);

  const ensureDetail = useCallback((id: string) => {
    getSubstackDetail(id)
      .then((row) => setDetails((prev) => ({ ...prev, [id]: toUiDetail(row) })))
      .catch(() => undefined);
  }, []);

  // Load substacks whenever the active account changes.
  useEffect(() => {
    setSubstacks([]);
    setSubstacksLoaded(false);
    setDetails({});
    setAnalysisRuns([]);
    setQueueIds([]);
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

  const activeType = selectedType ? stackTypes.find((t) => t.id === selectedType) ?? null : null;
  const selectedSubstack = selectedSubstackId
    ? substacks.find((item) => item.id === selectedSubstackId) ?? null
    : null;

  // Views kept mounted after the first visit so Back returns to the same state.
  if (activeNav && !visitedViews.has(activeNav)) setVisitedViews(new Set(visitedViews).add(activeNav));
  if (activeNav === "tocheck" && analyzeHref !== href) setAnalyzeHref(href);

  // Review queue: the batch captured when the reviewer left the Analyze list.
  const liveQueue = fromReview ? reviewQueue(substacks, reviewState).map((item) => item.ss.id) : [];
  if (fromReview && selectedSubstackId && !queueIds.includes(selectedSubstackId) && liveQueue.includes(selectedSubstackId)) {
    setQueueIds(liveQueue);
  }
  const queueIndex = fromReview && selectedSubstackId ? queueIds.indexOf(selectedSubstackId) : -1;
  const queueNav = queueIndex >= 0
    ? {
      position: queueIndex + 1,
      total: queueIds.length,
      // Previous revisits any earlier item in the batch (even if already
      // confirmed); Next skips items that no longer need checking.
      prevId: queueIds.slice(0, queueIndex).reverse().find((id) => substacks.some((item) => item.id === id)) ?? null,
      nextId: queueIds.slice(queueIndex + 1).find((id) => liveQueue.includes(id)) ?? null,
    }
    : null;

  // Poll while any record is being generated; reload the open record's detail once it finishes.
  const generatingIds = substacks.filter((item) => item.generating).map((item) => item.id).join(",");
  const selectedGenerating = selectedSubstack?.generating ?? false;
  useEffect(() => {
    if (!generatingIds) return;
    const timer = window.setInterval(refreshSubstacks, 2500);
    return () => window.clearInterval(timer);
  }, [generatingIds, refreshSubstacks]);

  useEffect(() => {
    if (selectedSubstackId) ensureDetail(selectedSubstackId);
  }, [ensureDetail, selectedSubstackId, selectedGenerating]);

  useEffect(() => {
    setSearchVal("");
  }, [selectedType, selectedSubstackId]);

  useEffect(() => {
    if (!selectedSubstack) return;
    const id = selectedSubstack.id;
    setRecentIds((current) => current[0] === id ? current : [id, ...current.filter((recentId) => recentId !== id)].slice(0, 5));
  }, [selectedSubstack]);

  // Keep the type segment of a record URL canonical (e.g. after a re-file).
  useEffect(() => {
    if (!selectedSubstack || selectedType === selectedSubstack.typeId) return;
    const query = searchParams.toString();
    navigate(`${substackPath(selectedSubstack)}${query ? `?${query}` : ""}`, "link", { replace: true });
  }, [navigate, searchParams, selectedSubstack, selectedType]);

  // Navigation analytics run on the URL change so browser Back/Forward count too.
  const trackedChange = useRef<typeof change>(null);
  useEffect(() => {
    if (!change || trackedChange.current === change) return;
    const current = parseRoute(change.href);
    const previous = change.previousHref ? parseRoute(change.previousHref) : null;
    const openedId = current?.view === "stacks" ? current.substackId : null;
    const previousId = previous?.view === "stacks" ? previous.substackId : null;
    if (openedId && !substacksLoaded) return;
    trackedChange.current = change;
    const view = current?.view ?? null;
    const fromView = previous?.view ?? null;
    if (view && view !== fromView) track("view_changed", { view, from_view: fromView, method: change.method });
    if (current?.view === "stacks" && openedId && openedId !== previousId) {
      track("substack_opened", {
        stack_type: current.typeId,
        status: substacks.find((item) => item.id === openedId)?.status ?? null,
        from_view: fromView,
        entry: change.method,
      });
    }
  }, [change, substacks, substacksLoaded]);

  const closeModal = useCallback(() => setModal(null), []);

  const commitSidebarWidth = (width: number) => {
    const next = clampSidebar(width);
    setSidebarWidth(next);
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
  };

  const handleResizeStart = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setResizing(true);
  };

  const handleResizeMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!resizing) return;
    const left = shellRef.current?.getBoundingClientRect().left ?? 0;
    setSidebarWidth(clampSidebar(event.clientX - left));
  };

  const handleResizeEnd = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!resizing) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setResizing(false);
    commitSidebarWidth(sidebarWidth);
  };

  const handleResizeKey = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 48 : 16;
    if (event.key === "ArrowLeft") commitSidebarWidth(sidebarWidth - step);
    else if (event.key === "ArrowRight") commitSidebarWidth(sidebarWidth + step);
    else if (event.key === "Home") commitSidebarWidth(SIDEBAR_MIN);
    else if (event.key === "End") commitSidebarWidth(SIDEBAR_MAX);
    else return;
    event.preventDefault();
  };

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

  const stepQueue = (id: string, direction: "prev" | "next" | "auto") => {
    const target = substacks.find((item) => item.id === id);
    if (!target || !queueNav) return;
    track("review_queue_step", { direction, position: queueNav.position, total: queueNav.total });
    navigate(substackPath(target, reviewState), "review_queue", { replace: true });
  };

  const handleConfirmContent = (substackId: string, contentId: string) => {
    const advanceTo = substackId === selectedSubstackId ? queueNav?.nextId ?? null : null;
    confirmSubstackContent(substackId, contentId)
      .then(() => {
        track("substack_confirmed", {
          method: "content",
          stack_type: substacks.find((item) => item.id === substackId)?.typeId ?? null,
        });
        refreshSubstacks();
        ensureDetail(substackId);
        if (advanceTo) stepQueue(advanceTo, "auto");
        showNotice(advanceTo ? "Confirmed. Showing the next item to check." : "Proposed content confirmed.");
      })
      .catch((reason) => showNotice(reason instanceof Error ? reason.message : "Content could not be confirmed."));
  };

  const handleAddSubstack = async (input: { name: string; desc: string; generate: boolean }) => {
    if (!activeAccount || modal?.kind !== "createSubstack") return;
    const typeId = modal.typeId;
    const row = await createSubstack(activeAccount.id, {
      stack_type: typeId,
      name: input.name,
      summary: input.desc,
      generate: input.generate,
    });
    track("substack_created", { stack_type: typeId, generated: input.generate });
    const created = toSubstack(row);
    setSubstacks((prev) => [created, ...prev]);
    setModal(null);
    if (input.generate) {
      showNotice(`Generating "${row.name}" from your files. It will be ready to check shortly.`);
      navigate(substackPath(created), "link");
    } else {
      showNotice(`"${row.name}" added to ${stackTypes.find((t) => t.id === typeId)?.name ?? typeId}.`);
    }
  };

  const openSubstack = (id: string) => {
    const target = substacks.find((item) => item.id === id);
    if (target) navigate(substackPath(target), "link");
  };

  /** Labels a plain <Link> click; modified clicks open a new tab and are left alone. */
  const linkClick = (target: string, method: NavMethod) => (event: MouseEvent) => {
    if (isPlainClick(event) && target !== href) markNavigation(method);
  };

  const openFromQueue = (event: MouseEvent, target: string) => {
    setQueueIds(reviewQueue(substacks, reviewStateOf(analyzeHref)).map((item) => item.ss.id));
    linkClick(target, "link")(event);
  };

  const hrefLabel = (target: string) => {
    const r = parseRoute(target);
    if (!r) return "previous page";
    if (r.view !== "stacks") return viewLabel(r.view);
    if (r.substackId) return substacks.find((item) => item.id === r.substackId)?.name ?? "previous record";
    return stackTypes.find((t) => t.id === r.typeId)?.name ?? "Stacks";
  };

  // In-app Back follows browser history while it stays inside the app, and
  // falls back to the parent page after a refresh or an opened link.
  const backHref = change?.backHref ?? null;
  const parentHref = fromReview ? analyzePath(reviewState) : stackPath(selectedType);
  const goBack = () => {
    const target = backHref ?? parentHref;
    track("nav_back_clicked", { target_view: parseRoute(target)?.view ?? null, fallback: !backHref });
    if (backHref) back();
    else navigate(parentHref, "in_app_back");
  };

  if (!authLoaded) return null;
  if (!me || me.needs_account) return <AccountOnboarding me={me} inviteToken={inviteToken} onCreated={refreshMe} />;

  const crumbClick = (target: string, level: number, targetView: NavId) => (event: MouseEvent) => {
    track("breadcrumb_clicked", { level, target_view: targetView });
    linkClick(target, "breadcrumb")(event);
  };

  const crumbLabel = activeNav === "stacks" ? null : activeNav ? viewLabel(activeNav) : "Not found";
  const analyzeState = reviewStateOf(analyzeHref);

  return (
    <div className={`${styles.app} ${resizing ? styles.appResizing : ""}`}>
      <div
        ref={shellRef}
        className={`${styles.shell} ${sidebarOpen ? "" : styles.shellCollapsed}`}
        style={{ "--sidebar-width": `${sidebarWidth}px` } as CSSProperties}
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
                  if (selectedSubstackId) navigate(stackPath(selectedType), "link");
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
            {NAV_ITEMS.map((item) => {
              const target = item.id === "tocheck" ? analyzeHref : NAV_PATHS[item.id];
              return (
                <Link
                  key={item.id}
                  href={target}
                  scroll={false}
                  aria-current={activeNav === item.id ? "page" : undefined}
                  onClick={linkClick(target, "sidebar")}
                  className={`${styles.navItem} ${activeNav === item.id ? styles.navItemActive : ""}`}
                >
                  <Icon name={item.icon} size={15} />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div>
            <div className={styles.sectionLabel}>Recent Substacks</div>
            {recentIds.map((id) => substacks.find((item) => item.id === id)).filter((item): item is Substack => Boolean(item)).map((ss) => {
              const type = stackTypes.find((t) => t.id === ss.typeId);
              const target = substackPath(ss);
              return (
                <Link
                  key={ss.id}
                  href={target}
                  scroll={false}
                  onClick={linkClick(target, "sidebar")}
                  className={styles.recentBtn}
                >
                  <span className={styles.recentIcon}>
                    <Icon name={type?.icon ?? "file-text"} size={11} />
                  </span>
                  <span className={styles.recentName}>{ss.name}</span>
                </Link>
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

        {sidebarOpen && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize sidebar"
            aria-valuemin={SIDEBAR_MIN}
            aria-valuemax={SIDEBAR_MAX}
            aria-valuenow={sidebarWidth}
            tabIndex={0}
            title="Drag to resize · double-click to reset"
            className={`${styles.resizer} ${resizing ? styles.resizerActive : ""}`}
            onPointerDown={handleResizeStart}
            onPointerMove={handleResizeMove}
            onPointerUp={handleResizeEnd}
            onPointerCancel={handleResizeEnd}
            onDoubleClick={() => commitSidebarWidth(SIDEBAR_DEFAULT)}
            onKeyDown={handleResizeKey}
          />
        )}

        {/* ── Main ── */}
        <main ref={mainRef} className={styles.main} onScroll={onScroll}>
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
              ) : fromReview ? (
                <>
                  <Link
                    href={parentHref}
                    scroll={false}
                    onClick={crumbClick(parentHref, 0, "tocheck")}
                    className={styles.crumbBtn}
                  >
                    Analyze workspace
                  </Link>
                  <Icon name="chevron-right" size={13} />
                  <span className={styles.crumbActive}>{selectedSubstack?.name ?? "Record"}</span>
                </>
              ) : (
                <>
                  {selectedType ? (
                    <Link
                      href={NAV_PATHS.stacks}
                      scroll={false}
                      onClick={crumbClick(NAV_PATHS.stacks, 0, "stacks")}
                      className={styles.crumbBtn}
                    >
                      Stacks
                    </Link>
                  ) : (
                    <span className={styles.crumbActive}>Stacks</span>
                  )}
                  {selectedType && (
                    <>
                      <Icon name="chevron-right" size={13} />
                      {selectedSubstackId ? (
                        <>
                          <Link
                            href={stackPath(selectedType)}
                            scroll={false}
                            onClick={crumbClick(stackPath(selectedType), 1, "stacks")}
                            className={styles.crumbBtn}
                          >
                            {activeType?.name ?? "Stack"}
                          </Link>
                          <Icon name="chevron-right" size={13} />
                          <span className={styles.crumbActive}>
                            {selectedSubstack?.name ?? "Record"}
                          </span>
                        </>
                      ) : (
                        <span className={styles.crumbActive}>
                          {activeType?.name ?? "Stack"}
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

          {visitedViews.has("tocheck") && (
            <div className={activeNav === "tocheck" ? styles.view : styles.hiddenView}>
              <ToCheckView
                accountId={activeAccount?.id ?? null}
                stackTypes={stackTypes}
                substacks={substacks}
                busy={analysisBusy}
                notice={notice}
                analysisRuns={analysisRuns}
                review={analyzeState}
                onReviewChange={(next) => navigate(analyzePath(next), "link", { replace: true })}
                substackHref={(ss) => substackPath(ss, analyzeState)}
                onOpen={openFromQueue}
                onConfirm={handleConfirmItem}
                onAnalyze={handleAnalyze}
                onConfirmAll={handleConfirmAll}
                onRetryAnalysis={handleRetryAnalysis}
              />
            </div>
          )}
          {activeNav === "sources" && (
            <SourcesView
              me={me}
              activeAccount={activeAccount}
              onManageWhatsApp={() => setWaOpen(true)}
              onManageDrive={() => setDriveOpen(true)}
            />
          )}
          {visitedViews.has("search") && (
            <div className={activeNav === "search" ? styles.view : styles.hiddenView}>
              <SearchView
                accountId={me?.active_account_id ?? null}
                onOpenRecord={openSubstack}
              />
            </div>
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
          {!route && (
            <div className={styles.placeholder}>
              <h1 className={styles.placeholderTitle}>Page not found</h1>
              <p className={styles.placeholderText}>
                This address doesn&apos;t match a page. <Link href={NAV_PATHS.stacks}>Go to Stacks</Link>
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
                backLabel={`Back to ${hrefLabel(backHref ?? parentHref)}`}
                onBack={goBack}
                queue={queueNav && {
                  position: queueNav.position,
                  total: queueNav.total,
                  onPrev: queueNav.prevId ? () => stepQueue(queueNav.prevId!, "prev") : null,
                  onNext: queueNav.nextId ? () => stepQueue(queueNav.nextId!, "next") : null,
                }}
                onOpen={openSubstack}
                onEnsureDetail={ensureDetail}
                onConfirmContent={(contentId) => handleConfirmContent(selectedSubstack.id, contentId)}
              />
            ) : selectedSubstackId ? (
              substacksLoaded && (
                <div className={styles.placeholder}>
                  <h1 className={styles.placeholderTitle}>Record not available</h1>
                  <p className={styles.placeholderText}>
                    This record isn&apos;t in {activeAccount?.name ?? "this workspace"}. It may belong to another
                    account you can switch to, or you may not have access.{" "}
                    <Link href={stackPath(selectedType)}>Back to {activeType?.name ?? "Stacks"}</Link>
                  </p>
                </div>
              )
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
                onSelectType={(typeId) => navigate(stackPath(typeId), "link")}
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
          linked={me.whatsapp_linked}
          displayName={me.display_name}
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
