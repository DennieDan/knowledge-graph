"use client";

import { useEffect, useId, useRef, useState } from "react";
import Icon from "./icons";
import styles from "./multi-select-chip.module.css";

export interface MultiSelectOption {
  value: string;
  label: string;
  icon?: string;
  count?: number;
}

/** Filter chip that opens a checkbox menu; an empty selection means "all". */
export default function MultiSelectChip({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: MultiSelectOption[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const toggle = (value: string) =>
    onChange(
      selected.includes(value)
        ? selected.filter((item) => item !== value)
        : options.map((option) => option.value).filter((item) => item === value || selected.includes(item)),
    );

  const summary =
    selected.length === 0
      ? label
      : selected.length === 1
        ? options.find((option) => option.value === selected[0])?.label ?? label
        : `${label} · ${selected.length}`;

  return (
    <div ref={rootRef} className={styles.root}>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((value) => !value)}
        className={`${styles.chip} ${selected.length ? styles.chipActive : ""}`}
      >
        {summary}
        <Icon name="chevron-down" size={13} />
      </button>
      {open && (
        <div id={menuId} role="group" aria-label={label} className={styles.menu}>
          {options.map((option) => (
            <label key={option.value} className={styles.option}>
              <input
                type="checkbox"
                checked={selected.includes(option.value)}
                onChange={() => toggle(option.value)}
              />
              {option.icon && <Icon name={option.icon} size={14} />}
              <span className={styles.optionLabel}>{option.label}</span>
              {option.count !== undefined && <span className={styles.count}>{option.count}</span>}
            </label>
          ))}
          <div className={styles.footer}>
            <button type="button" className={styles.clear} disabled={selected.length === 0} onClick={() => onChange([])}>
              Clear
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
