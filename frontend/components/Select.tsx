"use client";

import { useEffect, useId, useRef, useState } from "react";

/**
 * An accessible listbox, replacing the native `<select>`.
 *
 * A native select paints its popup with OS chrome — on Windows that is a hard blue
 * highlight that ignores every token in this app and looks broken in dark mode. It is also
 * the one control CSS genuinely cannot style.
 *
 * The tradeoff is that rebuilding it means rebuilding its keyboard contract too, so this
 * implements the WAI-ARIA combobox/listbox pattern rather than just a styled div:
 *
 *   Enter / Space / Alt+Down   open, focusing the selected option
 *   Arrow Up / Down            move the active option (opens if closed)
 *   Home / End                 first / last
 *   Type-ahead                 jump to the next option starting with the typed letters
 *   Enter                      commit the active option
 *   Escape / blur / outside    close without changing the value
 *
 * On a touch device the panel is the same component — no hover states are required to
 * operate it, and every option clears the 44px target from globals.css.
 */

export interface SelectOption {
  value: string;
  label: string;
  hint?: string;
}

export function Select({
  value,
  options,
  onChange,
  id,
  ariaLabel,
  className = "",
}: {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  id?: string;
  ariaLabel?: string;
  className?: string;
}) {
  const generated = useId();
  const listId = `${id ?? generated}-listbox`;

  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const typeahead = useRef({ buffer: "", at: 0 });

  const selectedIndex = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  );
  const selected = options[selectedIndex];

  // Close on any interaction outside the component — pointerdown rather than click so the
  // panel is gone before the underlying control receives the press.
  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  // Keep the active option in view when arrowing through a long list.
  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector<HTMLElement>(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const openWith = (index: number) => {
    setActive(index);
    setOpen(true);
  };

  const commit = (index: number) => {
    const opt = options[index];
    if (opt) onChange(opt.value);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!open) openWith(selectedIndex);
        else setActive((i) => Math.min(i + 1, options.length - 1));
        return;
      case "ArrowUp":
        e.preventDefault();
        if (!open) openWith(selectedIndex);
        else setActive((i) => Math.max(i - 1, 0));
        return;
      case "Home":
        if (open) {
          e.preventDefault();
          setActive(0);
        }
        return;
      case "End":
        if (open) {
          e.preventDefault();
          setActive(options.length - 1);
        }
        return;
      case "Enter":
        e.preventDefault();
        if (open) commit(active);
        else openWith(selectedIndex);
        return;
      case " ":
        // Space must not scroll the page while the control has focus.
        e.preventDefault();
        if (open) commit(active);
        else openWith(selectedIndex);
        return;
      case "Escape":
        if (open) {
          e.preventDefault();
          setOpen(false);
        }
        return;
      case "Tab":
        setOpen(false);
        return;
      default:
        break;
    }

    // Type-ahead: letters typed within a second accumulate into one search term.
    if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) {
      const now = Date.now();
      const t = typeahead.current;
      t.buffer = now - t.at > 1000 ? e.key : t.buffer + e.key;
      t.at = now;

      const from = open ? active : selectedIndex;
      const needle = t.buffer.toLowerCase();
      const order = [
        ...options.slice(from + 1),
        ...options.slice(0, from + 1),
      ];
      const hit = order.find((o) => o.label.toLowerCase().startsWith(needle));
      if (hit) {
        const idx = options.indexOf(hit);
        if (open) setActive(idx);
        else onChange(hit.value);
      }
    }
  };

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        id={id}
        type="button"
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={open ? listId : undefined}
        aria-label={ariaLabel}
        onClick={() => (open ? setOpen(false) : openWith(selectedIndex))}
        onKeyDown={onKeyDown}
        className="input flex w-full items-center justify-between gap-2 text-left"
        style={open ? { borderColor: "var(--brand-ring)", boxShadow: "0 0 0 3px var(--brand-soft)" } : undefined}
      >
        <span className="truncate font-mono text-[13px]">{selected?.label ?? "—"}</span>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`h-3.5 w-3.5 shrink-0 text-faint transition-transform duration-150 ${
            open ? "rotate-180" : ""
          }`}
          aria-hidden
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {open && (
        <ul
          id={listId}
          ref={listRef}
          role="listbox"
          aria-label={ariaLabel}
          tabIndex={-1}
          className="pop absolute z-50 mt-1.5 max-h-64 w-full overflow-auto rounded-md border border-line bg-surface p-1"
          style={{ boxShadow: "var(--elev-3)" }}
        >
          {options.map((o, i) => {
            const isSelected = o.value === value;
            const isActive = i === active;
            return (
              <li key={o.value}>
                <button
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  data-index={i}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => commit(i)}
                  className="flex w-full items-center gap-2 rounded px-2.5 py-2 text-left transition-colors"
                  style={{
                    background: isActive ? "var(--surface-2)" : "transparent",
                    boxShadow: isSelected ? "inset 2px 0 0 var(--brand)" : undefined,
                  }}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-mono text-[13px] text-body">
                      {o.label}
                    </span>
                    {o.hint && (
                      <span className="mt-0.5 block truncate text-[11px] text-faint">
                        {o.hint}
                      </span>
                    )}
                  </span>
                  {isSelected && (
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="var(--brand)"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="h-3.5 w-3.5 shrink-0"
                      aria-hidden
                    >
                      <path d="M20 6L9 17l-5-5" />
                    </svg>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
