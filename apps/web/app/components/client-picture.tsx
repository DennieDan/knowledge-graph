"use client";

import { useEffect, useMemo, useState } from "react";
import { getClientPicture, type ApiClientPicture } from "../lib/api";
import { type StackType } from "../lib/stacks";
import styles from "./client-picture.module.css";

interface Props {
  accountId: string;
  substackId: string;
  stackTypes: StackType[];
  onOpen: (id: string) => void;
}

/** Links-only client neighbourhood as a grouped list — no graph layout (#99 Step 1). */
export default function ClientPicture({ accountId, substackId, stackTypes, onOpen }: Props) {
  const [picture, setPicture] = useState<ApiClientPicture | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPicture(null);
    setError(null);
    getClientPicture(accountId, substackId)
      .then((body) => {
        if (!cancelled) setPicture(body);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load linked records.");
      });
    return () => {
      cancelled = true;
    };
  }, [accountId, substackId]);

  const groups = useMemo(() => {
    if (!picture) return [];
    const byType = new Map<string, ApiClientPicture["nodes"]>();
    for (const node of picture.nodes) {
      if (node.id === picture.subject.id) continue;
      const list = byType.get(node.type_id) ?? [];
      list.push(node);
      byType.set(node.type_id, list);
    }
    // Prefer orders and items first for the client briefing use case.
    const preferred = ["sales-orders", "items"];
    const keys = [
      ...preferred.filter((key) => byType.has(key)),
      ...[...byType.keys()].filter((key) => !preferred.includes(key)).sort(),
    ];
    return keys.map((typeId) => ({
      typeId,
      label: stackTypes.find((candidate) => candidate.id === typeId)?.name ?? typeId,
      nodes: (byType.get(typeId) ?? []).slice().sort((a, b) => a.name.localeCompare(b.name)),
    }));
  }, [picture, stackTypes]);

  const omitted = picture?.omitted_neighbours[picture.subject.id] ?? 0;

  return (
    <section className={styles.section} aria-label="Client picture">
      <header className={styles.header}>
        <h2>Linked records</h2>
        {picture && (
          <p className={styles.meta}>
            Within {picture.caps.max_depth} hops
            {omitted > 0 ? ` · +${omitted} more at this client` : ""}
            {picture.truncated ? " · capped" : ""}
          </p>
        )}
      </header>
      {!picture && !error && <p className={styles.empty}>Loading linked records…</p>}
      {error && <p className={styles.empty}>{error}</p>}
      {picture && groups.length === 0 && <p className={styles.empty}>No linked orders or items yet.</p>}
      {groups.map((group) => (
        <div key={group.typeId} className={styles.group}>
          <h3>{group.label} <small>{group.nodes.length}</small></h3>
          <ul className={styles.list}>
            {group.nodes.map((node) => (
              <li key={node.id}>
                <button type="button" onClick={() => onOpen(node.id)}>
                  <strong>{node.name}</strong>
                  <span>{node.depth === 1 ? "Direct link" : `${node.depth} hops`}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
