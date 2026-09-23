import posthog from "posthog-js";

const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
const host = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com";

if (key) {
  posthog.init(key, {
    api_host: "/ingest",
    ui_host: host.replace(".i.posthog.com", ".posthog.com"),
    defaults: "2026-05-30",
    person_profiles: "identified_only",
    // PDPA: customer order data must never leave the app through analytics.
    mask_all_text: true,
    mask_all_element_attributes: true,
    session_recording: { maskAllInputs: true, maskTextSelector: "*" },
  });
  posthog.register({ environment: process.env.NEXT_PUBLIC_VERCEL_ENV ?? "development" });
}
