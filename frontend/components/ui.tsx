"use client";

import { motion } from "framer-motion";
import { useState } from "react";
import type { Severity } from "@/lib/api";

export type Verdict = "pass" | "fail" | "exempt";

const SEVERITY_STYLE: Record<Severity, string> = {
  critical: "border-fail-border bg-fail-bg text-fail-fg",
  high: "border-warn-border bg-warn-bg text-warn-fg",
  medium: "border-warn-border bg-warn-bg text-warn-fg",
  low: "border-line bg-surface-2 text-muted",
};

export function SeverityTag({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide ${SEVERITY_STYLE[severity]}`}
    >
      {severity}
    </span>
  );
}

const VERDICT_STYLE: Record<Verdict, string> = {
  pass: "border-pass-border bg-pass-bg text-pass-fg",
  fail: "border-fail-border bg-fail-bg text-fail-fg",
  exempt: "border-exempt-border bg-exempt-bg text-exempt-fg",
};
const VERDICT_GLYPH: Record<Verdict, string> = {
  pass: "✓",
  fail: "✕",
  exempt: "✓",
};

/** Colour is never the only signal — the glyph and the word carry it too. */
export function VerdictPill({ verdict }: { verdict: Verdict }) {
  return (
    <span
      className={`pop inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${VERDICT_STYLE[verdict]}`}
    >
      <span aria-hidden>{VERDICT_GLYPH[verdict]}</span>
      {verdict.toUpperCase()}
    </span>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`shimmer rounded bg-surface-2 ${className}`} aria-hidden />
  );
}

export function ErrorNote({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      role="alert"
      className="rounded-md border border-fail-border bg-fail-bg px-4 py-3 text-sm text-fail-fg"
    >
      {title && <p className="font-semibold">{title}</p>}
      <div className={title ? "mt-1" : ""}>{children}</div>
    </div>
  );
}

export function WarnNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-warn-border bg-warn-bg px-4 py-3 text-xs leading-relaxed text-warn-fg">
      {children}
    </div>
  );
}

export function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="label">{label}</div>
      <div
        className={`mt-0.5 truncate text-sm text-body ${mono ? "font-mono text-xs" : ""}`}
        title={typeof value === "string" ? value : undefined}
      >
        {value}
      </div>
    </div>
  );
}

/** Copying a clause citation into a ticket is the single most likely next action. */
export function CopyButton({
  value,
  label = "Copy",
}: {
  value: string;
  label?: string;
}) {
  const [done, setDone] = useState(false);

  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setDone(true);
          setTimeout(() => setDone(false), 1400);
        } catch {
          /* clipboard blocked — the text is on screen and selectable anyway */
        }
      }}
      className={`rounded px-1.5 py-0.5 text-[11px] transition-all duration-150 hover:bg-surface-2 ${done ? "scale-105 text-pass-fg" : "text-faint hover:text-body"}`}
      aria-label={`${label}: ${value}`}
    >
      {done ? "copied" : label}
    </button>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string; count?: number }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex rounded-md border border-line bg-surface p-0.5"
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            aria-pressed={active}
            className={`relative rounded px-2.5 py-1 text-xs font-medium transition-colors ${
              active ? "text-paper" : "text-muted hover:text-body"
            }`}
          >
            {active && (
              <motion.span
                layoutId={`seg-${label}`}
                transition={{ type: "spring", stiffness: 480, damping: 36 }}
                className="absolute inset-0 rounded bg-ink"
                aria-hidden
              />
            )}
            <span className="relative z-10">{o.label}</span>
            {o.count !== undefined && (
              <span className={`relative z-10 ml-1.5 tabular-nums ${active ? "opacity-70" : "text-faint"}`}>
                {o.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
