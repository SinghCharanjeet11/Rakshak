"use client";

import { useCallback, useState } from "react";
import type { Severity } from "@/lib/api";

/**
 * Chart primitives. Inline SVG on purpose — every chart here is a few dozen marks, and a
 * charting library would cost more bundle than the entire rest of the route.
 *
 * Conventions applied throughout, from the dataviz method:
 *  - marks are thin; grid and axes are recessive
 *  - stacked/adjacent fills carry a 2px surface gap so segments never bleed together
 *  - data-ends are 4px-rounded and anchored to the baseline
 *  - every chart ships a hover layer and an accessible table fallback; identity is never
 *    carried by colour alone
 */

export const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];

export const SEVERITY_VAR: Record<Severity, string> = {
  critical: "var(--sev-critical)",
  high: "var(--sev-high)",
  medium: "var(--sev-medium)",
  low: "var(--sev-low)",
};

export type TooltipState = {
  x: number;
  y: number;
  title: string;
  rows: { label: string; value: string; color?: string }[];
} | null;

export function useTooltip() {
  const [tip, setTip] = useState<TooltipState>(null);
  const show = useCallback(
    (
      e: React.MouseEvent,
      title: string,
      rows: { label: string; value: string; color?: string }[],
    ) => {
      const host = (e.currentTarget as SVGElement).closest("[data-chart-host]");
      if (!host) return;
      const r = host.getBoundingClientRect();
      setTip({ x: e.clientX - r.left, y: e.clientY - r.top, title, rows });
    },
    [],
  );
  const hide = useCallback(() => setTip(null), []);
  return { tip, show, hide };
}

export function Tooltip({ tip }: { tip: TooltipState }) {
  if (!tip) return null;
  return (
    <div
      role="presentation"
      className="pointer-events-none absolute z-20 min-w-[9rem] max-w-[16rem] rounded-md border border-line bg-surface px-2.5 py-2 text-xs shadow-lg"
      style={{
        left: Math.max(0, tip.x + 12),
        top: Math.max(0, tip.y - 8),
        transform: tip.x > 320 ? "translateX(-100%) translateX(-24px)" : undefined,
      }}
    >
      <div className="font-medium text-body">{tip.title}</div>
      {tip.rows.map((r, i) => (
        <div key={i} className="mt-1 flex items-center gap-1.5 text-muted">
          {r.color && (
            <span
              className="h-2 w-2 shrink-0 rounded-[2px]"
              style={{ background: r.color }}
              aria-hidden
            />
          )}
          <span className="min-w-0 flex-1 truncate">{r.label}</span>
          <span className="tabular-nums text-body">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

export function ChartCard({
  title,
  hint,
  legend,
  children,
  table,
}: {
  title: string;
  hint?: string;
  legend?: React.ReactNode;
  children: React.ReactNode;
  /** Accessible equivalent — a chart is never the only way to read the data. */
  table?: React.ReactNode;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <section className="card reveal lift flex flex-col p-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold text-body">{title}</h3>
        {hint && <p className="text-xs text-faint">{hint}</p>}
        {table && (
          <button
            type="button"
            onClick={() => setShowTable((v) => !v)}
            className="no-print ml-auto rounded px-1.5 py-0.5 text-[11px] text-faint transition-colors hover:bg-surface-2 hover:text-body"
            aria-expanded={showTable}
          >
            {showTable ? "chart" : "table"}
          </button>
        )}
      </div>
      {legend && <div className="mt-2">{legend}</div>}
      <div data-chart-host className="relative mt-3 flex-1">
        {showTable && table ? table : children}
      </div>
    </section>
  );
}

export function Legend({
  items,
}: {
  items: { label: string; color: string; value?: string }[];
}) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1">
      {items.map((it) => (
        <li key={it.label} className="inline-flex items-center gap-1.5 text-xs text-muted">
          <span
            className="h-2 w-2 rounded-[2px]"
            style={{ background: it.color }}
            aria-hidden
          />
          {it.label}
          {it.value !== undefined && (
            <span className="tabular-nums text-faint">{it.value}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function EmptyChart({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex h-full min-h-[6rem] items-center justify-center text-center text-xs text-faint">
      {children}
    </p>
  );
}
