"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { faqs } from "@/lib/site";
import styles from "./page.module.css";

export default function FaqAccordion() {
  return (
    <Accordion
      type="single"
      collapsible
      defaultValue={faqs[0].question}
      className={styles.faqAccordion}
    >
      {faqs.map((faq) => (
        <AccordionItem key={faq.question} value={faq.question}>
          <AccordionTrigger className="text-left text-[17px] font-semibold text-foreground">
            {faq.question}
          </AccordionTrigger>
          <AccordionContent className="text-[16px] leading-relaxed text-muted-foreground">
            {faq.answer}
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
}
