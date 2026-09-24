import type { ReviewState } from "./routes";
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

/** Substacks waiting for a person, in display order, for the given filters. */
export function reviewQueue(
  substacks: Substack[],
  { filter, types }: Pick<ReviewState, "filter" | "types">,
): { ss: Substack; kind: QueueKind }[] {
  return substacks
    .map((ss) => ({ ss, kind: queueKind(ss) }))
    .filter((item): item is { ss: Substack; kind: QueueKind } =>
      item.kind !== null
      && (filter === "all" || item.kind === filter)
      && (types.length === 0 || types.includes(item.ss.typeId)));
}
