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
  type WhatsappChatItem,
  type WhatsappImportItem,
} from "../lib/api";
import { track } from "../lib/analytics";
import styles from "./whatsapp-connect.module.css";

type Step = "link" | "chats" | "importing" | "done";

const STATUS_LABELS: Record<string, string> = {
  STOPPED: "Stopped — tap Connect to restart",
  STARTING: "Starting…",
  SCAN_QR_CODE: "Scan the QR code with WhatsApp",
  WORKING: "Connected",
  FAILED: "Connection failed — try again",
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
}: {
  onClose: () => void;
  onChanged: () => void;
  accountId?: string;
}) {
  const [step, setStep] = useState<Step>("link");
  const [status, setStatus] = useState("STARTING");
  const [qr, setQr] = useState<string | null>(null);
  const [phone, setPhone] = useState("");
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [chats, setChats] = useState<WhatsappChatItem[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [imports, setImports] = useState<WhatsappImportItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const changed = useRef(false);

  const close = useCallback(() => {
    if (changed.current) onChanged();
    onClose();
  }, [onChanged, onClose]);

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

  useEffect(() => {
    let cancelled = false;
    track("whatsapp_connect_started");
    whatsappConnect()
      .then((s) => {
        if (cancelled) return;
        setStatus(s.status);
        if (s.status === "WORKING") {
          changed.current = true;
          loadChats();
        }
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "connect_failed"));
    return () => {
      cancelled = true;
    };
  }, [loadChats]);

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

  const toggle = (jid: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(jid)) next.delete(jid);
      else next.add(jid);
      return next;
    });

  const selectable = (chats ?? []).filter((c) => c.import_status !== "importing");

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
            </div>
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
