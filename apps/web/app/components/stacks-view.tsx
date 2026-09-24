"use client";

import { useEffect, useState } from "react";
import Icon from "./icons";
import styles from "./stacks.module.css";
import {
  SCOPE_TABS,
  inScope,
  type Scope,
  type StackType,
  type Substack,
} from "../lib/stacks";

const ROLE_FILTERS = ["Proposed", "Confirmed", "Update available", "Needs review"];

function TypeTile({
  type,
  substacks,
  scope,
  onClick,
}: {
  type: StackType;
  substacks: Substack[];
  scope: Scope;
  onClick: () => void;
}) {
  const visible = substacks.filter(
    (ss) => ss.typeId === type.id && inScope(ss, scope),
  );
  const recent = visible.slice(0, 2);

  return (
    <button onClick={onClick} className={styles.tile}>
      <div className={styles.tileTop}>
        <span className={styles.tileIcon}>
          <Icon name={type.icon} size={18} />
        </span>
        <span className={styles.chip}>
          {visible.length} {visible.length === 1 ? "item" : "items"}
        </span>
      </div>
      <h3 className={styles.tileName}>{type.name}</h3>
      <div className={styles.tileDesc}>{type.desc}</div>
      {recent.length > 0 && (
        <div className={styles.tileRecent}>
          {recent.map((ss) => (
            <div key={ss.id} className={styles.tileRecentRow}>
              <Icon name="file-text" />
              <span className={styles.tileRecentName}>{ss.name}</span>
            </div>
          ))}
        </div>
      )}
      <div className={styles.tileOpen}>
        <span>
          Open <Icon name="chevron-right" size={13} />
        </span>
      </div>
    </button>
  );
}

function SubstackCard({
  ss,
  type,
  onClick,
  onDelete,
  listMode,
}: {
  ss: Substack;
  type: StackType;
  onClick: () => void;
  onDelete: () => void;
  listMode: boolean;
}) {
  return (
    <div className={`${styles.card} ${listMode ? styles.cardList : ""}`}>
      <button
        onClick={onClick}
        className={styles.cardOpen}
        aria-label={`Open ${ss.name}`}
      />
      <div className={styles.tileTop}>
        <span className={styles.cardIcon}>
          <Icon name={type.icon} />
        </span>
        <span className={styles.chip}>{ss.role}</span>
      </div>
      <h3 className={styles.tileName}>{ss.name}</h3>
      {!listMode && <div className={styles.tileDesc}>{ss.desc}</div>}
      {!listMode && (
        <div className={styles.cardDocs}>
          {ss.docs.map((d, i) => (
            <div key={`${d}-${i}`} className={styles.cardDocRow}>
              <Icon name="file-text" />
              <span>{d}</span>
            </div>
          ))}
          <span className={styles.cardDocCount}>{ss.count} sources</span>
        </div>
      )}
      <div className={styles.cardFoot}>
        <span>
          {ss.access} · {ss.role}
        </span>
        <span className={styles.cardFootEnd}>
          {ss.updated}
          <button
            type="button"
            onClick={onDelete}
            className={styles.deleteBtn}
            aria-label={`Delete ${ss.name}`}
            title="Delete"
          >
            <Icon name="trash" size={15} />
          </button>
        </span>
      </div>
    </div>
  );
}

export default function StacksView({
  stackTypes,
  substacks,
  scope,
  selectedType,
  searchVal,
  listMode,
  notice,
  onScopeChange,
  onSelectType,
  onSearchChange,
  onToggleListMode,
  onOpenDetails,
  onAddItem,
  onDeleteItem,
}: {
  stackTypes: StackType[];
  substacks: Substack[];
  scope: Scope;
  selectedType: string | null;
  searchVal: string;
  listMode: boolean;
  notice: string;
  onScopeChange: (scope: Scope) => void;
  onSelectType: (typeId: string | null) => void;
  onSearchChange: (value: string) => void;
  onToggleListMode: () => void;
  onOpenDetails: (ss: Substack) => void;
  onAddItem: (typeId: string) => void;
  onDeleteItem: (ss: Substack) => void;
}) {
  const activeType = selectedType
    ? stackTypes.find((t) => t.id === selectedType)
    : null;
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set());

  useEffect(() => setStatusFilter(new Set()), [selectedType]);

  const toggleStatus = (role: string) =>
    setStatusFilter((current) => {
      const next = new Set(current);
      if (next.has(role)) next.delete(role);
      else next.add(role);
      return next;
    });

  const filteredSubstacks = substacks.filter(
    (ss) =>
      (selectedType ? ss.typeId === selectedType : true) &&
      inScope(ss, scope) &&
      (statusFilter.size === 0 || statusFilter.has(ss.role)) &&
      (ss.name + " " + ss.desc)
        .toLowerCase()
        .includes(searchVal.toLowerCase()),
  );

  const tabCount = (sc: Scope) =>
    selectedType
      ? substacks.filter((ss) => ss.typeId === selectedType && inScope(ss, sc))
          .length
      : stackTypes.filter((t) =>
          substacks.some((ss) => ss.typeId === t.id && inScope(ss, sc)),
        ).length;

  const visibleTypes = stackTypes
    .filter(
      (t) =>
        scope === "all" ||
        substacks.some((ss) => ss.typeId === t.id && inScope(ss, scope)),
    )
    .filter(
      (t) =>
        !searchVal ||
        t.name.toLowerCase().includes(searchVal.toLowerCase()) ||
        t.desc.toLowerCase().includes(searchVal.toLowerCase()),
    );

  return (
    <div className={styles.page}>
      {/* Hero row */}
      <div className={styles.hero}>
        <div>
          {activeType ? (
            <>
              <button
                onClick={() => {
                  onSelectType(null);
                  onSearchChange("");
                }}
                className={`${styles.ghostBtn} ${styles.backBtn}`}
              >
                <Icon name="arrow-left" size={14} /> All stacks
              </button>
              <h1 className={styles.title}>
                <span className={styles.titleIcon}>
                  <Icon name={activeType.icon} size={17} />
                </span>
                {activeType.name}
              </h1>
              <p className={styles.subtitle}>{activeType.desc}</p>
            </>
          ) : (
            <>
              <h1 className={styles.title}>Your knowledge, together.</h1>
              <p className={styles.subtitle}>
                Keep the context. Connect the pieces.
              </p>
            </>
          )}
        </div>

        {activeType && (
          <button
            onClick={() => onAddItem(activeType.id)}
            className={styles.primaryBtn}
          >
            <Icon name="plus" /> Add to {activeType.name}
          </button>
        )}
      </div>

      {/* Tabs */}
      <div role="tablist" aria-label="Scope filter" className={styles.tabs}>
        {SCOPE_TABS.map(([sc, label]) => (
          <button
            key={sc}
            role="tab"
            aria-selected={scope === sc}
            onClick={() => onScopeChange(sc)}
            className={`${styles.tab} ${scope === sc ? styles.tabActive : ""}`}
          >
            {label}
            <span className={styles.tabCount}>{tabCount(sc)}</span>
          </button>
        ))}
      </div>

      {/* Search + view toggle */}
      <div className={styles.searchRow}>
        <label className={styles.searchBox}>
          <Icon name="search" size={14} />
          <input
            value={searchVal}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-label={
              activeType ? `Search ${activeType.name}` : "Search stacks"
            }
            placeholder={
              activeType ? `Search ${activeType.name}…` : "Search stacks…"
            }
            className={styles.searchInput}
          />
        </label>
        {activeType && (
          <button
            onClick={onToggleListMode}
            aria-label={listMode ? "Grid view" : "List view"}
            className={styles.actionBtn}
          >
            <Icon name={listMode ? "layout-grid" : "list"} />
          </button>
        )}
      </div>

      {/* Status filter (multi-select) */}
      {activeType && (
        <div className={styles.filterRow} role="group" aria-label="Filter by status">
          {ROLE_FILTERS.map((role) => (
            <button
              key={role}
              type="button"
              aria-pressed={statusFilter.has(role)}
              onClick={() => toggleStatus(role)}
              className={`${styles.filterChip} ${statusFilter.has(role) ? styles.filterChipActive : ""}`}
            >
              {role}
            </button>
          ))}
        </div>
      )}

      {/* Level 1: stack type tiles */}
      {!activeType &&
        (visibleTypes.length === 0 ? (
          <div className={styles.empty}>
            <p className={styles.emptyTitle}>No stacks found</p>
            <p className={styles.emptyText}>
              Try a different filter or create a new stack.
            </p>
          </div>
        ) : (
          <div className={styles.grid}>
            {visibleTypes.map((type) => (
              <TypeTile
                key={type.id}
                type={type}
                substacks={substacks}
                scope={scope}
                onClick={() => {
                  onSelectType(type.id);
                  onSearchChange("");
                }}
              />
            ))}
          </div>
        ))}

      {/* Level 2: substacks */}
      {activeType &&
        (filteredSubstacks.length === 0 ? (
          <div className={styles.empty}>
            <p className={styles.emptyTitle}>No items found</p>
            <p className={styles.emptyText}>
              Try a different filter or add a new item.
            </p>
          </div>
        ) : (
          <div
            className={listMode ? styles.gridList : styles.gridCards}
          >
            {filteredSubstacks.map((ss) => (
              <SubstackCard
                key={ss.id}
                ss={ss}
                type={activeType}
                listMode={listMode}
                onClick={() => onOpenDetails(ss)}
                onDelete={() => onDeleteItem(ss)}
              />
            ))}
          </div>
        ))}

      {notice && (
        <div role="status" aria-live="polite" className={styles.notice}>
          {notice}
        </div>
      )}
    </div>
  );
}
