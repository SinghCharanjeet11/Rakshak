"use client";

import type { Report, Severity } from "@/lib/api";
import {
  ChartCard,
  EmptyChart,
  SEVERITY_VAR,
  Tooltip,
  useTooltip,
} from "./primitives";

/**
 * Which rules are actually being broken — magnitude across a handful of named categories,
 * so: horizontal bars, sorted descending, labels on the left where they are readable
 * without rotation.
 *
 * Bars are coloured by the rule's severity rather than by rank. That matters: a filter or
 * a re-sort must never repaint a bar, because the colour means "this is critical", not
 * "this is the first one".
 */
export function ViolationsByRule({ report }: { report: Report }) {
  const { tip, show, hide } = useTooltip();

  const byRule = new Map<string, { n: number; severity: Severity; title: string }>();
  for (const v of report.violations) {
    const cur = byRule.get(v.rule_id);
    if (cur) cur.n += 1;
    else byRule.set(v.rule_id, { n: 1, severity: v.severity, title: v.title });
  }
  const rows = [...byRule.entries()]
    .map(([rule_id, r]) => ({ rule_id, ...r }))
    .sort((a, b) => b.n - a.n || a.rule_id.localeCompare(b.rule_id));

  // Domain floor, not a literal max. In a well-curated batch every rule trips exactly
  // once, and scaling to the observed max would paint every bar full-width — a correct
  // encoding that reads as "maxed out" and tells you nothing. Anchoring the domain at 4
  // keeps a single occurrence looking like a single occurrence, and lets genuinely hot
  // rules stand out once counts do vary.
  const max = Math.max(4, ...rows.map((r) => r.n));

  return (
    <ChartCard
      title="Violations by rule"
      hint={rows.length ? `${rows.length} rule${rows.length === 1 ? "" : "s"} tripped` : undefined}
      table={
        <table className="w-full text-xs">
          <tbody>
            {rows.map((r) => (
              <tr key={r.rule_id} className="border-b border-line last:border-0">
                <td className="py-1.5 font-mono text-muted">{r.rule_id}</td>
                <td className="py-1.5 text-right tabular-nums text-body">{r.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      {rows.length === 0 ? (
        <EmptyChart>No rules tripped in this batch.</EmptyChart>
      ) : (
        <>
          <ul className="space-y-2">
            {rows.map((r, i) => (
              <li key={r.rule_id} className="grid grid-cols-[1fr_auto] items-center gap-x-3">
                <div className="min-w-0">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate font-mono text-[11px] text-muted">
                      {r.rule_id}
                    </span>
                    <span className="shrink-0 tabular-nums text-[11px] font-medium text-body">
                      {r.n}
                    </span>
                  </div>
                  <svg
                    viewBox="0 0 100 6"
                    preserveAspectRatio="none"
                    className="mt-1 h-1.5 w-full overflow-visible"
                    role="img"
                    aria-label={`${r.rule_id}: ${r.n}`}
                  >
                    <rect x={0} y={0} width={100} height={6} rx={3} fill="var(--track)" />
                    <rect
                      x={0}
                      y={0}
                      width={Math.max(2, (r.n / max) * 100)}
                      height={6}
                      rx={3}
                      fill={SEVERITY_VAR[r.severity]}
                      // grows from the axis, so the eye reads length as the measurement
                      style={{
                        transformOrigin: "left center",
                        animation: `grow-x 520ms cubic-bezier(0.22,1,0.36,1) ${i * 55}ms both`,
                      }}
                      onMouseMove={(e) =>
                        show(e, r.rule_id, [
                          { label: r.severity, value: String(r.n), color: SEVERITY_VAR[r.severity] },
                          { label: "rule", value: r.title },
                        ])
                      }
                      onMouseLeave={hide}
                    />
                  </svg>
                </div>
              </li>
            ))}
          </ul>
          <Tooltip tip={tip} />
        </>
      )}
    </ChartCard>
  );
}
