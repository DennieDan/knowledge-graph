export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const loginUrl = `${API_URL}/auth/google/login`;

export interface Me {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  drive_linked: boolean;
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

export async function logout(): Promise<void> {
  await fetch(`${API_URL}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}
