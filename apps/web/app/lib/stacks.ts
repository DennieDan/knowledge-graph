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

export const STACK_TYPES: StackType[] = [
  { id: "clients", name: "Clients", icon: "building-2", desc: "Client accounts, relationships, and key contacts." },
  { id: "events", name: "Events", icon: "calendar", desc: "Events, schedules, and coordination details." },
  { id: "meetings", name: "Meetings", icon: "users", desc: "Meeting notes, agendas, and action items." },
  { id: "vendors", name: "Vendors", icon: "package", desc: "Vendor contracts, contacts, and orders." },
  { id: "contacts", name: "Contacts", icon: "user", desc: "Individual contact records and history." },
  { id: "proposals", name: "Proposals", icon: "file-text", desc: "Active and archived proposals and quotes." },
  { id: "finance", name: "Finance Documents", icon: "receipt", desc: "Invoices, budgets, and financial records." },
  { id: "conversations", name: "Conversations", icon: "message-circle", desc: "Ongoing threads and communication history." },
  { id: "crew", name: "Crew", icon: "users", desc: "Team members, roles, and assignments." },
  { id: "licenses", name: "Licenses", icon: "shield", desc: "Software, creative, and legal licenses." },
  { id: "venues", name: "Venues", icon: "map-pin", desc: "Event venues — contracts, rates, and availability." },
];

export const INITIAL_SUBSTACKS: Substack[] = [
  // Clients
  { id: "c1", typeId: "clients", name: "Acme Corp", desc: "End-to-end client relationship history and deliverables.", scope: "workspace", access: "Product & Design", role: "Can view", updated: "1 hour ago", docs: ["Client overview", "Kickoff notes"], count: 24 },
  { id: "c2", typeId: "clients", name: "Meridian Studios", desc: "Ongoing partnership with contracts and project briefs.", scope: "shared", access: "Shared by Maya", role: "Can edit", updated: "3 hours ago", docs: ["Contract v2", "Project brief"], count: 11 },
  { id: "c3", typeId: "clients", name: "Northfield Retail", desc: "Seasonal campaigns and account manager notes.", scope: "mine", access: "Only you", role: "Owner", updated: "Yesterday", docs: ["Campaign brief", "Account notes"], count: 8 },
  // Events
  { id: "e1", typeId: "events", name: "Product Launch Q4", desc: "All coordination, speakers, and run-of-show for the launch.", scope: "workspace", access: "All members", role: "Can view", updated: "2 min ago", docs: ["Run of show", "Speaker list"], count: 18 },
  { id: "e2", typeId: "events", name: "Annual Offsite 2026", desc: "Planning docs, logistics, and attendee list.", scope: "mine", access: "Only you", role: "Owner", updated: "2 hours ago", docs: ["Logistics", "Agenda draft"], count: 7 },
  { id: "e3", typeId: "events", name: "Design Summit", desc: "Workshop sessions, facilitators, and outcomes.", scope: "shared", access: "Shared by Alex", role: "Can view", updated: "Yesterday", docs: ["Session plan", "Outcomes"], count: 5 },
  // Meetings
  { id: "m1", typeId: "meetings", name: "Product Weekly", desc: "Weekly discussions, action items, and decisions.", scope: "shared", access: "Shared by Maya", role: "Can edit", updated: "18 min ago", docs: ["Weekly notes · Sep 17", "Sprint priorities"], count: 8 },
  { id: "m2", typeId: "meetings", name: "Leadership Sync", desc: "Bi-weekly leadership sync notes and follow-ups.", scope: "workspace", access: "All members", role: "Can view", updated: "4 hours ago", docs: ["Sync notes", "Decision log"], count: 15 },
  { id: "m3", typeId: "meetings", name: "Client Check-ins", desc: "Regular client touchpoints and status updates.", scope: "mine", access: "Only you", role: "Owner", updated: "Yesterday", docs: ["Check-in template", "Open items"], count: 6 },
  // Vendors
  { id: "v1", typeId: "vendors", name: "Printbase Co.", desc: "Print vendor POs, proofs, and delivery tracking.", scope: "mine", access: "Only you", role: "Owner", updated: "2 hours ago", docs: ["PO #1042", "Proof approvals"], count: 10 },
  { id: "v2", typeId: "vendors", name: "Studio Freight", desc: "Logistics partner with rate cards and contacts.", scope: "shared", access: "Shared by Dan", role: "Can edit", updated: "Yesterday", docs: ["Rate card", "Contact list"], count: 4 },
  // Contacts
  { id: "co1", typeId: "contacts", name: "Maya Osei", desc: "Head of Design — primary creative contact.", scope: "shared", access: "Shared by team", role: "Can view", updated: "30 min ago", docs: ["Bio", "Project history"], count: 3 },
  { id: "co2", typeId: "contacts", name: "Jordan Lee", desc: "Engineering lead — integration and delivery point.", scope: "workspace", access: "Product & Design", role: "Can view", updated: "Yesterday", docs: ["Contact notes"], count: 2 },
  // Proposals
  { id: "p1", typeId: "proposals", name: "Rebrand Proposal 2026", desc: "Full scope, timeline, and pricing for rebrand engagement.", scope: "mine", access: "Only you", role: "Owner", updated: "1 hour ago", docs: ["Scope doc", "Pricing sheet"], count: 6 },
  { id: "p2", typeId: "proposals", name: "Event Production Bid", desc: "Vendor bid for Q4 event, including AV and logistics.", scope: "shared", access: "Shared by Alex", role: "Can view", updated: "2 days ago", docs: ["Bid deck", "Line items"], count: 9 },
  // Finance
  { id: "f1", typeId: "finance", name: "Q3 Invoices", desc: "All outgoing invoices for Q3, with payment status.", scope: "mine", access: "Only you", role: "Owner", updated: "3 hours ago", docs: ["Invoice #101", "Invoice #102"], count: 14 },
  { id: "f2", typeId: "finance", name: "Annual Budget 2026", desc: "Departmental budgets and variance tracking.", scope: "workspace", access: "All members", role: "Can view", updated: "Yesterday", docs: ["Budget overview", "Variance sheet"], count: 5 },
  // Conversations
  { id: "cv1", typeId: "conversations", name: "Customer Insights", desc: "Themes from recent customer conversations.", scope: "shared", access: "Shared by Alex", role: "Can view", updated: "3 hours ago", docs: ["Interview synthesis", "Research highlights"], count: 19 },
  { id: "cv2", typeId: "conversations", name: "Sales Thread — Meridian", desc: "Email thread history and negotiation notes.", scope: "mine", access: "Only you", role: "Owner", updated: "Yesterday", docs: ["Email archive", "Negotiation notes"], count: 7 },
  // Crew
  { id: "cr1", typeId: "crew", name: "Production Team", desc: "Crew roster, roles, and on-site contacts.", scope: "workspace", access: "All members", role: "Can view", updated: "2 days ago", docs: ["Roster", "Contact sheet"], count: 12 },
  { id: "cr2", typeId: "crew", name: "Freelance Pool", desc: "Vetted freelancers, rates, and availability.", scope: "mine", access: "Only you", role: "Owner", updated: "4 days ago", docs: ["Freelancer list", "Rate reference"], count: 8 },
  // Licenses
  { id: "l1", typeId: "licenses", name: "Software Licenses", desc: "Active software subscriptions and renewal dates.", scope: "workspace", access: "All members", role: "Can view", updated: "1 week ago", docs: ["License inventory", "Renewal calendar"], count: 22 },
  { id: "l2", typeId: "licenses", name: "Stock Media Rights", desc: "Image and video licenses with usage rights.", scope: "shared", access: "Product & Design", role: "Can edit", updated: "3 days ago", docs: ["Rights ledger", "Expiry tracker"], count: 9 },
  // Venues
  { id: "vn1", typeId: "venues", name: "Marina Bay Expo Hall", desc: "Large convention space with preferred rates and contacts.", scope: "workspace", access: "All members", role: "Can view", updated: "5 hours ago", docs: ["Rate card", "Floor plan"], count: 15 },
  { id: "vn2", typeId: "venues", name: "Raffles Ballroom", desc: "Hotel ballroom for D&D and gala events; AV restrictions noted.", scope: "shared", access: "Shared by Maya", role: "Can edit", updated: "Yesterday", docs: ["Contract", "AV notes"], count: 6 },
];

export const SCOPE_TABS: [Scope, string][] = [
  ["all", "All Stacks"],
  ["mine", "My Stacks"],
  ["workspace", "Workspace"],
  ["shared", "Shared with me"],
];

export function inScope(ss: Substack, sc: Scope): boolean {
  return (
    sc === "all" ||
    ss.scope === sc ||
    (sc === "workspace" && ["Product & Design", "All members"].includes(ss.access))
  );
}

const STORAGE_KEY = "crosspod.stacks.v1";

export interface StacksState {
  stackTypes: StackType[];
  substacks: Substack[];
}

export function loadStacksState(): StacksState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StacksState;
    if (!Array.isArray(parsed.stackTypes) || !Array.isArray(parsed.substacks)) {
      return null;
    }
    // Merge in any default entries added since the state was persisted.
    const typeIds = new Set(parsed.stackTypes.map((t) => t.id));
    const substackIds = new Set(parsed.substacks.map((s) => s.id));
    return {
      stackTypes: [
        ...parsed.stackTypes,
        ...STACK_TYPES.filter((t) => !typeIds.has(t.id)),
      ],
      substacks: [
        ...parsed.substacks,
        ...INITIAL_SUBSTACKS.filter((s) => !substackIds.has(s.id)),
      ],
    };
  } catch {
    return null;
  }
}

export function saveStacksState(state: StacksState): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Storage unavailable (private mode, quota) — keep state in memory only.
  }
}
