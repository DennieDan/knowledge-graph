export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const loginUrl = `${API_URL}/auth/google/login`;

export interface Me {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  drive_linked: boolean;
  whatsapp_linked: boolean;
}

export interface DriveFile {
  id: string;
  name: string;
  mimeType: string;
  modifiedTime?: string;
  webViewLink?: string;
}

export interface DriveFileList {
  files: DriveFile[];
  nextPageToken?: string;
}

export interface DriveTreeItem {
  id: string;
  name: string;
  mimeType: string;
  parents?: string[];
  modifiedTime?: string;
}

export interface DriveSelection {
  configured: boolean;
  share_all: boolean;
  file_ids: string[];
}

export async function getMe(): Promise<Me | null> {
  const res = await fetch(`${API_URL}/auth/me`, { credentials: "include" });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(`GET /auth/me failed: ${res.status}`);
  return res.json();
}

export async function listDriveFiles(): Promise<DriveFileList> {
  const res = await fetch(`${API_URL}/drive/files`, { credentials: "include" });
  if (!res.ok) throw new Error(`GET /drive/files failed: ${res.status}`);
  return res.json();
}

export function driveTree(): Promise<{ files: DriveTreeItem[] }> {
  return apiFetch("/drive/tree");
}

export function getDriveSelection(): Promise<DriveSelection> {
  return apiFetch("/drive/selection");
}

export function putDriveSelection(
  shareAll: boolean,
  fileIds: string[],
): Promise<DriveSelection> {
  return apiFetch("/drive/selection", {
    method: "PUT",
    body: JSON.stringify({ share_all: shareAll, file_ids: fileIds }),
  });
}

export async function logout(): Promise<void> {
  await fetch(`${API_URL}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export interface WhatsappConnectionStatus {
  status: string;
  phone_number: string | null;
}

export interface WhatsappQr {
  mimetype: string;
  data: string;
}

export interface WhatsappChatItem {
  chat_jid: string;
  name: string | null;
  chat_type: string;
  last_message_at: string | null;
  import_status: "none" | "importing" | "imported" | "failed";
  message_count: number;
}

export interface WhatsappImportItem {
  chat_jid: string;
  name: string | null;
  import_status: "none" | "importing" | "imported" | "failed";
  import_error: string | null;
  message_count: number;
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

export function whatsappConnect(): Promise<WhatsappConnectionStatus> {
  return apiFetch("/whatsapp/connect", { method: "POST" });
}

export function whatsappStatus(): Promise<WhatsappConnectionStatus> {
  return apiFetch("/whatsapp/connect/status");
}

export function whatsappQr(): Promise<WhatsappQr> {
  return apiFetch("/whatsapp/connect/qr");
}

export function whatsappPairing(phoneNumber: string): Promise<{ code: string }> {
  return apiFetch("/whatsapp/connect/pairing", {
    method: "POST",
    body: JSON.stringify({ phone_number: phoneNumber }),
  });
}

export function whatsappDisconnect(): Promise<{ status: string }> {
  return apiFetch("/whatsapp/connect", { method: "DELETE" });
}

export function whatsappChats(): Promise<WhatsappChatItem[]> {
  return apiFetch("/whatsapp/chats");
}

export function whatsappImport(chatIds: string[]): Promise<{ queued: string[] }> {
  return apiFetch("/whatsapp/imports", {
    method: "POST",
    body: JSON.stringify({ chat_ids: chatIds }),
  });
}

export function whatsappImports(): Promise<WhatsappImportItem[]> {
  return apiFetch("/whatsapp/imports");
}
