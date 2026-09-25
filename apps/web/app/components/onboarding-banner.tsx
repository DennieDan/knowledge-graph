"use client";

import Link from "next/link";
import type { MouseEvent } from "react";
import Icon from "./icons";
import styles from "./onboarding-banner.module.css";

export type OnboardingStep = "connect" | "sync" | "analyze";

const STEPS: OnboardingStep[] = ["connect", "sync", "analyze"];

const COPY: Record<OnboardingStep, { title: string; here: string; away: string; cta: string }> = {
  connect: {
    title: "Connect a source to get started",
    here: "Connect Google Drive or WhatsApp below so crosspod can read your orders and conversations.",
    away: "Connect Google Drive or WhatsApp so crosspod can read your orders and conversations.",
    cta: "Go to Sources",
  },
  sync: {
    title: "Sync your Google Drive",
    here: "Click Sync now on the Google Drive card to pull in your files.",
    away: "Open Sources and click Sync now to pull in your Drive files.",
    cta: "Go to Sources",
  },
  analyze: {
    title: "Analyze your workspace",
    here: "Click Analyze workspace to turn your sources into Stacks you can check.",
    away: "Go to Analyze workspace and click Analyze workspace to turn your sources into Stacks.",
    cta: "Go to Analyze workspace",
  },
};

export default function OnboardingBanner({
  step,
  href,
  onPage,
  onNavigate,
  onDismiss,
}: {
  step: OnboardingStep;
  href: string;
  onPage: boolean;
  onNavigate: (event: MouseEvent) => void;
  onDismiss: () => void;
}) {
  const copy = COPY[step];
  return (
    <section className={styles.banner} aria-label="Getting started">
      <span className={styles.step}>Step {STEPS.indexOf(step) + 1} of {STEPS.length}</span>
      <div className={styles.text}>
        <p className={styles.title}>{copy.title}</p>
        <p className={styles.body}>{onPage ? copy.here : copy.away}</p>
      </div>
      {!onPage && (
        <Link href={href} scroll={false} onClick={onNavigate} className={styles.cta}>
          {copy.cta} <Icon name="chevron-right" size={13} />
        </Link>
      )}
      <button type="button" className={styles.dismiss} onClick={onDismiss} aria-label="Dismiss getting started">
        <Icon name="x" size={14} />
      </button>
    </section>
  );
}
