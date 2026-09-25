import type { Metadata } from "next";
import { faqs, plans, site, siteUrl } from "../lib/site";
import DemoDialog from "./demo-dialog";
import FaqAccordion from "./faq-accordion";
import PricingTabs from "./pricing-tabs";
import SourcesCarousel from "./sources-carousel";
import styles from "./page.module.css";

const pageUrl = `${siteUrl}/landing`;

const title = `${site.name} — ${site.tagline}`;

export const metadata: Metadata = {
  title,
  description: site.description,
  keywords: [
    "order management software Singapore",
    "purchase order automation",
    "WhatsApp order processing",
    "B2B supplier software",
    "SME order entry",
    "PO data extraction",
  ],
  applicationName: site.name,
  alternates: { canonical: pageUrl },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large" },
  },
  openGraph: {
    type: "website",
    url: pageUrl,
    siteName: site.name,
    locale: site.locale,
    title,
    description: site.description,
  },
  twitter: {
    card: "summary_large_image",
    site: site.twitter,
    title,
    description: site.description,
  },
};

const steps = [
  {
    step: "Read",
    body: "crossPOd watches the channels your customers already use and pulls out orders, quantities, dates and revisions — including the ones buried in a WhatsApp voice note or a scanned fax.",
  },
  {
    step: "Confirm",
    body: "Each proposal arrives with the evidence beside it. Your coordinator checks the line, corrects anything off, and confirms it into a record the rest of the business can trust.",
  },
  {
    step: "Ask",
    body: "Ask what is due this week or which revision is current. Answers come from confirmed records first, with the original source one click away.",
  },
] as const;

const features = [
  {
    title: "Every format your customers actually send",
    body: "PO PDFs, WhatsApp threads, scanned forms, email attachments and Google Drive files land in one queue instead of five inboxes.",
  },
  {
    title: "Evidence on every field",
    body: "A quantity is never just a number. crossPOd keeps the line, page or message it came from attached to the record forever.",
  },
  {
    title: "12 Stacks, ready on day one",
    body: "Sales Orders, Clients, Items, Invoices, Suppliers, Supplier Orders, Production Jobs, Specifications, Conversations, PICs, Meetings and Files.",
  },
  {
    title: "Revisions that stop surprising you",
    body: "A late change lands as a revision to confirm against the original order, linked to the message that asked for it.",
  },
  {
    title: "Knowledge that outlasts staff turnover",
    body: "The terms, part codes and quirks your senior admin keeps in her head become records anyone on the team can look up.",
  },
  {
    title: "PDPA compliance built into ingestion",
    body: "Consent, retention, access control and audit history are part of how sources are read, not a policy document nobody reads.",
  },
] as const;

const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "SoftwareApplication",
      name: site.name,
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      url: pageUrl,
      description: site.description,
      offers: plans
        .filter((plan) => plan.price.startsWith("S$"))
        .map((plan) => ({
          "@type": "Offer",
          name: plan.name,
          price: plan.price.replace("S$", ""),
          priceCurrency: "SGD",
          url: `${pageUrl}#pricing`,
        })),
    },
    {
      "@type": "FAQPage",
      mainEntity: faqs.map((faq) => ({
        "@type": "Question",
        name: faq.question,
        acceptedAnswer: { "@type": "Answer", text: faq.answer },
      })),
    },
  ],
};

export default function LandingPage() {
  return (
    <div className={styles.page}>
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger -- structured data must be inlined for crawlers
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <header className={styles.nav}>
        <a className={styles.brand} href="#hero">
          {site.name}
          <span className={styles.brandDot} />
        </a>
        <nav aria-label="Sections">
          <ul className={styles.navLinks}>
            <li>
              <a href="#how">How it works</a>
            </li>
            <li>
              <a href="#sources">Sources</a>
            </li>
            <li>
              <a href="#features">Features</a>
            </li>
            <li>
              <a href="#pricing">Pricing</a>
            </li>
          </ul>
        </nav>
        <DemoDialog className={styles.navCta} label="Book a walkthrough" />
      </header>

      <main>
        <section className={styles.hero} id="hero">
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>
              For B2B suppliers and Singapore SMEs
            </p>
            <h1 className={styles.heroTitle}>
              Every order, <em>confirmed</em> in one place.
            </h1>
            <p className={styles.heroBody}>
              POs, WhatsApp, email, scans — crossPOd turns all of it into one
              confirmed order your whole team can trust.
            </p>
            <div className={styles.heroActions}>
              <DemoDialog
                className={styles.primaryCta}
                label="Book a 20-minute walkthrough"
              />
              <a className={styles.secondaryCta} href="#how">
                See how it works
              </a>
            </div>
            <ul className={styles.heroProof}>
              <li>No change for your customers</li>
              <li>PDPA-ready ingestion</li>
              <li>Live in under two weeks</li>
            </ul>
          </div>

          <div className={styles.heroVisual} aria-hidden="true">
            <div className={`${styles.card} ${styles.cardSource}`}>
              <span className={styles.cardTag}>WhatsApp · 4:12 PM</span>
              <p>
                &ldquo;Hi, for PO 88213 please make it 500pcs instead of 300,
                same delivery date ok?&rdquo;
              </p>
            </div>
            <div className={`${styles.card} ${styles.cardProposal}`}>
              <span className={styles.cardTag}>Proposed revision</span>
              <strong>SO-88213 · Rev B</strong>
              <dl className={styles.cardFields}>
                <div>
                  <dt>Qty</dt>
                  <dd>
                    <s>300</s> 500
                  </dd>
                </div>
                <div>
                  <dt>Delivery</dt>
                  <dd>Unchanged</dd>
                </div>
              </dl>
              <span className={styles.cardEvidence}>
                Evidence: WhatsApp message · 4:12 PM
              </span>
            </div>
            <div className={`${styles.card} ${styles.cardConfirmed}`}>
              <span className={styles.cardTagOk}>Confirmed by Serene</span>
              <strong>Production Job PJ-1042 updated</strong>
              <p>Material shortfall flagged to Suppliers Stack</p>
            </div>
            <div className={`${styles.card} ${styles.cardAsk}`}>
              <span className={styles.cardTag}>Ask crossPOd</span>
              <p>Which orders changed since Monday?</p>
              <strong>3 revisions · all confirmed</strong>
            </div>
          </div>
        </section>

        <section className={styles.how} id="how">
          <div className={styles.sectionHead}>
            <p className={styles.sectionLabel}>01 / How it works</p>
            <h2>Read, confirm, ask.</h2>
            <p className={styles.sectionBody}>
              crossPOd never quietly becomes the record of truth. Sources produce
              proposals, people confirm them, and everything downstream reads
              the confirmed version.
            </p>
          </div>
          <ol className={styles.steps}>
            {steps.map((item, index) => (
              <li key={item.step}>
                <span className={styles.stepNumber}>{index + 1}</span>
                <h3>{item.step}</h3>
                <p>{item.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className={styles.sources} id="sources">
          <div className={styles.sectionHead}>
            <p className={styles.sectionLabel}>02 / Sources</p>
            <h2>Whatever your customers send, it lands in one queue.</h2>
          </div>
          <SourcesCarousel />
        </section>

        <section className={styles.features} id="features">
          <div className={styles.sectionHead}>
            <p className={styles.sectionLabel}>03 / Features</p>
            <h2>Built for the way order desks really run.</h2>
            <p className={styles.sectionBody}>
              Duplicate entry, missed changes, outdated revisions and evidence
              scattered across four apps — each one has somewhere to go now.
            </p>
          </div>
          <ul className={styles.featureGrid}>
            {features.map((feature) => (
              <li key={feature.title} className={styles.featureCard}>
                <h3>{feature.title}</h3>
                <p>{feature.body}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.pricing} id="pricing">
          <div className={styles.sectionHead}>
            <p className={styles.sectionLabel}>04 / Pricing</p>
            <h2>Priced per team, not per order.</h2>
            <p className={styles.sectionBody}>
              Priced in SGD. Every plan includes onboarding of your existing
              order formats, and you can leave with your data whenever you like.
            </p>
          </div>
          <PricingTabs />
        </section>

        <section className={styles.faq} aria-labelledby="faq-heading">
          <h2 id="faq-heading">Questions we get asked first</h2>
          <FaqAccordion />
        </section>

        <section className={styles.demo} id="demo">
          <p className={styles.sectionLabel}>05 / Get started</p>
          <h2>Bring one week of messy orders. We&apos;ll run them through.</h2>
          <p className={styles.sectionBody}>
            A 20-minute walkthrough on your own POs and WhatsApp threads — you
            will see exactly what crossPOd proposes and what your team would
            confirm.
          </p>
          <DemoDialog className={styles.primaryCta} label="Book a walkthrough" />
          <p className={styles.demoNote}>
            Prefer email? Write to{" "}
            <a href={`mailto:${site.contactEmail}`}>{site.contactEmail}</a>.
          </p>
        </section>
      </main>

      <footer className={styles.footer}>
        <p>
          {site.name} — {site.tagline}.
        </p>
        <p>Singapore</p>
      </footer>
    </div>
  );
}
