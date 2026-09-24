"use client";

import { useCallback, useEffect, useRef, useState, type MouseEvent, type RefObject, type UIEvent } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { pathOf } from "./routes";

export type NavMethod =
  | "direct"
  | "link"
  | "sidebar"
  | "breadcrumb"
  | "in_app_back"
  | "browser_history"
  | "review_queue";

export interface RouteChange {
  href: string;
  previousHref: string | null;
  /** The in-app entry that browser Back would return to, if any. */
  backHref: string | null;
  method: NavMethod;
}

/**
 * Mirrors the browser history stack for in-app pages so the app can label its
 * own Back button, tell how a navigation happened, and restore scroll position
 * of the scrolling container on Back/Forward.
 */
export function useAppHistory(scroller: RefObject<HTMLElement | null>) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const href = search ? `${pathname}?${search}` : pathname;
  const stack = useRef<{ entries: string[]; index: number }>({ entries: [], index: -1 });
  const popped = useRef(false);
  const pending = useRef<NavMethod | null>(null);
  const replacing = useRef(false);
  const scrollTops = useRef(new Map<string, number>());
  const currentHref = useRef(href);
  const [change, setChange] = useState<RouteChange | null>(null);

  useEffect(() => {
    const onPop = () => { popped.current = true; };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    const s = stack.current;
    const previousHref = s.entries[s.index] ?? null;
    if (previousHref === href) return;
    let method: NavMethod = pending.current ?? "link";
    const isPop = popped.current;
    if (s.index < 0) {
      s.entries = [href];
      s.index = 0;
      method = "direct";
    } else if (isPop) {
      method = pending.current === "in_app_back" ? "in_app_back" : "browser_history";
      if (s.entries[s.index - 1] && pathOf(s.entries[s.index - 1]!) === pathname) s.index -= 1;
      else if (s.entries[s.index + 1] && pathOf(s.entries[s.index + 1]!) === pathname) s.index += 1;
      else {
        s.entries = [href];
        s.index = 0;
      }
      s.entries[s.index] = href;
    } else if (replacing.current || (previousHref && pathOf(previousHref) === pathname)) {
      s.entries[s.index] = href;
    } else {
      s.entries = [...s.entries.slice(0, s.index + 1), href];
      s.index += 1;
    }
    const replaced = replacing.current;
    popped.current = false;
    pending.current = null;
    replacing.current = false;
    currentHref.current = href;

    const el = scroller.current;
    if (el && isPop) {
      const top = scrollTops.current.get(href) ?? 0;
      requestAnimationFrame(() => { el.scrollTop = top; });
    } else if (el && !replaced && previousHref && pathOf(previousHref) !== pathname) {
      el.scrollTop = 0;
    }
    setChange({ href, previousHref, backHref: s.entries[s.index - 1] ?? null, method });
  }, [href, pathname, scroller]);

  /** Call from a plain (unmodified) click on a <Link> to label the navigation. */
  const markNavigation = useCallback((method: NavMethod) => {
    pending.current = method;
  }, []);

  const navigate = useCallback((to: string, method: NavMethod, options?: { replace?: boolean }) => {
    pending.current = method;
    replacing.current = Boolean(options?.replace);
    if (options?.replace) router.replace(to, { scroll: false });
    else router.push(to, { scroll: false });
  }, [router]);

  const back = useCallback(() => {
    pending.current = "in_app_back";
    router.back();
  }, [router]);

  const onScroll = useCallback((event: UIEvent<HTMLElement>) => {
    scrollTops.current.set(currentHref.current, event.currentTarget.scrollTop);
  }, []);

  return { href, change, navigate, markNavigation, back, onScroll };
}

/** True for a primary-button click without modifiers (i.e. not "open in new tab"). */
export function isPlainClick(event: MouseEvent): boolean {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}
