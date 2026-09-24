import { STACK_TYPES } from "./stacks";

// URLs are sent to analytics as pageviews: they may only contain internal IDs
// and stack type IDs — never names, message text or search queries.

export type NavId = "tocheck" | "stacks" | "sources" | "search" | "maintenance";

export type ReviewFilter = "all" | "new" | "update" | "attention" | "findings";

export type AppRoute =
  | { view: Exclude<NavId, "stacks"> }
  | { view: "stacks"; typeId: string | null; substackId: string | null };

export const NAV_PATHS: Record<NavId, string> = {
  tocheck: "/analyze",
  search: "/search",
  stacks: "/stacks",
  sources: "/sources",
  maintenance: "/maintenance",
};

const VIEW_BY_SEGMENT: Record<string, Exclude<NavId, "stacks">> = {
  analyze: "tocheck",
  search: "search",
  sources: "sources",
  maintenance: "maintenance",
};

const REVIEW_FILTERS: ReviewFilter[] = ["all", "new", "update", "attention", "findings"];

export const pathOf = (href: string) => href.split("?")[0] ?? href;

export function parseRoute(href: string): AppRoute | null {
  const [first, typeId, substackId, ...rest] = pathOf(href).split("/").filter(Boolean);
  if (!first) return null;
  if (first !== "stacks") {
    const view = VIEW_BY_SEGMENT[first];
    return view && typeId === undefined ? { view } : null;
  }
  if (rest.length > 0) return null;
  if (typeId && !substackId && !STACK_TYPES.some((type) => type.id === typeId)) return null;
  return { view: "stacks", typeId: typeId ?? null, substackId: substackId ?? null };
}

export function parseReviewFilter(value: string | null): ReviewFilter {
  return REVIEW_FILTERS.find((filter) => filter === value) ?? "all";
}

export const analyzePath = (filter: ReviewFilter) =>
  filter === "all" ? NAV_PATHS.tocheck : `${NAV_PATHS.tocheck}?filter=${filter}`;

export const stackPath = (typeId: string | null) =>
  typeId ? `/stacks/${encodeURIComponent(typeId)}` : NAV_PATHS.stacks;

/** `review` marks a substack opened from the Analyze workspace queue. */
export function substackPath(ss: { id: string; typeId: string }, review?: ReviewFilter): string {
  const base = `${stackPath(ss.typeId)}/${encodeURIComponent(ss.id)}`;
  if (!review) return base;
  return `${base}?from=analyze${review === "all" ? "" : `&filter=${review}`}`;
}
