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

export interface DetailToken {
  id: string;
  label: string;
  value: string;
  sourceIds: string[];
}

export interface ConversationEntry {
  id: string;
  date: string;
  author: string;
  message: string;
  summary: string;
  sourceIds: string[];
}

export interface SubstackDetail {
  tokens?: DetailToken[];
  conversation?: ConversationEntry[];
  sources: DetailSource[];
  relatedIds: string[];
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

const substack = (id: string, typeId: string, name: string, desc: string, updated: string, docs: string[]): Substack => ({
  id, typeId, name, desc, scope: "workspace", access: "All members", role: "Can view", updated, docs, count: docs.length,
});

export const INITIAL_SUBSTACKS: Substack[] = [
  substack("so-2431", "sales-orders", "PO2431", "Precision parts order for Acme Engineering.", "12 min ago", ["PO2431.pdf", "Group ABC"]),
  substack("so-2432", "sales-orders", "PO2432", "Repeat order with revised delivery dates.", "1 hour ago", ["PO2432.pdf", "Order update.eml"]),
  substack("cl-acme", "clients", "Acme Engineering", "Singapore precision engineering customer.", "Yesterday", ["Account overview.pdf"]),
  substack("item-bracket", "items", "BRK-440 Bracket", "CNC-machined aluminium mounting bracket.", "2 days ago", ["BRK-440 drawing.pdf"]),
  substack("inv-2431", "invoices", "INV-2026-081", "Invoice issued for PO2431.", "3 hours ago", ["INV-2026-081.pdf"]),
  substack("sup-metal", "suppliers", "MetalWorks SG", "Aluminium stock supplier.", "4 days ago", ["Rate card.pdf"]),
  substack("spo-881", "supplier-orders", "SPO881", "Aluminium 6061 stock purchase.", "Yesterday", ["SPO881.pdf"]),
  substack("job-2431", "production-jobs", "JOB2431", "Production run for PO2431.", "28 min ago", ["Job traveller.pdf"]),
  substack("spec-bracket", "specifications", "BRK-440 Rev C", "Current approved bracket specification.", "2 days ago", ["BRK-440-REV-C.pdf"]),
  substack("conv-group-abc", "conversations", "Group ABC", "WhatsApp order updates with Acme Engineering.", "13 Sep", ["items.jpg", "PRD.docx", "Meeting_notes.docx"]),
  substack("pic-anna", "pics", "Anna Tan", "Sales coordinator responsible for Acme Engineering.", "Today", ["Contact card"]),
  substack("meet-production", "meetings", "Wednesday, Ideas Finalisation", "Production planning and order review.", "11 Sep", ["Meeting_notes.docx"]),
  substack("file-po2431", "files", "PO2431.pdf", "Original purchase order received from Acme Engineering.", "13 Sep", ["PO2431.pdf"]),
  substack("file-items", "files", "items.jpg", "Annotated product reference shared in WhatsApp.", "13 Sep", ["items.jpg"]),
  substack("file-prd", "files", "PRD.docx", "Product requirements document.", "12 Sep", ["PRD.docx"]),
  substack("file-meeting", "files", "Meeting_notes.docx", "Notes from the production review.", "11 Sep", ["Meeting_notes.docx"]),
];

export const SUBSTACK_DETAILS: Record<string, SubstackDetail> = {
  "so-2431": {
    tokens: [
      { id: "po", label: "PO number", value: "PO2431", sourceIds: ["src-po", "src-chat"] },
      { id: "client", label: "Client", value: "Acme Engineering", sourceIds: ["src-po"] },
      { id: "item", label: "Item", value: "BRK-440 Bracket", sourceIds: ["src-po", "src-chat"] },
      { id: "qty", label: "Quantity", value: "240 units", sourceIds: ["src-chat"] },
      { id: "delivery", label: "Delivery date", value: "18 Sep 2026", sourceIds: ["src-po", "src-chat"] },
      { id: "status", label: "Status", value: "Confirmed", sourceIds: ["src-chat"] },
      { id: "total", label: "Order total", value: "S$18,720.00", sourceIds: ["src-po"] },
      { id: "pic", label: "PIC", value: "Anna Tan", sourceIds: ["src-chat"] },
    ],
    sources: [
      { id: "src-po", substackId: "file-po2431", name: "PO2431.pdf", type: "Files", origin: "Google Drive", updated: "13 Sep", note: "Original customer purchase order" },
      { id: "src-chat", substackId: "conv-group-abc", name: "Group ABC", type: "Conversations", origin: "WhatsApp", updated: "13 Sep", note: "Quantity and delivery confirmation" },
    ],
    relatedIds: ["cl-acme", "item-bracket", "job-2431", "inv-2431", "pic-anna"],
  },
  "conv-group-abc": {
    conversation: [
      { id: "msg-1", date: "10 Sep 1PM", author: "Acme Engineering", message: "Should we move forward with Plan B?", summary: "Customer asks to proceed with the revised production plan.", sourceIds: ["att-items"] },
      { id: "msg-2", date: "10 Sep 1PM", author: "Anna Tan", message: "Meet us at SFF. I’ve attached the revised requirements and launch schedule.", summary: "Revised requirements shared; launch remains scheduled for 18 Sep.", sourceIds: ["att-prd", "att-meeting"] },
      { id: "msg-3", date: "10 Sep 1PM", author: "Acme Engineering", message: "Confirmed. Please move forward with Plan B.", summary: "Customer confirms Plan B.", sourceIds: ["att-prd"] },
    ],
    sources: [
      { id: "att-items", substackId: "file-items", name: "items.jpg", type: "Files", origin: "Drive", updated: "13 Sep", note: "Annotated item reference" },
      { id: "att-prd", substackId: "file-prd", name: "PRD.docx", type: "Files", origin: "Drive", updated: "12 Sep", note: "Launch date: 18 Sep" },
      { id: "att-meeting", substackId: "file-meeting", name: "Meeting_notes.docx", type: "Files", origin: "Drive", updated: "11 Sep", note: "Schedule under review" },
    ],
    relatedIds: ["meet-production", "so-2431", "inv-2431"],
  },
};

export const SCOPE_TABS: [Scope, string][] = [["all", "All Stacks"], ["mine", "My Stacks"], ["workspace", "Workspace"], ["shared", "Shared with me"]];

export function inScope(ss: Substack, sc: Scope): boolean {
  return sc === "all" || ss.scope === sc || (sc === "workspace" && ["Product & Design", "All members"].includes(ss.access));
}

const STORAGE_KEY = "crosspod.stacks.v2";
export interface StacksState { stackTypes: StackType[]; substacks: Substack[]; }

export function loadStacksState(): StacksState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StacksState;
    if (!Array.isArray(parsed.stackTypes) || !Array.isArray(parsed.substacks)) return null;
    const typeIds = new Set(parsed.stackTypes.map((t) => t.id));
    const substackIds = new Set(parsed.substacks.map((s) => s.id));
    return { stackTypes: [...parsed.stackTypes, ...STACK_TYPES.filter((t) => !typeIds.has(t.id))], substacks: [...parsed.substacks, ...INITIAL_SUBSTACKS.filter((s) => !substackIds.has(s.id))] };
  } catch { return null; }
}

export function saveStacksState(state: StacksState): void {
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch {}
}
