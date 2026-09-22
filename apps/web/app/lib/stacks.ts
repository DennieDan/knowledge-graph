import type { ApiSubstack, ApiSubstackContent, ApiSubstackDetail } from "./api";

export type Scope = "all" | "mine" | "shared" | "workspace";

export interface StackType {
  id: string;
  name: string;
  icon: string;
  desc: string;
}

export interface Substack {
  id: string;
  typeId: string;
  name: string;
  desc: string;
  scope: "mine" | "shared" | "workspace";
  access: string;
  role: string;
  reviewState: "clean" | "pending" | "pending_update" | "unsupported" | "generation_error";
  updated: string;
  docs: string[];
  count: number;
}

export interface DetailSource {
  id: string;
  substackId: string;
  name: string;
  type: "Files" | "Conversations";
  origin: string;
  updated: string;
  note: string;
}

export interface ConversationEntry {
  id: string;
  date: string;
  author: string;
  message: string;
  summary: string;
  sourceIds: string[];
}

export interface UiSegment {
  id: string;
  kind: "text" | "token" | "field";
  value: string;
  name?: string | null;
  ref?: string | null;
  sourceIds: string[];
}

export interface UiContentRevision {
  id: string;
  status: string;
  revision: number;
  segments: UiSegment[];
  conversation: ConversationEntry[];
}

export interface UiSubstackDetail extends UiContentRevision {
  pending: UiContentRevision | null;
  sources: DetailSource[];
  related: { id: string; typeId: string; name: string }[];
}

export const STACK_TYPES: StackType[] = [
  { id: "sales-orders", name: "Sales Orders", icon: "receipt", desc: "Customer POs, line items, quantities, revisions, and dates." },
  { id: "clients", name: "Clients", icon: "building-2", desc: "Customer companies, terms, locations, and account history." },
  { id: "items", name: "Items", icon: "package", desc: "Products, SKUs, materials, specifications, and customer codes." },
  { id: "invoices", name: "Invoices", icon: "file-text", desc: "Sales invoices, GST, payments, credit notes, and InvoiceNow." },
  { id: "suppliers", name: "Suppliers", icon: "building-2", desc: "Material and service vendors, prices, lead times, and performance." },
  { id: "supplier-orders", name: "Supplier Orders", icon: "receipt", desc: "Purchases placed with suppliers and subcontractors." },
  { id: "production-jobs", name: "Production Jobs", icon: "settings", desc: "Work orders, schedules, progress, and blockers." },
  { id: "specifications", name: "Specifications & Revisions", icon: "layers", desc: "Drawings, requirements, approvals, and revision history." },
  { id: "conversations", name: "Conversations", icon: "message-circle", desc: "WhatsApp and email changes, approvals, and commitments." },
  { id: "pics", name: "PICs", icon: "user", desc: "People responsible for each task or decision." },
  { id: "meetings", name: "Meetings", icon: "users", desc: "Meeting notes, action items, and follow-ups." },
  { id: "files", name: "Files", icon: "folder", desc: "Documents, drawings, images, and attachments." },
];

export const SCOPE_TABS: [Scope, string][] = [["all", "All Stacks"], ["mine", "My Stacks"], ["workspace", "Workspace"], ["shared", "Shared with me"]];

export function inScope(ss: Substack, sc: Scope): boolean {
  return sc === "all" || ss.scope === sc || (sc === "workspace" && ss.access === "All members");
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diff = Date.now() - then;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function formatEntryDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.toLocaleDateString(undefined, { day: "numeric", month: "short" })} · ${date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
}

export function toSubstack(row: ApiSubstack): Substack {
  return {
    id: row.id,
    typeId: row.type_id,
    name: row.name,
    desc: row.desc ?? "",
    scope: row.scope,
    access: row.scope === "mine" ? "Only me" : "All members",
    role: row.review_state === "pending_update" ? "Update available" : row.review_state === "unsupported" ? "Needs review" : row.status === "confirmed" ? "Confirmed" : "Proposed",
    reviewState: row.review_state,
    updated: relativeTime(row.updated_at),
    docs: row.docs,
    count: row.count,
  };
}

function toContentRevision(content: ApiSubstackContent): UiContentRevision {
  return {
    id: content.id ?? "",
    status: content.status ?? "",
    revision: content.revision ?? 0,
    segments: (content.segments ?? []).map((segment, index) => ({
      id: `seg-${content.revision ?? 0}-${index}`,
      kind: segment.kind,
      value: segment.value,
      name: segment.name,
      ref: segment.ref,
      sourceIds: segment.source_ids ?? [],
    })),
    conversation: (content.entries ?? []).map((entry, index) => ({
      id: `entry-${content.revision ?? 0}-${index}`,
      date: formatEntryDate(entry.date),
      author: entry.author,
      message: entry.message,
      summary: "",
      sourceIds: entry.source_ids ?? [],
    })),
  };
}

export function toUiDetail(api: ApiSubstackDetail): UiSubstackDetail {
  return {
    ...toContentRevision(api.content),
    pending: api.pending_content ? toContentRevision(api.pending_content) : null,
    sources: api.sources.map((source) => ({
      // Hover matching keys on the cited document id; keep the source row id
      // only as a React key fallback via document_id uniqueness per substack.
      id: source.document_id,
      substackId: source.substack_id ?? "",
      name: source.name,
      type: source.type === "Conversations" ? "Conversations" : "Files",
      origin: source.origin,
      updated: relativeTime(source.updated),
      note: source.role === "attachment" ? "Attachment" : "Supporting evidence",
    })),
    related: api.related.map((item) => ({ id: item.id, typeId: item.type_id, name: item.name })),
  };
}
