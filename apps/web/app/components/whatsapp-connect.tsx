"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  whatsappChats,
  whatsappConnect,
  whatsappDisconnect,
  whatsappImport,
  whatsappImports,
  whatsappPairing,
  whatsappQr,
  whatsappStatus,
  whatsappUpload,
  whatsappUploads,
  whatsappWipeUploads,
  type WhatsappChatItem,
  type WhatsappImportItem,
  type WhatsappUploadItem,
} from "../lib/api";
import { track } from "../lib/analytics";
import styles from "./whatsapp-connect.module.css";

type Step = "choose" | "upload" | "uploaded" | "link" | "chats" | "importing" | "done";

type UploadOutcome = { file: string; name?: string; messages?: number; added?: number; error?: string };

const STATUS_LABELS: Record<string, string> = {
  STOPPED: "Stopped — tap Connect to restart",
  STARTING: "Starting…",
  SCAN_QR_CODE: "Scan the QR code with WhatsApp",
  WORKING: "Connected",
  FAILED: "Connection failed — try again",
};

const UPLOAD_ERRORS: Record<string, string> = {
  not_a_whatsapp_export: "This doesn't look like a WhatsApp chat export.",
  no_messages_in_export: "No messages found in this export.",
  export_too_large: "This export is too large (max 5 MB).",
  invalid_zip: "This .zip file could not be opened.",
  zip_has_no_chat_txt: "This .zip has no chat text file inside.",
};

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}

export default function WhatsAppConnect({
  onClose,
  onChanged,
  accountId,
  linked = false,
  displayName,
}: {
  onClose: () => void;
  onChanged: () => void;
  accountId?: string;
  linked?: boolean;
  displayName?: string | null;
}) {
  const [step, setStep] = useState<Step>(linked ? "link" : "choose");
  const [status, setStatus] = useState("STARTING");
  const [qr, setQr] = useState<string | null>(null);
  const [phone, setPhone] = useState("");
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [chats, setChats] = useState<WhatsappChatItem[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [imports, setImports] = useState<WhatsappImportItem[]>([]);
  const [uploads, setUploads] = useState<WhatsappUploadItem[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [meName, setMeName] = useState(displayName ?? "");
  const [uploading, setUploading] = useState(false);
  const [outcomes, setOutcomes] = useState<UploadOutcome[]>([]);
  const [error, setError] = useState<string | null>(null);
  const changed = useRef(false);

  const close = useCallback(() => {
    if (changed.current) onChanged();
    onClose();
  }, [onChanged, onClose]);

  const loadUploads = useCallback(() => {
    whatsappUploads().then(setUploads).catch(() => setUploads([]));
  }, []);

  useEffect(() => {
    loadUploads();
  }, [loadUploads]);

  const loadChats = useCallback(async () => {
    try {
      const list = await whatsappChats();
      setChats(list);
      setSelected(new Set());
      setStep("chats");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load chats");
    }
  }, []);

  const startLink = useCallback(() => {
    setError(null);
    setStep("link");
    track("whatsapp_connect_started");
    whatsappConnect()
      .then((s) => {
        setStatus(s.status);
        if (s.status === "WORKING") {
          changed.current = true;
          loadChats();
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "connect_failed"));
  }, [loadChats]);

  // Already linked: go straight to the chat picker, as before.
  const autoLinked = useRef(false);
  useEffect(() => {
    if (!linked || autoLinked.current) return;
    autoLinked.current = true;
    startLink();
  }, [linked, startLink]);

  // Poll session status while linking; refresh the QR whenever WhatsApp rotates it.
  useEffect(() => {
    if (step !== "link") return;
    const timer = setInterval(async () => {
      try {
        const s = await whatsappStatus();
        setStatus(s.status);
        if (s.status === "SCAN_QR_CODE") {
          const code = await whatsappQr();
          setQr(`data:${code.mimetype};base64,${code.data}`);
        }
        if (s.status === "WORKING") {
          changed.current = true;
          clearInterval(timer);
          loadChats();
        }
      } catch {
        // Transient polling failures are ignored; the next tick retries.
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [step, loadChats]);

  // Poll import progress.
  useEffect(() => {
    if (step !== "importing") return;
    const timer = setInterval(async () => {
      try {
        const list = await whatsappImports();
        setImports(list);
        if (list.every((i) => i.import_status !== "importing")) {
          clearInterval(timer);
          setStep("done");
          changed.current = true;
        }
      } catch {
        // Ignore transient failures.
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [step]);

  const requestPairing = async () => {
    setError(null);
    try {
      const { code } = await whatsappPairing(phone.replace(/[^0-9]/g, ""));
      setPairingCode(code);
    } catch (e) {
      setError(e instanceof Error ? e.message : "pairing_failed");
    }
  };

  const startImport = async () => {
    setError(null);
    try {
      await whatsappImport([...selected], accountId);
      track("whatsapp_import_started", { chat_count: selected.size });
      setImports(await whatsappImports());
      setStep("importing");
    } catch (e) {
      setError(e instanceof Error ? e.message : "import_failed");
    }
  };

  const disconnect = async () => {
    try {
      await whatsappDisconnect();
      changed.current = true;
      onChanged();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "disconnect_failed");
    }
  };

  const uploadFiles = async () => {
    if (!accountId) {
      setError("Choose an account before uploading chats.");
      return;
    }
    setError(null);
    setUploading(true);
    const results: UploadOutcome[] = [];
    for (const file of files) {
      try {
        const result = await whatsappUpload(file, accountId, meName);
        results.push({ file: file.name, name: result.name ?? file.name, messages: result.message_count, added: result.new_messages });
      } catch (e) {
        const code = e instanceof Error ? e.message : "upload_failed";
        results.push({ file: file.name, error: UPLOAD_ERRORS[code] ?? code });
      }
    }
    const succeeded = results.filter((r) => !r.error);
    track("whatsapp_upload_completed", {
      chat_count: succeeded.length,
      failed_count: results.length - succeeded.length,
      message_count: succeeded.reduce((sum, r) => sum + (r.messages ?? 0), 0),
    });
    if (succeeded.length > 0) changed.current = true;
    setOutcomes(results);
    setFiles([]);
    setUploading(false);
    setStep("uploaded");
    loadUploads();
  };

  const wipeUploads = async () => {
    if (!window.confirm("Wipe out all imported chats? Their messages and Conversations records will be deleted.")) return;
    setError(null);
    try {
      const { deleted } = await whatsappWipeUploads();
      track("whatsapp_uploads_wiped", { chat_count: deleted });
      changed.current = true;
      setUploads([]);
      setStep("choose");
    } catch (e) {
      setError(e instanceof Error ? e.message : "wipe_failed");
    }
  };

  const toggle = (jid: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(jid)) next.delete(jid);
      else next.add(jid);
      return next;
    });

  const uploadedList = uploads.length > 0 && (
    <>
      <p className={styles.sectionLabel}>Uploaded chats · no live sync</p>
      <ul className={styles.chatList}>
        {uploads.map((item) => (
          <li key={item.chat_jid} className={styles.importRow}>
            <span className={styles.chatName}>{item.name ?? "WhatsApp chat"}</span>
            <span className={styles.chatMeta}>
              {item.chat_type}
              {item.last_message_at && ` · ${formatDate(item.last_message_at)}`}
              {` · ${item.message_count} msgs`}
              {item.import_status === "failed" && " · failed"}
            </span>
          </li>
        ))}
      </ul>
    </>
  );

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="WhatsApp import">
      <div className={styles.dialog}>
        <div className={styles.head}>
          <h2 className={styles.heading}>WhatsApp</h2>
          <button type="button" className={styles.closeBtn} onClick={close} aria-label="Close">
            ×
          </button>
        </div>

        {error && <p className={styles.error}>{error}</p>}

        {step === "choose" && (
          <>
            <div className={styles.options}>
              <button type="button" className={styles.option} onClick={() => setStep("upload")}>
                <span className={styles.optionTitle}>Upload chat export</span>
                <span className={styles.optionText}>
                  Use a chat exported from WhatsApp (.txt or .zip). No phone linking needed.
                </span>
              </button>
              <button type="button" className={styles.option} onClick={startLink}>
                <span className={styles.optionTitle}>Link WhatsApp</span>
                <span className={styles.optionText}>
                  Scan a QR code to import history and keep chats in sync.
                </span>
              </button>
            </div>
            {uploadedList}
            {uploads.length > 0 && (
              <div className={styles.actions}>
                <button type="button" className={`${styles.btnText} ${styles.btnDanger}`} onClick={wipeUploads}>
                  Wipe out imported chats
                </button>
              </div>
            )}
          </>
        )}

        {step === "upload" && (
          <div className={styles.uploadStep}>
            <ol className={styles.steps}>
              <li>Open the chat in WhatsApp.</li>
              <li>
                iPhone: tap the chat name → <strong>Export chat</strong>. Android: ⋮ →{" "}
                <strong>More</strong> → <strong>Export chat</strong>.
              </li>
              <li>
                Choose <strong>Without media</strong>, save the file, and upload it here.
              </li>
            </ol>
            <label className={styles.field}>
              <span className={styles.muted}>Your name in these chats</span>
              <input
                className={styles.phoneInput}
                type="text"
                placeholder="As it appears in the export"
                value={meName}
                onChange={(e) => setMeName(e.target.value)}
              />
            </label>
            <label className={styles.dropZone}>
              <input
                type="file"
                multiple
                accept=".txt,.zip,text/plain,application/zip"
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
              <span>
                {files.length === 0
                  ? "Choose .txt or .zip export files"
                  : files.map((f) => f.name).join(", ")}
              </span>
            </label>
            <p className={styles.muted}>Uploaded chats stay private to you.</p>
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.btnTonal}
                disabled={files.length === 0 || uploading}
                aria-busy={uploading}
                onClick={uploadFiles}
              >
                {uploading ? "Uploading…" : `Upload ${files.length > 1 ? `${files.length} chats` : "chat"}`}
              </button>
              <button type="button" className={styles.btnText} onClick={() => setStep("choose")}>
                Back
              </button>
            </div>
          </div>
        )}

        {step === "uploaded" && (
          <>
            <p className={styles.muted}>Upload finished.</p>
            <ul className={styles.chatList}>
              {outcomes.map((item) => (
                <li key={item.file} className={styles.importRow}>
                  <span className={styles.chatName}>{item.name ?? item.file}</span>
                  <span className={styles.chatMeta}>
                    {item.error
                      ? item.error
                      : `${item.messages} messages${item.added !== item.messages ? ` · ${item.added} new` : ""}`}
                  </span>
                </li>
              ))}
            </ul>
            <div className={styles.actions}>
              <button type="button" className={styles.btnTonal} onClick={close}>
                Done
              </button>
              <button type="button" className={styles.btnText} onClick={() => setStep("upload")}>
                Upload more
              </button>
            </div>
          </>
        )}

        {step === "link" && (
          <div className={styles.linkStep}>
            <p className={styles.muted}>{STATUS_LABELS[status] ?? status}</p>
            {status === "SCAN_QR_CODE" && qr && (
              <img className={styles.qr} src={qr} alt="WhatsApp QR code" />
            )}
            {status === "SCAN_QR_CODE" && !qr && (
              <p className={styles.muted}>Loading QR code…</p>
            )}
            <p className={styles.hint}>
              Open WhatsApp → Settings → Linked devices → Link a device
            </p>
            <div className={styles.pairing}>
              <p className={styles.muted}>Or link with your phone number:</p>
              <div className={styles.pairingRow}>
                <input
                  className={styles.phoneInput}
                  type="tel"
                  placeholder="+65 9123 4567"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
                <button
                  type="button"
                  className={styles.btnTonal}
                  disabled={phone.replace(/[^0-9]/g, "").length < 6}
                  onClick={requestPairing}
                >
                  Get code
                </button>
              </div>
              {pairingCode && (
                <p className={styles.pairingCode}>
                  Enter in WhatsApp: <strong>{pairingCode}</strong>
                </p>
              )}
            </div>
            {!linked && (
              <button type="button" className={styles.btnText} onClick={() => setStep("choose")}>
                Back
              </button>
            )}
          </div>
        )}

        {step === "chats" && (
          <>
            <p className={styles.muted}>
              Pick the chats to import. Imported chats stay private to you.
            </p>
            {chats === null && <p className={styles.muted}>Loading chats…</p>}
            {chats !== null && chats.length === 0 && (
              <p className={styles.muted}>No chats found on this account.</p>
            )}
            {chats !== null && chats.length > 0 && (
              <ul className={styles.chatList}>
                {chats.map((chat) => (
                  <li key={chat.chat_jid}>
                    <label className={styles.chatRow}>
                      <input
                        type="checkbox"
                        disabled={chat.import_status === "importing"}
                        checked={
                          chat.import_status === "imported" || selected.has(chat.chat_jid)
                        }
                        onChange={() => toggle(chat.chat_jid)}
                      />
                      <span className={styles.chatName}>
                        {chat.name ?? chat.chat_jid.split("@")[0]}
                      </span>
                      <span className={styles.chatMeta}>
                        {chat.chat_type}
                        {chat.last_message_at && ` · ${formatDate(chat.last_message_at)}`}
                        {chat.import_status === "imported" &&
                          ` · imported ${chat.message_count} msgs`}
                        {chat.import_status === "importing" && " · importing…"}
                        {chat.import_status === "failed" && " · failed"}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.btnTonal}
                disabled={selected.size === 0}
                onClick={startImport}
              >
                Import {selected.size > 0 ? `${selected.size} ` : ""}chat
                {selected.size === 1 ? "" : "s"}
              </button>
              <button type="button" className={styles.btnText} onClick={disconnect}>
                Disconnect
              </button>
              <button type="button" className={styles.btnText} onClick={() => setStep("upload")}>
                Upload export
              </button>
            </div>
            {uploadedList}
            {uploads.length > 0 && (
              <div className={styles.actions}>
                <button type="button" className={`${styles.btnText} ${styles.btnDanger}`} onClick={wipeUploads}>
                  Wipe out imported chats
                </button>
              </div>
            )}
          </>
        )}

        {(step === "importing" || step === "done") && (
          <>
            <p className={styles.muted}>
              {step === "importing" ? "Importing chat history…" : "Import finished."}
            </p>
            <ul className={styles.chatList}>
              {imports.map((item) => (
                <li key={item.chat_jid} className={styles.importRow}>
                  <span className={styles.chatName}>
                    {item.name ?? item.chat_jid.split("@")[0]}
                  </span>
                  <span className={styles.chatMeta}>
                    {item.import_status === "importing" && "Importing…"}
                    {item.import_status === "imported" &&
                      `${item.message_count} messages imported`}
                    {item.import_status === "failed" &&
                      `Failed${item.import_error ? ` — ${item.import_error}` : ""}`}
                  </span>
                </li>
              ))}
            </ul>
            {step === "done" && (
              <div className={styles.actions}>
                <button type="button" className={styles.btnTonal} onClick={close}>
                  Done
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
