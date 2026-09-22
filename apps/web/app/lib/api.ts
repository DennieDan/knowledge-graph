export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const loginUrl = `${API_URL}/auth/google/login`;
export const loginWithInviteUrl = (token: string) => `${loginUrl}?invite=${encodeURIComponent(token)}`;
export const driveConnectUrl = (accountId: string) => `${API_URL}/drive/connect?organization_id=${encodeURIComponent(accountId)}`;

export interface Account {
  id: string;
  name: string;
  account_type: "personal" | "company";
  google_domain: string | null;
  role: "admin" | "member";
  drive_linked: boolean;
}

export interface Me {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  hosted_domain: string | null;
  accounts: Account[];
  active_account_id: string | null;
  needs_account: boolean;
  drive_linked: boolean;
  whatsapp_linked: boolean;
}

export interface DriveFile {
  id: string;
  name: string;
  mimeType: string;
  modifiedTime?: string;
  webViewLink?: string;
  parents?: string[];
}

export interface DriveFileList {
  files: DriveFile[];
  nextPageToken?: string;
}

export interface DriveTreeItem extends DriveFile {
  driveId?: string;
}

export interface DriveSelection {
  configured: boolean;
  share_all: boolean;
  file_ids: string[];
}

export interface DriveWorkspace {
  id: string;
  name: string;
  kind: "my_drive" | "shared_drive";
  private: boolean;
  updated_at: string;
}

export interface DrivePermission {
  id: string;
  type: "user" | "group" | "domain" | "anyone";
  role: string;
  displayName?: string;
  emailAddress?: string;
  domain?: string;
  allowFileDiscovery?: boolean;
  expirationTime?: string;
  permissionDetails?: { inherited: boolean; inheritedFrom?: string; role: string }[];
}

export interface DrivePermissionDetails {
  file: { id: string; name: string; shared: boolean; inherited_permissions_disabled: boolean };
  capabilities: Record<string, boolean>;
  permissions: DrivePermission[];
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `${init?.method ?? "GET"} ${path} failed: ${res.status}`);
  }
  return res.json();
}

export async function getMe(): Promise<Me | null> {
  const res = await fetch(`${API_URL}/auth/me`, { credentials: "include" });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(`GET /auth/me failed: ${res.status}`);
  return res.json();
}

export function createAccount(accountType: "personal" | "company", name?: string): Promise<Account> {
  return apiFetch("/accounts", { method: "POST", body: JSON.stringify({ account_type: accountType, name }) });
}

export function activateAccount(accountId: string): Promise<{ active_account_id: string }> {
  return apiFetch(`/accounts/${accountId}/activate`, { method: "POST" });
}

export function convertToCompany(accountId: string): Promise<Account> {
  return apiFetch(`/accounts/${accountId}/convert-to-company`, { method: "POST" });
}

export function acceptInvitation(token: string): Promise<Account> {
  return apiFetch(`/invitations/${encodeURIComponent(token)}/accept`, { method: "POST" });
}

export interface AccountInvitation {
  id: string;
  email: string;
  status: string;
  expires_at: string;
  invite_url?: string;
}

export function listInvitations(accountId: string): Promise<AccountInvitation[]> {
  return apiFetch(`/accounts/${accountId}/invitations`);
}

export function createInvitation(accountId: string, email: string): Promise<AccountInvitation> {
  return apiFetch(`/accounts/${accountId}/invitations`, { method: "POST", body: JSON.stringify({ email }) });
}

export function revokeInvitation(accountId: string, invitationId: string): Promise<{ status: string }> {
  return apiFetch(`/accounts/${accountId}/invitations/${invitationId}`, { method: "DELETE" });
}

export function listDriveWorkspaces(accountId: string): Promise<DriveWorkspace[]> {
  return apiFetch(`/accounts/${accountId}/drive/workspaces`);
}

export function refreshDriveWorkspaces(accountId: string): Promise<DriveWorkspace[]> {
  return apiFetch(`/accounts/${accountId}/drive/workspaces/refresh`, { method: "POST" });
}

export function listDriveFiles(workspaceId: string): Promise<DriveFileList> {
  return apiFetch(`/drive/workspaces/${workspaceId}/files`);
}

export function driveTree(workspaceId: string): Promise<{ files: DriveTreeItem[] }> {
  return apiFetch(`/drive/workspaces/${workspaceId}/tree`);
}

export function getDriveSelection(workspaceId: string): Promise<DriveSelection> {
  return apiFetch(`/drive/workspaces/${workspaceId}/selection`);
}

export function putDriveSelection(workspaceId: string, shareAll: boolean, fileIds: string[]): Promise<DriveSelection> {
  return apiFetch(`/drive/workspaces/${workspaceId}/selection`, {
    method: "PUT",
    body: JSON.stringify({ share_all: shareAll, file_ids: fileIds }),
  });
}

export function getDrivePermissions(workspaceId: string, fileId: string): Promise<DrivePermissionDetails> {
  return apiFetch(`/drive/workspaces/${workspaceId}/files/${encodeURIComponent(fileId)}/permissions`);
}

export async function logout(): Promise<void> {
  await fetch(`${API_URL}/auth/logout`, { method: "POST", credentials: "include" });
}

export interface WhatsappConnectionStatus { status: string; phone_number: string | null }
export interface WhatsappQr { mimetype: string; data: string }
export interface WhatsappChatItem {
  chat_jid: string; name: string | null; chat_type: string; last_message_at: string | null;
  import_status: "none" | "importing" | "imported" | "failed"; message_count: number;
}
export interface WhatsappImportItem {
  chat_jid: string; name: string | null; import_status: "none" | "importing" | "imported" | "failed";
  import_error: string | null; message_count: number;
}

export function whatsappConnect(): Promise<WhatsappConnectionStatus> { return apiFetch("/whatsapp/connect", { method: "POST" }) }
export function whatsappStatus(): Promise<WhatsappConnectionStatus> { return apiFetch("/whatsapp/connect/status") }
export function whatsappQr(): Promise<WhatsappQr> { return apiFetch("/whatsapp/connect/qr") }
export function whatsappPairing(phoneNumber: string): Promise<{ code: string }> {
  return apiFetch("/whatsapp/connect/pairing", { method: "POST", body: JSON.stringify({ phone_number: phoneNumber }) });
}
export function whatsappDisconnect(): Promise<{ status: string }> { return apiFetch("/whatsapp/connect", { method: "DELETE" }) }
export function whatsappChats(): Promise<WhatsappChatItem[]> { return apiFetch("/whatsapp/chats") }
export function whatsappImport(chatIds: string[], organizationId?: string): Promise<{ queued: string[] }> {
  return apiFetch("/whatsapp/imports", {
    method: "POST",
    body: JSON.stringify({ chat_ids: chatIds, organization_id: organizationId }),
  });
}
export function whatsappImports(): Promise<WhatsappImportItem[]> { return apiFetch("/whatsapp/imports") }

// ── Stacks ──────────────────────────────────────────────────────────────

export interface StackCount { type: string; count: number }

export interface ApiSubstack {
  id: string;
  type_id: string;
  name: string;
  desc: string | null;
  scope: "mine" | "workspace";
  status: string;
  review_state: "clean" | "pending" | "pending_update" | "unsupported" | "generation_error";
  updated_at: string | null;
  count: number;
  docs: string[];
}

export interface ApiSegment {
  kind: "text" | "token" | "field";
  value: string;
  name?: string | null;
  ref?: string | null;
  citations: string[];
  locator?: Record<string, unknown> | null;
  source_ids?: string[];
}

export interface ApiConversationEntry {
  date: string;
  author: string;
  message: string;
  citations: string[];
  locator?: Record<string, unknown> | null;
  source_ids?: string[];
}

export interface ApiSubstackSource {
  id: string;
  document_id: string;
  substack_id: string | null;
  name: string;
  type: string;
  origin: string;
  updated: string | null;
  role: string;
}

export interface ApiSubstackContent {
  id?: string;
  revision?: number;
  status?: string;
  segments: ApiSegment[];
  entries: ApiConversationEntry[];
}

export interface ApiSubstackDetail extends ApiSubstack {
  content: ApiSubstackContent;
  content_status: string | null;
  pending_content: ApiSubstackContent | null;
  sources: ApiSubstackSource[];
  related: { id: string; type_id: string; name: string }[];
}

export function getStacks(accountId: string): Promise<StackCount[]> {
  return apiFetch(`/accounts/${accountId}/stacks`);
}

export function getSubstacks(accountId: string, filter?: { type?: string; q?: string }): Promise<ApiSubstack[]> {
  const params = new URLSearchParams();
  if (filter?.type) params.set("type", filter.type);
  if (filter?.q) params.set("q", filter.q);
  const suffix = params.size ? `?${params}` : "";
  return apiFetch(`/accounts/${accountId}/substacks${suffix}`);
}

export function getSubstackDetail(id: string): Promise<ApiSubstackDetail> {
  return apiFetch(`/substacks/${id}`);
}

export function createSubstack(accountId: string, input: { stack_type: string; name: string; summary?: string }): Promise<ApiSubstack> {
  return apiFetch(`/accounts/${accountId}/substacks`, { method: "POST", body: JSON.stringify(input) });
}

export function updateSubstack(id: string, patch: { name?: string; summary?: string }): Promise<ApiSubstack> {
  return apiFetch(`/substacks/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export function confirmSubstack(id: string): Promise<ApiSubstack> {
  return apiFetch(`/substacks/${id}/confirm`, { method: "POST" });
}

export function confirmSubstackContent(id: string, contentId: string): Promise<ApiSubstack> {
  return apiFetch(`/substacks/${id}/contents/${contentId}/confirm`, { method: "POST" });
}

export interface AnalysisRun {
  id: string;
  scope: "mine" | "workspace";
  trigger: string;
  status: "queued" | "embedding" | "discovering" | "generating" | "completed" | "partial" | "failed";
  documents_total: number;
  documents_processed: number;
  chunks_embedded: number;
  candidates_found: number;
  substacks_created: number;
  substacks_updated: number;
  failures: number;
  error: string | null;
}

export function startAnalysis(accountId: string): Promise<AnalysisRun[]> {
  return apiFetch(`/accounts/${accountId}/analysis`, { method: "POST" });
}

export function listAnalysis(accountId: string): Promise<AnalysisRun[]> {
  return apiFetch(`/accounts/${accountId}/analysis`);
}

export function retryAnalysis(runId: string): Promise<{ queued: number; run: AnalysisRun }> {
  return apiFetch(`/analysis/${runId}/retry`, { method: "POST" });
}

export function fileAllSubstacks(accountId: string): Promise<{ filed: number }> {
  return apiFetch(`/accounts/${accountId}/stacks/file-all`, { method: "POST" });
}

export interface DriveSyncResult { synced: number; ingested: number; skipped: number; errors: string[] }

export function syncDriveWorkspace(workspaceId: string): Promise<DriveSyncResult> {
  return apiFetch(`/drive/workspaces/${workspaceId}/sync`, { method: "POST" });
}
