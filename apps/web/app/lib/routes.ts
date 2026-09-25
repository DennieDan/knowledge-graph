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

/** Analyze workspace list state: queue kind, stack types (empty = all), page. */
export interface ReviewState {
  filter: ReviewFilter;
  types: string[];
  page: number;
}

export function parseReviewState(params: URLSearchParams): ReviewState {
  const requested = new Set((params.get("types") ?? "").split(","));
  const page = Number.parseInt(params.get("page") ?? "", 10);
  return {
    filter: parseReviewFilter(params.get("filter")),
    types: STACK_TYPES.filter((type) => requested.has(type.id)).map((type) => type.id),
    page: page > 1 ? page : 1,
  };
}

export const reviewStateOf = (href: string) => parseReviewState(new URLSearchParams(href.split("?")[1] ?? ""));

function reviewQuery(review: Partial<ReviewState>): string[] {
  const query: string[] = [];
  if (review.filter && review.filter !== "all") query.push(`filter=${review.filter}`);
  if (review.types?.length) query.push(`types=${review.types.map(encodeURIComponent).join(",")}`);
  if (review.page && review.page > 1) query.push(`page=${review.page}`);
  return query;
}

export function analyzePath(review: Partial<ReviewState>): string {
  const query = reviewQuery(review);
  return query.length ? `${NAV_PATHS.tocheck}?${query.join("&")}` : NAV_PATHS.tocheck;
}

export const stackPath = (typeId: string | null) =>
  typeId ? `/stacks/${encodeURIComponent(typeId)}` : NAV_PATHS.stacks;

/** `review` marks a substack opened from the Analyze workspace queue. */
export function substackPath(ss: { id: string; typeId: string }, review?: ReviewState): string {
  const base = `${stackPath(ss.typeId)}/${encodeURIComponent(ss.id)}`;
  if (!review) return base;
  return [`${base}?from=analyze`, ...reviewQuery({ ...review, page: 1 })].join("&");
}
