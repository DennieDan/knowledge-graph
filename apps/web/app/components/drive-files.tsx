"use client";

import { useEffect, useState } from "react";
import { listDriveFiles, type DriveFile } from "../lib/api";
import styles from "./drive-files.module.css";

function formatModified(iso?: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}

export default function DriveFiles() {
  const [files, setFiles] = useState<DriveFile[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    listDriveFiles()
      .then((data) => setFiles(data.files))
      .catch(() => setError(true));
  }, []);

  return (
    <section className={styles.driveFiles} aria-live="polite">
      <span className={styles.overline}>Google Drive</span>
      {error && (
        <p className={styles.muted}>
          Couldn't load your Drive files. Try linking Google Drive again.
        </p>
      )}
      {!error && files === null && (
        <p className={styles.muted}>Loading Drive files…</p>
      )}
      {!error && files !== null && files.length === 0 && (
        <p className={styles.muted}>No files found in this Drive.</p>
      )}
      {!error && files !== null && files.length > 0 && (
        <>
          <p className={styles.muted}>
            {files.length} file{files.length === 1 ? "" : "s"} accessible
          </p>
          <ul className={styles.list}>
            {files.map((file) => (
              <li key={file.id}>
                <a
                  className={styles.file}
                  href={file.webViewLink}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className={styles.fileName}>{file.name}</span>
                  <span className={styles.fileMeta}>
                    {file.mimeType.replace("application/vnd.google-apps.", "Google ").replace("application/", "")}
                    {file.modifiedTime && ` · ${formatModified(file.modifiedTime)}`}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
