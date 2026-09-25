// Canonical origin of the marketing deployment; override once a domain exists.
export const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ??
  "https://discover-crosspod.vercel.app";

export const landingOnly = process.env.NEXT_PUBLIC_LANDING_ONLY === "true";

export const site = {
  name: "crossPOd",
  tagline: "Every order, confirmed in one place",
  description:
    "crossPOd reads the WhatsApp messages and Google Drive documents your customers and team already use, turns them into confirmed records with evidence, and answers questions about them. Built for B2B suppliers and Singapore SMEs.",
  // The long `description` is for JSON-LD. Search results cut off around 160
  // characters; link previews (og:/twitter:) around 125.
  metaDescription:
    "Turn WhatsApp threads and Drive documents into confirmed order records with evidence on every field — for Singapore B2B suppliers.",
  socialDescription:
    "Turn WhatsApp threads and Drive documents into confirmed orders, with evidence on every field.",
  addressLocality: "Singapore",
  addressCountry: "SG",
  locale: "en_SG",
  language: "en-SG",
  twitter: "@crosspodhq",
  contactEmail: "hello@crosspod.sg",
  // Raster logo for structured data; the nav uses an inline SVG of the same mark.
  logoPath: "/crosspod-logo.png",
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
      "WhatsApp ingestion",
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
      "WhatsApp and Google Drive, including Shared Drives",
      "All 9 Stacks with revision tracking",
      "Ask crossPOd with citations",
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
      "Company account with an administrator and members",
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
    channel: "WhatsApp exports",
    detail: "Older threads from a phone, uploaded as a chat export.",
    example: "WhatsApp Chat with Acme Purchasing.zip",
  },
  {
    channel: "Google Docs & Sheets",
    detail: "Order schedules, price lists and specs your team keeps in Drive.",
    example: "/Customers/Acme/Oct delivery schedule",
  },
  {
    channel: "Shared Drives",
    detail: "Each Shared Drive becomes its own workspace; you pick the folders.",
    example: "Sales Shared Drive \u00b7 /Customers",
  },
] as const;

export const faqs = [
  {
    question: "Does crossPOd change how my customers send orders?",
    answer:
      "No. Customers keep messaging you on WhatsApp exactly as they do today, and your team keeps working in Google Drive. crossPOd reads those sources and proposes structured records from them.",
  },
  {
    question: "Can crossPOd enter orders into my system on its own?",
    answer:
      "crossPOd proposes; a person confirms. Every proposed field carries a link to the message or document passage it came from, so your coordinator checks it in seconds before it becomes a confirmed record.",
  },
  {
    question: "What can crossPOd read today?",
    answer:
      "WhatsApp chats, connected live or uploaded as an export, and Google Docs, Sheets, Slides and text files in My Drive or Shared Drives. PDFs, scanned forms and email are not read yet — tell us if your orders arrive that way.",
  },
  {
    question: "What happens when a customer changes an order?",
    answer:
      "Revisions are tracked against the original order, so a 'make it 500 instead' message in WhatsApp shows up as a change to confirm rather than a detail someone has to remember.",
  },
] as const;
