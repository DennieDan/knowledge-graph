"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { site } from "@/lib/site";

const fields = [
  { name: "name", label: "Your name", type: "text", autoComplete: "name" },
  {
    name: "company",
    label: "Company",
    type: "text",
    autoComplete: "organization",
  },
  { name: "email", label: "Work email", type: "email", autoComplete: "email" },
] as const;

export default function DemoDialog({
  label,
  className,
}: {
  label: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = [
      `Name: ${data.get("name")}`,
      `Company: ${data.get("company")}`,
      `Email: ${data.get("email")}`,
      "",
      `What we send today: ${data.get("sources") || "-"}`,
    ].join("\n");
    window.location.href = `mailto:${site.contactEmail}?subject=${encodeURIComponent(
      `${site.name} walkthrough`,
    )}&body=${encodeURIComponent(body)}`;
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger className={className}>{label}</DialogTrigger>
      {/* The dialog portals to <body>, outside the landing layout wrapper, so
          it carries the theme class itself. */}
      <DialogContent className="landingTheme bg-background sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle>Book a 20-minute walkthrough</DialogTitle>
          <DialogDescription>
            Bring one week of messy orders. We run them through {site.name} and
            show you what your team would confirm.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4">
          {fields.map((field) => (
            <label key={field.name} className="grid gap-1.5 text-sm font-medium">
              {field.label}
              <input
                required
                name={field.name}
                type={field.type}
                autoComplete={field.autoComplete}
                className="h-10 rounded-md border border-input bg-background px-3 text-[15px] font-normal outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
          ))}
          <label className="grid gap-1.5 text-sm font-medium">
            How do orders reach you today?
            <textarea
              name="sources"
              rows={3}
              placeholder="WhatsApp, PO PDFs, scanned forms…"
              className="rounded-md border border-input bg-background p-3 text-[15px] font-normal outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          <DialogFooter>
            <Button
              type="submit"
              className="bg-primary text-primary-foreground hover:bg-accent"
            >
              Send request
            </Button>
          </DialogFooter>
        </form>
        <p className="text-xs text-muted-foreground">
          This opens your email client with the details filled in — nothing is
          sent to us until you press send.
        </p>
      </DialogContent>
    </Dialog>
  );
}
