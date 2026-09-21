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
export function whatsappImport(chatIds: string[]): Promise<{ queued: string[] }> {
  return apiFetch("/whatsapp/imports", { method: "POST", body: JSON.stringify({ chat_ids: chatIds }) });
}
export function whatsappImports(): Promise<WhatsappImportItem[]> { return apiFetch("/whatsapp/imports") }
