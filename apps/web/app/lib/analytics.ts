import posthog from "posthog-js";
import type { Account, Me } from "./api";

// Only counts, types and internal IDs are sent — never names, file contents,
// messages or search text.
export type AnalyticsEvent =
  | "sign_in_clicked"
  | "account_created"
  | "account_switched"
  | "converted_to_company"
  | "view_changed"
  | "substack_opened"
  | "substack_created"
  | "substack_deleted"
  | "substack_confirmed"
  | "substack_update_dismissed"
  | "confirm_all"
  | "analyze_workspace_clicked"
  | "analysis_started"
  | "drive_connect_clicked"
  | "drive_connected"
  | "drive_selection_saved"
  | "drive_sync_started"
  | "drive_sync_completed"
  | "whatsapp_connect_started"
  | "whatsapp_import_started"
  | "whatsapp_upload_completed"
  | "whatsapp_uploads_wiped"
  | "evidence_panel_toggled"
  | "source_opened"
  | "related_opened"
  | "nav_back_clicked"
  | "breadcrumb_clicked"
  | "review_queue_step";

const enabled = () => Boolean(process.env.NEXT_PUBLIC_POSTHOG_KEY);

export function track(event: AnalyticsEvent, props?: Record<string, string | number | boolean | null>) {
  if (enabled()) posthog.capture(event, props);
}

export function identifyUser(me: Me, account: Account | null) {
  if (!enabled()) return;
  posthog.identify(me.id, {
    account_type: account?.account_type ?? null,
    role: account?.role ?? null,
    organization_id: account?.id ?? null,
    drive_linked: me.drive_linked,
    whatsapp_linked: me.whatsapp_linked,
  });
}

export function resetAnalytics() {
  if (enabled()) posthog.reset();
}
