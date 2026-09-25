export const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ?? "https://crosspod.sg";

export const landingOnly = process.env.NEXT_PUBLIC_LANDING_ONLY === "true";

export const site = {
  name: "crossPOd",
  tagline: "Every order, confirmed in one place",
  description:
    "crossPOd reads the purchase orders, WhatsApp messages, scanned forms and Drive files your customers already send, turns them into confirmed records with evidence, and answers questions about them. Built for B2B suppliers and Singapore SMEs.",
  locale: "en_SG",
  twitter: "@crosspodhq",
  contactEmail: "hello@crosspod.sg",
} as const;

export const plans = [
  {
    id: "starter",
    name: "Starter",
    price: "S$249",
    cadence: "/month",
    monthlyPrice: 249,
    summary: "For a single admin team getting orders out of the inbox.",
    features: [
      "5 users",
      "200 documents a month",
      "WhatsApp and email ingestion",
      "Sales Orders, Clients and Items Stacks",
      "Evidence links on every confirmed field",
    ],
    cta: "Start a 14-day trial",
    featured: false,
  },
  {
    id: "growth",
    name: "Growth",
    price: "S$699",
    cadence: "/month",
    monthlyPrice: 699,
    summary: "For suppliers running production off confirmed orders.",
    features: [
      "20 users",
      "2,000 documents a month",
      "All connectors, including PDF, scans and Google Drive",
      "All 12 Stacks with revision tracking and change alerts",
      "Ask crossPOd with citations, plus API access",
    ],
    cta: "Start a 14-day trial",
    featured: true,
  },
  {
    id: "enterprise",
    name: "Enterprise",
    price: "Let's talk",
    cadence: "",
    monthlyPrice: null,
    summary: "For multi-site operations with their own compliance rules.",
    features: [
      "Unlimited users and documents",
      "Single sign-on and role-based access control",
      "Custom Stacks and ERP integrations",
      "Data residency, retention policies and audit exports",
      "Named onboarding lead",
    ],
    cta: "Talk to us",
    featured: false,
  },
] as const;

/** Annual plans are billed up front at ten months of the monthly price. */
export const annualMonthsCharged = 10;

export const sources = [
  {
    channel: "WhatsApp",
    detail: "Order changes, approvals and commitments buried in a thread.",
    example: "\u201cMake PO 88213 500pcs instead of 300, same date ok?\u201d",
  },
  {
    channel: "PO PDFs",
    detail: "Line items, part codes, quantities and delivery dates.",
    example: "PO-88213.pdf \u00b7 4 lines \u00b7 delivery 14 Oct",
  },
  {
    channel: "Scanned forms",
    detail: "Faxed and photographed orders that never reach your ERP.",
    example: "scan_0142.jpg \u00b7 handwritten quantity on line 2",
  },
  {
    channel: "Email attachments",
    detail: "Revisions sent as replies to a thread nobody else can see.",
    example: "Re: Oct schedule \u00b7 revised_spec_revB.xlsx",
  },
  {
    channel: "Google Drive",
    detail: "Shared folders of drawings, specs and price lists.",
    example: "/Customers/Acme/Drawings/ACM-220-revC.pdf",
  },
] as const;

export const faqs = [
  {
    question: "Does crossPOd change how my customers send orders?",
    answer:
      "No. Customers keep sending POs, WhatsApp messages, scanned forms and email attachments exactly as they do today. crossPOd reads those sources and proposes structured records from them.",
  },
  {
    question: "Can crossPOd enter orders into my system on its own?",
    answer:
      "crossPOd proposes; a person confirms. Every proposed field carries a link to the message or document line it came from, so your coordinator checks it in seconds before it becomes a confirmed record.",
  },
  {
    question: "How does crossPOd handle PDPA?",
    answer:
      "Consent, retention windows, access control and a full audit history are part of ingestion rather than an afterthought. You can see who confirmed what, when, and from which source.",
  },
  {
    question: "What happens when a customer changes an order?",
    answer:
      "Revisions are tracked against the original order, so a 'make it 500 instead' message in WhatsApp shows up as a change to confirm rather than a detail someone has to remember.",
  },
] as const;
