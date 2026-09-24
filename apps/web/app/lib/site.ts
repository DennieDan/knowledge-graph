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
