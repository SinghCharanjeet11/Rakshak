"use client";

import Link from "next/link";
import type { ReportSummary } from "@/lib/api";
import { ChartCard, EmptyChart, Tooltip, useTooltip } from "./primitives";

/**
 * Compliance score across successive verifications.
 *
 * Renders only at three or more reports. Below that a "trend" is a decoration — two points
 * make a line that always looks like a story, and one makes none at all. The stat tile on
 * the dashboard already carries the latest number, which is the honest read of a short
 * history.
 */
export function ScoreTrend({ reports }: { reports: ReportSummary[] }) {
  const { tip, show, hide } = useTooltip();

  // API returns newest first; a trend reads left-to-right oldest-first.
  const series = [...reports].reverse();

  if (series.length < 3) {
    return (
      <ChartCard title="Score trend">
        <EmptyChart>
          {series.length === 0
            ? "No verifications yet."
            : `${series.length} report${series.length === 1 ? "" : "s"} so far — a trend needs at least 3.`}
        </EmptyChart>
      </ChartCard>
    );
  }

  const W = 100;
  const H = 44;
  const x = (i: number) => (i / (series.length - 1)) * W;
  const y = (score: number) => H - (Math.max(0, Math.min(100, score)) / 100) * H;

  const path = series.map((r, i) => `${i ? "L" : "M"}${x(i)},${y(r.score)}`).join(" ");
  const latest = series[series.length - 1];
  const first = series[0];
  const delta = latest.score - first.score;

  return (
    <ChartCard
      title="Score trend"
      hint={`${series.length} reports · ${delta >= 0 ? "+" : ""}${delta.toFixed(1)} overall`}
      table={
        <table className="w-full text-xs">
          <tbody>
            {series.map((r) => (
              <tr key={r.id} className="border-b border-line last:border-0">
                <td className="py-1 font-mono text-muted">{r.id.slice(0, 14)}…</td>
                <td className="py-1 text-right tabular-nums text-body">
                  {r.score.toFixed(1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-28 w-full overflow-visible" role="img"
             aria-label={`Score across ${series.length} reports, from ${first.score} to ${latest.score}`}>
          {[0, 50, 100].map((g) => (
            <line
              key={g}
              x1={0}
              x2={W}
              y1={y(g)}
              y2={y(g)}
              stroke="var(--grid)"
              strokeWidth={0.4}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          <path
            d={path}
            fill="none"
            stroke="var(--pass-fg)"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
          {series.map((r, i) => (
            <circle
              key={r.id}
              cx={x(i)}
              cy={y(r.score)}
              r={2.4}
              fill={r.failed === 0 ? "var(--pass-fg)" : "var(--fail-fg)"}
              stroke="var(--surface)"
              strokeWidth={1.2}
              onMouseMove={(e) =>
                show(e, r.id, [
                  { label: "score", value: r.score.toFixed(1) },
                  { label: "failed", value: String(r.failed) },
                ])
              }
              onMouseLeave={hide}
            />
          ))}
        </svg>
        <div className="mt-2 flex items-baseline justify-between text-[11px] text-faint">
          <span>oldest</span>
          <Link
            href={`/reports/${latest.id}`}
            className="tabular-nums text-body underline-offset-2 hover:underline"
          >
            latest {latest.score.toFixed(1)}
          </Link>
        </div>
        <Tooltip tip={tip} />
      </div>
    </ChartCard>
  );
}
