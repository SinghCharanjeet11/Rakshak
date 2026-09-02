"use client";

import type { Report, Severity } from "@/lib/api";
import {
  ChartCard,
  EmptyChart,
  Legend,
  SEVERITY_ORDER,
  SEVERITY_VAR,
  Tooltip,
  useTooltip,
} from "./primitives";

/**
 * Severity mix as a single stacked bar.
 *
 * A donut was the obvious reach here and the wrong one: with four ordinal statuses and
 * small counts, angle is harder to compare than length, and a ring wastes the space a
 * dense dashboard needs. One bar, four segments, 2px surface gaps so the boundaries stay
 * legible, and each segment direct-labelled once it is wide enough.
 */
export function SeverityBar({ report }: { report: Report }) {
  const { tip, show, hide } = useTooltip();

  const counts = SEVERITY_ORDER.map((sev) => ({
    sev,
    n: report.violations.filter((v) => v.severity === sev).length,
  }));
  const total = counts.reduce((a, c) => a + c.n, 0);
  const present = counts.filter((c) => c.n > 0);

  const H = 34;
  const GAP = 2; // surface gap between segments

  return (
    <ChartCard
      title="Severity mix"
      hint={total ? `${total} violation${total === 1 ? "" : "s"}` : undefined}
      legend={
        present.length > 1 ? (
          <Legend
            items={present.map((c) => ({
              label: c.sev,
              color: SEVERITY_VAR[c.sev],
              value: String(c.n),
            }))}
          />
        ) : undefined
      }
      table={
        <table className="w-full text-xs">
          <tbody>
            {counts.map((c) => (
              <tr key={c.sev} className="border-b border-line last:border-0">
                <td className="py-1.5 capitalize text-muted">{c.sev}</td>
                <td className="py-1.5 text-right tabular-nums text-body">{c.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      {total === 0 ? (
        <EmptyChart>No violations — nothing to break down.</EmptyChart>
      ) : (
        <>
          <svg
            viewBox={`0 0 100 ${H}`}
            preserveAspectRatio="none"
            className="h-[34px] w-full"
            role="img"
            aria-label={present
              .map((c) => `${c.n} ${c.sev}`)
              .join(", ")}
          >
            {(() => {
              let x = 0;
              return present.map((c, i) => {
                const w = (c.n / total) * 100;
                const isFirst = i === 0;
                const isLast = i === present.length - 1;
                const gapL = isFirst ? 0 : GAP / 2;
                const gapR = isLast ? 0 : GAP / 2;
                const seg = (
                  <rect
                    key={c.sev}
                    x={x + gapL}
                    y={0}
                    width={Math.max(0.5, w - gapL - gapR)}
                    height={H}
                    rx={1.2}
                    fill={SEVERITY_VAR[c.sev]}
                    style={{
                      transformOrigin: "left center",
                      animation: `grow-x 480ms cubic-bezier(0.22,1,0.36,1) ${i * 70}ms both`,
                    }}
                    onMouseMove={(e) =>
                      show(e, c.sev, [
                        {
                          label: "violations",
                          value: `${c.n} of ${total}`,
                          color: SEVERITY_VAR[c.sev],
                        },
                        {
                          label: "share",
                          value: `${((c.n / total) * 100).toFixed(0)}%`,
                        },
                      ])
                    }
                    onMouseLeave={hide}
                  />
                );
                x += w;
                return seg;
              });
            })()}
          </svg>

          {/* Direct labels below the bar — the count is never colour-alone. */}
          <div className="mt-2 flex text-[11px]">
            {present.map((c) => (
              <div
                key={c.sev}
                style={{ width: `${(c.n / total) * 100}%` }}
                className="min-w-0 truncate pr-2"
              >
                <span className="tabular-nums font-medium text-body">{c.n}</span>{" "}
                <span className="text-faint">{c.sev}</span>
              </div>
            ))}
          </div>
          <Tooltip tip={tip} />
        </>
      )}
    </ChartCard>
  );
}

export function severityCounts(report: Report): Record<Severity, number> {
  return SEVERITY_ORDER.reduce(
    (acc, s) => {
      acc[s] = report.violations.filter((v) => v.severity === s).length;
      return acc;
    },
    {} as Record<Severity, number>,
  );
}
