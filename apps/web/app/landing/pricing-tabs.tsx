"use client";

import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { annualMonthsCharged, plans } from "@/lib/site";
import styles from "./page.module.css";

const billing = [
  { id: "monthly", label: "Monthly" },
  { id: "annual", label: `Annual · ${12 - annualMonthsCharged} months free` },
] as const;

function priceFor(
  plan: (typeof plans)[number],
  period: (typeof billing)[number]["id"],
) {
  if (plan.monthlyPrice === null) {
    return { price: plan.price, cadence: plan.cadence, note: null };
  }
  if (period === "monthly") {
    return { price: plan.price, cadence: plan.cadence, note: "Billed monthly" };
  }
  const yearly = plan.monthlyPrice * annualMonthsCharged;
  return {
    price: `S$${Math.round(yearly / 12)}`,
    cadence: "/month",
    note: `S$${yearly.toLocaleString("en-SG")} billed yearly · monthly figure rounded`,
  };
}

function PlanGrid({ period }: { period: (typeof billing)[number]["id"] }) {
  return (
    <ul className={styles.planGrid}>
      {plans.map((plan) => {
        const { price, cadence, note } = priceFor(plan, period);
        return (
          <li
            key={plan.id}
            className={
              plan.featured
                ? `${styles.planCard} ${styles.planCardFeatured}`
                : styles.planCard
            }
          >
            {plan.featured ? (
              <Badge className="absolute -top-3 left-6 bg-accent text-accent-foreground">
                Most popular
              </Badge>
            ) : null}
            <h3>{plan.name}</h3>
            <p className={styles.planPrice}>
              {price}
              <span>{cadence}</span>
            </p>
            <p className="min-h-[20px] text-[13px] text-muted-foreground">
              {note}
            </p>
            <p className={styles.planSummary}>{plan.summary}</p>
            <ul className={styles.planFeatures}>
              {plan.features.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
            <a
              className={plan.featured ? styles.primaryCta : styles.secondaryCta}
              href="#demo"
            >
              {plan.cta}
            </a>
          </li>
        );
      })}
    </ul>
  );
}

export default function PricingTabs() {
  return (
    <Tabs defaultValue="monthly" className="items-center gap-8">
      <TabsList className="rounded-full bg-secondary p-1">
        {billing.map((option) => (
          <TabsTrigger
            key={option.id}
            value={option.id}
            className="rounded-full px-5 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            {option.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {billing.map((option) => (
        <TabsContent key={option.id} value={option.id} className="w-full">
          <PlanGrid period={option.id} />
        </TabsContent>
      ))}
    </Tabs>
  );
}
