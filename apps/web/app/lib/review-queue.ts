import type { ReviewFilter } from "./routes";
import type { Substack } from "./stacks";

export type QueueKind = "new" | "update" | "attention";

export function queueKind(ss: Substack): QueueKind | null {
  if (ss.reviewState === "unsupported" || ss.reviewState === "generation_error") {
    return "attention";
  }
  if (ss.status !== "confirmed") return "new";
  if (ss.reviewState === "pending_update") return "update";
  return null;
}

/** Substacks waiting for a person, in display order, for the given filter. */
export function reviewQueue(substacks: Substack[], filter: ReviewFilter): { ss: Substack; kind: QueueKind }[] {
  return substacks
    .map((ss) => ({ ss, kind: queueKind(ss) }))
    .filter((item): item is { ss: Substack; kind: QueueKind } =>
      item.kind !== null && (filter === "all" || item.kind === filter));
}
